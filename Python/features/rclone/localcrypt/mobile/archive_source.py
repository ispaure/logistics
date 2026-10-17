"""Seekable encrypted ranges and lazy inner-archive members from the native bridge."""
import base64
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path

from commonUtils.runtime.range_reader import RangeReader
from commonUtils.filesystem.snapshots import file_revision
from commonUtils.runtime.operations import check_cancelled


def revision(path):
    return file_revision(path)


from services.documents.archive_access import NativeArchiveAccess


class NativeSource(NativeArchiveAccess):
    archive_action = 'crypt_archive'
    manifest_action = 'crypt_manifest'
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
