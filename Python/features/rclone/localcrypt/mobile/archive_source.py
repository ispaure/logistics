"""Seekable encrypted ranges and lazy inner-archive members from the native bridge."""
import base64
from contextlib import contextmanager
from pathlib import Path

from commonUtils.runtime.resources.range_reader import RangeReader
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
        super().__init__(password=password)
        self.client, self.record, self.path = client, dict(record), Path(path)
        self.cancelled = cancelled
        self.expected = revision(self.path)
        self.generation = client.generation
        try:
            data = self.request('crypt_stat')
            self.name, self.size = data['name'], data['size']
        except BaseException:
            self.close()
            raise

    def version(self, path):
        self._check_open()
        check_cancelled(self.cancelled)
        if self.client.generation != self.generation:
            self.close()
            raise ValueError('Credentials changed or were locked. Reopen the file after unlocking.')
        current = revision(self.path)
        if current != self.expected:
            raise ValueError('The encrypted file changed; reopen it.')
        return current

    def _request(self, action, **values):
        with self.path.open('rb') as encrypted:
            return self.client.request(action, remote=self.record['remote'], identity=self.record['identity'],
                path=self.record['encrypted_path'], fd=encrypted.fileno(), password=self.password, **values)

    @contextmanager
    def open(self, path):
        def read(offset, count):
            data = base64.b64decode(self.request('crypt_range', offset=offset, count=count)['data'], validate=True)
            self.check()
            return data
        with RangeReader(self.size, read, cache_blocks=2, validate=self.check) as stream:
            yield stream
