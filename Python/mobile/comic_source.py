"""Lazy standalone encrypted CBZ reads; passwords and decoded members stay in RAM."""
from commonUtils.runtime.resources.archives import LocalArchiveSource
from services.documents.archive_access import NativeArchiveAccess


class LocalComicSource(NativeArchiveAccess, LocalArchiveSource):
    archive_action = 'file_archive'

    def __init__(self, path, client, password):
        super().__init__(password=password)
        LocalArchiveSource.__init__(self, path, max_read=8 * 1024 * 1024, max_members=5000)
        self.client = client

    def _request(self, action, **values):
        if action != self.archive_action:
            raise ValueError('Unsupported local archive operation.')
        with self.open(self.path) as stream:
            return self.client.request(action, fd=stream.fileno(), password=self.password or '', **values)

