"""Read-only native rclone bridge; credentials can use device-protected encrypted storage."""
import base64
import ctypes
import json
from pathlib import Path, PurePosixPath

PACKAGE_LIMIT = 1024 * 1024
DOWNLOAD_LIMIT = 32 * 1024 * 1024


class CloudClient:
    supports_streaming = True
    def __init__(self, *, library=None, vault=None):
        self.vault = vault
        self.package_name = ""
        self.vault_attached = False
        self.generation = 0
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
        if action not in {'import', 'list', 'read', 'crypt_read', 'probe', 'clear', 'cancel', 'vault_open', 'vault_info', 'crypt_remotes', 'crypt_fetch', 'crypt_describe', 'crypt_decode', 'crypt_encode', 'crypt_metadata', 'crypt_path', 'crypt_raw_read', 'crypt_raw_write', 'crypt_stat', 'crypt_range', 'crypt_archive', 'crypt_manifest', 'crypt_thumbnail', 'file_thumbnail', 'image_thumbnail', 'remote_thumbnail', 'file_archive'}:
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
        if action in {'import', 'clear', 'vault_open'}:
            self.generation += 1
        return reply.get('result')

    def import_package(self, access, reference, password, *, remember=True):
        with access.open(reference) as (name, source):
            data = source.read(PACKAGE_LIMIT + 1)
        if len(data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        name = download_name(name)
        if remember and getattr(self, 'vault', None) is not None and not self.vault_attached:
            self.restore(create=True)
        names = self.request('import', package=base64.b64encode(data).decode('ascii'),
                             password=password, package_name=name, session_only=not remember)
        self.package_name = name
        if remember and getattr(self, 'vault', None) is not None:
            self.vault.set_label(name)
        if not remember:
            self.vault_attached = False
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

    def download(self, remote, path):
        from tempfile import TemporaryFile
        with TemporaryFile() as stream:
            self.download_into(remote, path, stream.fileno())
            stream.seek(0)
            return stream.read(DOWNLOAD_LIMIT + 1)

    def download_into(self, remote, path, descriptor):
        return self.request('read', remote=remote, path=path, fd=descriptor)

    def download_decrypted_into(self, remote, path, descriptor):
        return self.request('crypt_read', remote=remote, path=path, fd=descriptor)

    def cancel(self):
        self.request('cancel')

    def clear(self):
        self.request('clear')
        self.package_name = ''
        self.vault_attached = False
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
    """Private copies use UUID folders, exclusive creation and completion markers."""
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Downloads require an absolute private directory.')
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, name, data):
        if not isinstance(data, bytes) or len(data) > DOWNLOAD_LIMIT:
            raise ValueError('Downloads are limited to 32 MiB.')
        return self._write(name, lambda stream: stream.write(data))

    def fetch(self, client, remote, path, *, decrypted=False):
        name = download_name(path)
        download = client.download_decrypted_into if decrypted else client.download_into
        return self._write(name, lambda stream: download(remote, path, stream.fileno()))

    def _write(self, name, writer):
        import os
        from uuid import uuid4
        name = download_name(name)
        folder = self.root / uuid4().hex
        folder.mkdir(mode=0o700)
        target = folder / name
        try:
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                writer(stream)
                stream.flush()
                os.fsync(stream.fileno())
            (folder / '.complete').write_text(name, encoding='utf-8')
        except Exception:
            target.unlink(missing_ok=True)
            (folder / '.complete').unlink(missing_ok=True)
            folder.rmdir()
            raise
        return target

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
