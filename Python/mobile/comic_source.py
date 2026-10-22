"""Lazy standalone encrypted CBZ reads; passwords and decoded members stay in RAM."""
from collections import OrderedDict
from contextlib import contextmanager
from commonUtils.runtime.resources.archives import LocalArchiveSource
from services.documents.archive_access import NativeArchiveAccess


class LocalComicSource(NativeArchiveAccess, LocalArchiveSource):
    archive_action = 'file_archive'

    def __init__(self, path, client, password):
        super().__init__(path, max_read=8 * 1024 * 1024, max_members=5000)
        self.client, self.password = client, password
        self.headers = None
        self.cache, self.cache_bytes = OrderedDict(), 0

    def request(self, action, **values):
        self.check()
        if action != self.archive_action:
            raise ValueError('Unsupported local archive operation.')
        if not values and self.headers is not None:
            return self.headers
        with self.open(self.path) as stream:
            result = self.client.request(action, fd=stream.fileno(), password=self.password or '', **values)
        if not values:
            self.headers = result
        return result

