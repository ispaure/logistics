"""Read-only native rclone bridge; credentials exist only in this app session."""
import base64
import ctypes
import json
from pathlib import Path

PACKAGE_LIMIT = 1024 * 1024
DOWNLOAD_LIMIT = 32 * 1024 * 1024


class CloudClient:
    def __init__(self, *, library=None):
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
        if action not in {'import', 'list', 'read', 'probe', 'clear', 'cancel'}:
            raise ValueError('Unsupported remote operation.')
        data = json.dumps(values, ensure_ascii=False).encode('utf-8')
        if len(data) > PACKAGE_LIMIT * 2:
            raise ValueError('Credential package exceeds the request limit.')
        pointer = self.call(action.encode('ascii'), data)
        if not pointer:
            raise OSError('The native rclone bridge returned no response.')
        try:
            reply = json.loads(ctypes.string_at(pointer))
        finally:
            self.free(pointer)
        if not reply.get('ok'):
            raise ValueError(reply.get('error', 'Remote operation failed.'))
        return reply.get('result')

    def import_package(self, access, reference, password):
        with access.open(reference) as (_, source):
            data = source.read(PACKAGE_LIMIT + 1)
        if len(data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        return self.request('import', package=base64.b64encode(data).decode('ascii'), password=password)

    def entries(self, remote, path=''):
        return self.request('list', remote=remote, path=path)

    def download(self, remote, path):
        data = base64.b64decode(self.request('read', remote=remote, path=path), validate=True)
        if len(data) > DOWNLOAD_LIMIT:
            raise ValueError('Downloads are limited to 32 MiB.')
        return data

    def cancel(self):
        self.request('cancel')

    def clear(self):
        self.request('clear')


def download_name(path):
    name = Path(path).name
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
        import os
        from uuid import uuid4
        name = download_name(name)
        if not isinstance(data, bytes) or len(data) > DOWNLOAD_LIMIT:
            raise ValueError('Downloads are limited to 32 MiB.')
        folder = self.root / uuid4().hex
        folder.mkdir(mode=0o700)
        target = folder / name
        try:
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
                stream.write(data)
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
                if target.is_file() and not target.is_symlink() and target.stat().st_size <= DOWNLOAD_LIMIT:
                    result.append(target)
            except (OSError, ValueError, UnicodeError):
                continue
        return sorted(result, key=lambda p: (p.name.casefold(), str(p)))
