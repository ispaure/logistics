"""Read-only native remote sessions bound to one credential generation."""
from contextlib import contextmanager
from pathlib import Path

from commonUtils.runtime.resources.paths import resource_path
from commonUtils.runtime.resources.provider import ResourceCapabilities
from features.rclone.access import ResourceAccess
from features.rclone.remote_access import NativeRemoteLocation
from .service import native_service


class NativeRemoteResources:
    private = remote_storage = True
    capabilities = ResourceCapabilities()

    def __init__(self, client, location):
        self.client, self.remote = client, location.remote
        self.generation = client.generation
        if location.generation is not None and location.generation != self.generation:
            raise ValueError('Credentials changed. Reopen the remote.')
        self._access = ResourceAccess(native_service(client).credentials.capture(self.remote))
        self.identity = client.connection_identity(self.remote)
        self.check()
        if location.identity is not None and location.identity != self.identity:
            raise ValueError('The remote connection changed. Reopen it.')
        self.location = NativeRemoteLocation(self.remote, self.identity, self.generation)
        self.root = Path('/remote') / str(self.generation) / self.remote

    @property
    def closed(self):
        return self._access.closed

    def check(self):
        if self.client.generation != self.generation:
            self.close()
            raise ValueError('Credentials changed. Reopen the remote.')
        self._access.check()

    def acquire(self):
        return self._access.acquire()

    def close(self):
        self._access.close()

    def operation(self, cancelled):
        return self._access.operation(cancelled)

    def relative(self, path):
        if isinstance(path, Path) and path.is_absolute():
            path = path.relative_to(self.root)
        return resource_path(str(path))

    def reopen(self):
        """Independent view of the original grant, even after this view closes."""
        self._access.grant.check()
        resource = native_service(self.client).remotes.open(self.location)
        try:
            self._access.grant.check()
        except BaseException:
            resource.close()
            raise
        return resource

    def list(self, path='', *, cancelled=lambda: False):
        with self.operation(cancelled):
            rows = self.client.entries(self.remote, self.relative(path))
            result = []
            for row in rows:
                self.check()
                key = resource_path(row['path'])
                if not key:
                    raise ValueError('Remote returned an invalid filename.')
                result.append(dict(row, path=key, name=Path(key).name,
                                   modified=row.get('modified', ''), size=row.get('size', 0)))
            self.check()
            return result

    def entry(self, path):
        self.check()
        key = self.relative(path)
        row = self.client.request('remote_stat', remote=self.remote, path=key, identity=self.identity)
        self.check()
        return dict(row, name=Path(key).name, path=key, directory=False, modified='')

    @contextmanager
    def open(self, path):
        from .remote_readers import RemoteSource
        self.check()
        source = RemoteSource(self.client, self.remote, self.relative(path), resource=self)
        try:
            with source.open(path) as stream:
                yield stream
        finally:
            source.close()

    def read_bytes(self, path, *, limit=16 * 1024 * 1024):
        with self.open(path) as stream:
            if stream.size > limit:
                from features.rclone.remote_policy import LocalCopyRequired
                raise LocalCopyRequired()
            return stream.read()

    def readers(self, *, progress=lambda message: None):
        from .remote_readers import RemoteReaders
        self._access.grant.check()
        return RemoteReaders(self.client, self.remote, resource=self, progress=progress)
