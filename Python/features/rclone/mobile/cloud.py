"""Scoped native rclone bridge; credentials can use device-protected encrypted storage."""
import base64
import ctypes
import json
from pathlib import Path, PurePosixPath

from .bridge_protocol import ACTIONS, decode_envelope
from .credential_state import NativeCredentialState
from features.rclone.credential_loading import CredentialBusyError

PACKAGE_LIMIT = 1024 * 1024


class CloudClient:
    supports_streaming = True
    # The native engine is process-global across scenes; so is its publication state.
    credential_state = NativeCredentialState()

    @property
    def session_privacy(self):
        # The native credential store is shared by all iPad scenes.
        return self.credential_state.session_privacy

    @property
    def package_records(self):
        return self.credential_state.package_records

    @property
    def session_privacies(self):
        return tuple(self.credential_state.package_privacy.values())

    def package_remotes(self, label, fallback=()):
        return self.credential_state.package_remotes(label, fallback)

    def resolve_remote(self, name, identity, *, cipher=False):
        return self.credential_state.resolve_remote(name, identity, cipher=cipher)

    @property
    def generation(self):
        return self.credential_state.generation

    @property
    def vault_attached(self):
        return (getattr(self, '_vault_attached', False)
                and getattr(self, '_vault_generation', None) == self.generation)

    @vault_attached.setter
    def vault_attached(self, value):
        self._vault_attached = value
        self._vault_generation = self.generation

    def __init__(self, *, library=None, vault=None):
        self.vault = vault
        self.package_name = ""
        self.vault_attached = False
        from commonUtils.runtime.platform import get_os, OS
        if library is None:
            current = get_os()
            if current is OS.ANDROID:
                library = 'liblogisticscloud.so'
            elif current is OS.IOS:
                library = None  # Functions statically linked into the native app.
            else:
                raise ValueError('Remote files require the native mobile build.')
        self.library = ctypes.CDLL(library)
        self.call = self.library.LogisticsCloud
        self.call.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.call.restype = ctypes.c_void_p
        self.free = self.library.LogisticsCloudFree
        self.free.argtypes = [ctypes.c_void_p]
        self.free.restype = None

    def request(self, action, **values):
        if action in {'import', 'clear', 'vault_open', 'add_smb', 'forget_package'}:
            # Serialize publication with the native commit across iPad scenes;
            # local reads and transfers keep their independent native scopes.
            blocking = action in {'clear', 'forget_package'}
            if not self.credential_state.lock.acquire(blocking=blocking):
                raise CredentialBusyError()
            try:
                return self._request(action, **values)
            finally:
                self.credential_state.lock.release()
        return self._request(action, **values)

    def _request(self, action, **values):
        if action not in ACTIONS:
            raise ValueError('Unsupported remote operation.')
        if values.get('remote') and values.get('identity'):
            values['remote'] = self.resolve_remote(values['remote'], values['identity'], cipher=action.startswith('crypt_'))
        if values.get('source_remote') and values.get('source_identity'):
            values['source_remote'] = self.resolve_remote(values['source_remote'], values['source_identity'], cipher=True)
        data = json.dumps(values, ensure_ascii=False).encode('utf-8')
        if len(data) > (45 * PACKAGE_LIMIT if action == 'crypt_write_buffer' else
                        PACKAGE_LIMIT * (24 if action == 'image_thumbnail' else 2)):
            raise ValueError('Credential package exceeds the request limit.')
        pointer = self.call(action.encode('ascii'), data)
        if not pointer:
            raise OSError('The native rclone bridge returned no response.')
        try:
            reply = decode_envelope(ctypes.string_at(pointer))
        finally:
            self.free(pointer)
        if not reply.get('ok'):
            if reply.get('error_code') == 'credentials_busy':
                raise CredentialBusyError(reply.get('error'))
            if reply.get('error_code') == 'archive_password':
                from commonUtils.archives.zip_access import ArchivePasswordError
                raise ArchivePasswordError(reply.get('error', 'Inner ZIP password required.'))
            raise ValueError(reply.get('error', 'Remote operation failed.'))
        if action in {'import', 'clear', 'vault_open', 'add_smb', 'forget_package'}:
            info = reply.get('credential_state')
            if not isinstance(info, dict):
                info = self.request('vault_info') if action != 'clear' else {}
            self.publish_credentials(action, values, info)
        return reply.get('result')

    def publish_credentials(self, action, values, info):
        return self.credential_state.publish(action, values, info)

    def import_package(self, access, reference, password, *, remember=True):
        with access.open(reference) as (name, source):
            data = source.read(PACKAGE_LIMIT + 1)
        if len(data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        name = download_name(name)
        if remember and getattr(self, 'vault', None) is not None and not self.vault_attached:
            self.restore(create=True)
        attached = self.vault_attached
        aliases = access.aliases(reference) if hasattr(access, 'aliases') else {}
        extra = {'aliases': aliases} if aliases else {}
        names = self.request('import', **extra, package=base64.b64encode(data).decode('ascii'),
                             password=password, package_name=name, session_only=not remember)
        self.vault_attached = attached
        self.package_name = name
        if remember and getattr(self, 'vault', None) is not None:
            self.vault.set_label(name)
        return names

    def add_smb(self, name, host, user, password, domain='', port='445', *, remember=True):
        if remember and self.vault is not None and not self.vault_attached:
            self.restore(create=True)
        attached = self.vault_attached
        names = self.request('add_smb', remote=name, host=host, user=user,
                             password=password, domain=domain, port=port,
                             session_only=not remember)
        self.vault_attached = attached
        info = self.request('vault_info')
        self.package_name = info['package_name']
        if remember and self.vault is not None:
            self.vault.set_label(self.package_name)
        return names

    def restore(self, *, create=False):
        if self.vault is None:
            return []
        values = self.vault.unlock(create=create)
        if values is None:
            info = self.request('vault_info')
            if isinstance(info, dict) and info.get('remotes'):
                self.package_name = info['package_name']
                self.vault_attached = False
                return info['remotes']
            self.request('clear')
            self.package_name = ''
            self.vault_attached = False
            return []
        result = self.request('vault_open', **values)
        self.vault_attached = True
        self.package_name = result['package_name']
        return result['remotes']

    def crypt_remotes(self):
        return self.request('crypt_remotes')

    def entries(self, remote, path=''):
        return self.request('list', remote=remote, path=path)

    def connection_identity(self, remote):
        return self.request('connection_identity', remote=remote)

    def cancel(self):
        self.request('cancel')

    def lock(self):
        self.request('clear')
        self.package_name = ''
        self.vault_attached = False

    def clear(self):
        # Another scene must not reattach the vault between clear and erasure.
        with self.credential_state.lock:
            try:
                self.lock()
            finally:
                if getattr(self, 'vault', None) is not None:
                    self.vault.forget()

    def forget_package(self, name):
        # Read a locked vault without restoring its other packages into memory.
        with self.credential_state.lock:
            values = self.vault.unlock() if self.vault is not None else None
            info = self.request('forget_package', package_name=name, **(values or {}))
            self.package_name = info['package_name']


def download_name(path):
    # Remote paths use POSIX separators regardless of the host testing them.
    # Windows Path would silently turn a forbidden backslash into a separator.
    if (not isinstance(path, str) or '\\' in path or path.startswith('/')
            or any(ord(c) < 32 for c in path) or any(part in {'.', '..'} for part in path.split('/'))):
        raise ValueError('Invalid remote download path.')
    name = PurePosixPath(path).name
    if not name or name in {'.', '..', '.complete'} or len(name) > 200 or any(ord(c) < 32 or c in '/\\' for c in name):
        raise ValueError('Invalid download filename.')
    return name


class Downloads:
    """Read existing private copies using UUID folders and completion markers."""
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Downloads require an absolute private directory.')
        self.root.mkdir(parents=True, exist_ok=True)

    def items(self):
        result = []
        for folder in self.root.iterdir():
            if folder.is_symlink() or not folder.is_dir() or len(folder.name) != 32 or any(c not in '0123456789abcdef' for c in folder.name):
                continue
            marker = folder / '.complete'
            if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 800:
                continue
            try:
                name = download_name(marker.read_text(encoding='utf-8'))
                target = folder / name
                if target.is_file() and not target.is_symlink():
                    result.append(target)
            except (OSError, ValueError, UnicodeError):
                continue
        return sorted(result, key=lambda p: (p.name.casefold(), str(p)))
