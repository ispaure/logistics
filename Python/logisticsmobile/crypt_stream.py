"""Seekable encrypted ranges and lazy inner-archive members from the native bridge."""
import base64
from collections import OrderedDict
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from zipfile import ZipInfo

from commonUtils.runtime.range_reader import RangeReader
from commonUtils.runtime.operations import check_cancelled


def revision(path):
    info = Path(path).stat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class NativeArchive:
    def __init__(self, source):
        self.source = source
        self.members = []
        for row in source.request('crypt_archive'):
            info = ZipInfo(row['name'])
            info.file_size, info.CRC = row['size'], row['crc']
            info.flag_bits = 0  # This facade exposes authenticated decoded members.
            self.members.append(info)
        self.protected = [row['name'] for row in source.headers if row['flags'] & 1 and not row['directory']]

    def content_manifest(self, *, cancelled=lambda: False):
        check_cancelled(cancelled)
        rows = self.source.request('crypt_manifest')
        check_cancelled(cancelled)
        return {name: None if value is None else tuple(value) for name, value in rows.items()}

    def infolist(self):
        return list(self.members)

    def namelist(self):
        return [member.filename for member in self.members]

    def getinfo(self, name):
        for info in self.members:
            if info.filename == name:
                return info
        raise KeyError(name)

    def read(self, member):
        name = member.filename if isinstance(member, ZipInfo) else member
        self.getinfo(name)
        return self.source.read_member(name)

    @contextmanager
    def open(self, member, *args, **kwargs):
        with BytesIO(self.read(member)) as stream:
            yield stream


class NativeSource:
    private = True
    def __init__(self, client, record, path, *, password='', cancelled=lambda: False):
        self.client, self.record, self.path = client, dict(record), Path(path)
        self.password, self.cancelled = password, cancelled
        self.expected = revision(self.path)
        self.generation = client.generation
        self.headers = None
        self.cache = OrderedDict()
        self.cache_bytes = 0
        data = self.request('crypt_stat')
        self.name, self.size = data['name'], data['size']

    def version(self, path):
        check_cancelled(self.cancelled)
        if self.client.generation != self.generation:
            self.cache.clear()
            self.cache_bytes = 0
            raise ValueError('Credentials changed or were locked. Reopen the file after unlocking.')
        current = revision(self.path)
        if current != self.expected:
            raise ValueError('The encrypted file changed; reopen it.')
        return current

    def request(self, action, **values):
        self.version(self.path)
        if action == 'crypt_archive' and not values and self.headers is not None:
            return self.headers
        with self.path.open('rb') as encrypted:
            result = self.client.request(action, remote=self.record['remote'], identity=self.record['identity'],
                path=self.record['encrypted_path'], fd=encrypted.fileno(), password=self.password, **values)
        self.version(self.path)
        if action == 'crypt_archive' and not values:
            self.headers = result
        return result

    @contextmanager
    def open(self, path):
        def read(offset, count):
            return base64.b64decode(self.request('crypt_range', offset=offset, count=count)['data'], validate=True)
        with RangeReader(self.size, read, cache_blocks=2, validate=lambda: self.version(self.path)) as stream:
            yield stream

    @contextmanager
    def open_archive(self, path, password=None):
        if password is not None:
            self.password = password
        archive = NativeArchive(self)
        if archive.protected:
            # Validate the supplied inner password before presenting a reader.
            candidates = [info for info in archive.members if info.filename in archive.protected]
            archive.read(min(candidates, key=lambda info: info.file_size))
        yield archive

    def archive_password(self, path):
        return self.password or None

    def read_member(self, member):
        self.version(self.path)
        key = member, self.password
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        data = base64.b64decode(self.request('crypt_archive', member=member)['data'], validate=True)
        if len(data) > 16 * 1024 * 1024:
            raise ValueError('Archive member exceeds the read buffer limit.')
        self.cache[key] = data
        self.cache_bytes += len(data)
        while self.cache_bytes > 8 * 1024 * 1024 or len(self.cache) > 32:
            _, removed = self.cache.popitem(last=False)
            self.cache_bytes -= len(removed)
        return data
