"""Resource-session lifetime bound to one credential generation."""
from contextlib import contextmanager
from threading import RLock
from commonUtils.runtime.resources.lifetime import ResourceLeases, WorkerCancellation
from commonUtils.runtime.operations import check_cancelled


class ResourceAccess:
    def __init__(self, grant):
        self.grant = grant
        self.closed = False
        self._lock = RLock()
        self._cancellation = WorkerCancellation()
        self._leases = ResourceLeases(validate=self.check, close=self.close)

    def check(self):
        check_cancelled(self._cancellation.current)
        with self._lock:
            if self.closed:
                raise ValueError('This resource view is closed. Reopen it.')
            try:
                self.grant.check()
            except ValueError:
                self.closed = True
                raise

    def acquire(self):
        return self._leases.acquire()

    @contextmanager
    def operation(self, cancelled):
        with self._cancellation.scope(cancelled):
            self.check()
            yield

    def close(self):
        with self._lock:
            self.closed = True
