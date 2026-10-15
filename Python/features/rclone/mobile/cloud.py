"""Scoped native rclone bridge; credentials can use device-protected encrypted storage."""
import base64
import ctypes
import json
import weakref
from pathlib import Path, PurePosixPath

PACKAGE_LIMIT = 1024 * 1024


class CloudClient:
    supports_streaming = True
    # The native bridge is process-global, including across iPad scenes. Every
    # wrapper must invalidate cached plaintext when any wrapper replaces it.
    _credential_generation = 0
    _credential_observers = weakref.WeakSet()
    _session_privacy = None

    @property
    def session_privacy(self):
        # The native credential store is shared by all iPad scenes.
        return CloudClient._session_privacy

    @property
    def generation(self):
        return CloudClient._credential_generation

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
        if action not in {'remote_cache_open', 'remote_cache_status', 'remote_cache_close', 'remote_cache_archive', 'remote_stat', 'remote_range', 'remote_archive', 'add_smb', 'import', 'list', 'connection_identity', 'mirror_info', 'mirror_validate', 'mirror_progress', 'mirror_review', 'mirror_review_progress', 'mirror_review_clear', 'mirror_sync', 'probe', 'clear', 'cancel', 'vault_open', 'vault_info', 'protect_package', 'unprotect_package', 'crypt_remotes', 'crypt_describe', 'crypt_decode', 'crypt_encode', 'crypt_metadata', 'crypt_path', 'crypt_raw_read', 'crypt_raw_write', 'crypt_stat', 'crypt_range', 'crypt_archive', 'crypt_manifest', 'crypt_thumbnail', 'file_thumbnail', 'image_thumbnail', 'remote_thumbnail', 'file_archive'}:
            raise ValueError('Unsupported remote operation.')
        data = json.dumps(values, ensure_ascii=False).encode('utf-8')
        if len(data) > PACKAGE_LIMIT * (24 if action == 'image_thumbnail' else 2):
            raise ValueError('Credential package exceeds the request limit.')
        pointer = self.call(action.encode('ascii'), data)
        if not pointer:
            raise OSError('The native rclone bridge returned no response.')
        try:
            reply = json.loads(ctypes.string_at(pointer))
        finally:
            self.free(pointer)
        if not reply.get('ok'):
            if reply.get('error_code') == 'archive_password':
                from commonUtils.archives.zip_access import ArchivePasswordError
                raise ArchivePasswordError(reply.get('error', 'Inner ZIP password required.'))
            raise ValueError(reply.get('error', 'Remote operation failed.'))
        if action in {'import', 'clear', 'vault_open', 'add_smb'}:
            if action in {'import', 'add_smb'} and values.get('session_only'):
                from .session_privacy import ResumePassword
                CloudClient._session_privacy = ResumePassword(values.get('password', ''))
            else:
                CloudClient._session_privacy = None
            CloudClient._credential_generation += 1
            for observer in tuple(CloudClient._credential_observers):
                observer.credentials_changed()
        return reply.get('result')

    def import_package(self, access, reference, password, *, remember=True):
        with access.open(reference) as (name, source):
            data = source.read(PACKAGE_LIMIT + 1)
        if len(data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        name = download_name(name)
        if remember and getattr(self, 'vault', None) is not None and not self.vault_attached:
            self.restore(create=True)
        attached = self.vault_attached
        names = self.request('import', package=base64.b64encode(data).decode('ascii'),
                             password=password, package_name=name, session_only=not remember)
        self.vault_attached = attached and remember
        self.package_name = name
        if remember and getattr(self, 'vault', None) is not None:
            self.vault.set_label(name)
        if not remember:
            self.vault_attached = False
        return names

    def add_smb(self, name, host, user, password, domain='', port='445', *, remember=True):
        if remember and self.vault is not None and not self.vault_attached:
            self.restore(create=True)
        attached = self.vault_attached
        names = self.request('add_smb', remote=name, host=host, user=user,
                             password=password, domain=domain, port=port,
                             session_only=not remember)
        self.vault_attached = attached and remember
        if not remember:
            self.vault_attached = False
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
        self.lock()
        if getattr(self, 'vault', None) is not None:
            self.vault.forget()


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
