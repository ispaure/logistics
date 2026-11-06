"""Generation-bound remote ranges and native archive snapshots kept only in RAM."""
import base64
from contextlib import contextmanager
from threading import Event, Thread
from uuid import uuid4

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.range_reader import RangeReader
from services.documents.archive_access import NativeArchiveAccess
from features.rclone.remote_policy import LocalCopyRequired


class RemoteSource(NativeArchiveAccess):
    archive_action = 'remote_archive'
    private = True
    archive_limit = 128 * 1024 * 1024

    def __init__(self, client, remote, path, *, password='', cancelled=lambda: False,
                 progress=lambda message: None, resource=None, owns_resource=False):
        super().__init__(password=password)
        from features.rclone.remote_access import NativeRemoteLocation
        from .service import native_service
        if resource is not None and (resource.client is not client or resource.remote != remote):
            raise ValueError('The remote view belongs to another connection.')
        self.resource = resource or native_service(client).remotes.open(NativeRemoteLocation(remote))
        self.owns_resource = owns_resource or resource is None
        self.client, self.remote, self.path = client, remote, path
        self.generation = self.resource.generation
        self.identity = self.resource.identity
        self.cancelled = cancelled
        self.progress = progress
        self.cache_token = None
        try:
            info = self.request('remote_stat')
            self.size, self.expected = info['size'], info['revision']
        except BaseException:
            self.close()
            raise

    def check(self):
        check_cancelled(self.cancelled)
        if self.closed or self.client.generation != self.generation:
            self.close()
            raise ValueError('Credentials changed or were locked. Reopen the remote.')
        self.resource.check()

    def version(self, path):
        self.check()
        if self.cache_token is not None:
            return self.expected
        result = self.request('remote_stat')
        if result['revision'] != self.expected:
            raise ValueError('The remote file changed. Reopen it.')
        return self.expected

    def _request(self, action, *, password, **values):
        if action == self.archive_action and self.cache_token is not None:
            action = 'remote_cache_archive'
            values['run'] = self.cache_token
        elif action == 'remote_stat':
            self.progress('Checking remote file and connection')
        elif action == self.archive_action:
            member = values.get('member')
            self.progress('Reading remote archive member: ' + member if member else 'Reading remote archive index')
        else:
            self.progress('Reading remote file data')
        self.check()  # Presentation callbacks may close or revoke this source.
        return self.client.request(action, remote=self.remote, path=self.path, identity=self.identity,
            expected=getattr(self, 'expected', ''), password=password, **values)

    def cache_archive(self):
        """One native network stream into RAM; progress/control bypass network locks."""
        if self.size > self.archive_limit:
            raise LocalCopyRequired()
        self.check()
        token, stopped = uuid4().hex, Event()
        self.cache_token = token
        def poll():
            previous = None
            while not stopped.wait(.25):
                try:
                    status = self.client.request('remote_cache_status', run=token)
                    total, done = status['total'], status['done']
                    if total and (done, total) != previous:
                        previous = done, total
                        self.progress(f'Downloading archive to memory: {100 * done // total}% '
                                      f'({done / 1048576:.1f} / {total / 1048576:.1f} MiB)')
                except Exception:
                    return
        worker = Thread(target=poll, daemon=True)
        started = False
        try:
            self.progress('Downloading archive to memory: 0%')
            worker.start()
            started = True
            self.check()
            self.client.request('remote_cache_open', remote=self.remote, path=self.path,
                                identity=self.identity, expected=self.expected, run=token)
            self.check()
        except BaseException:
            # An earlier close may have run before native cache publication.
            # Retire this exact token again after the request has finished.
            try:
                self.close()
            finally:
                self.client.request('remote_cache_close', run=token)
            raise
        finally:
            stopped.set()
            if started:
                worker.join()
        try:
            self.progress('Archive downloaded: 100% · Preparing reader from memory')
        except BaseException:
            self.close()
            raise

    @contextmanager
    def open(self, path):
        def read(offset, count):
            data = base64.b64decode(self.request('remote_range', offset=offset, count=count)['data'], validate=True)
            self.check()
            return data
        with RangeReader(self.size, read, cache_blocks=2, max_read=16*1024*1024, validate=self.check) as stream:
            yield stream

    def close(self):
        with self._archive_lock:
            token, self.cache_token = self.cache_token, None
            super().close()
        try:
            if self.owns_resource:
                self.resource.close()
        finally:
            if token is not None:
                self.client.request('remote_cache_close', run=token)
