"""Application services for credentials, remote/LocalCrypt access and transfers.

Platform adapters own credential publication and storage layout. An opened provider
is a resource session: its leases belong to browsers/readers, not to the account.
"""
from dataclasses import dataclass, field
from typing import Callable, Protocol
from threading import RLock
from contextlib import contextmanager
from weakref import WeakKeyDictionary, finalize
from commonUtils.runtime.operations import check_cancelled
from .credential_loading import CredentialBusyError, CredentialContext, PreparedCredentials


@dataclass(frozen=True)
class CredentialGrant:
    """Access to exactly one unlocked generation; contains no credential values."""
    key: object
    revoked: Callable[[], bool] = field(repr=False, compare=False)

    def check(self):
        if self.revoked():
            raise ValueError('Credentials changed or were locked. Reopen after unlocking.')


class CredentialBackend(Protocol):
    lock_scope: str

    def capture(self, key: object) -> CredentialGrant: ...
    def lock(self, key: object | None = None) -> None: ...
    def prepare(self, request, password: str): ...
    def restore(self, *, create: bool = False): ...


class CredentialService:
    """Own staged loading, single-use unlock publication and access revocation."""
    def __init__(self, backend: CredentialBackend):
        self._backend = backend
        self._lock = RLock()
        self._epoch = 0
        self._pending = WeakKeyDictionary()

    @property
    def lock_scope(self):
        return self._backend.lock_scope

    def capture(self, key):
        grant = self._backend.capture(key)
        grant.check()
        return grant

    @contextmanager
    def _publication(self):
        if not self._lock.acquire(blocking=False):
            raise CredentialBusyError('Credentials are in use. Stop the active operation, then retry loading the credential ZIP.')
        try:
            yield
        finally:
            self._lock.release()

    def _retire_pending(self):
        pending, self._pending = self._pending, WeakKeyDictionary()
        failure = None
        for _, _, _, cleanup in list(pending.values()):
            try:
                cleanup()
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure

    def prepare_load(self, request, password, context=CredentialContext()):
        """Decode/read on a worker without publishing credentials or saved files."""
        check_cancelled(context.cancelled)
        if not context.valid():
            raise ValueError('Credential loading is no longer current. Try again.')
        with self._publication():
            epoch = self._epoch
        stage = self._backend.prepare(request, password)
        try:
            check_cancelled(context.cancelled)
            with self._publication():
                if epoch != self._epoch or not context.valid() or not stage.valid():
                    raise ValueError('Credentials changed while loading. Try again.')
                prepared = PreparedCredentials(request)
                cleanup = finalize(prepared, stage.close)
                self._pending[prepared] = stage, context, epoch, cleanup
                return prepared
        except BaseException:
            stage.close()
            raise

    def unlock(self, prepared):
        """Publish exactly once on the platform's required thread/worker."""
        with self._publication():
            if not isinstance(prepared, PreparedCredentials) or prepared not in self._pending:
                raise ValueError('This credential load is closed or belongs to another runtime.')
            stage, context, epoch, cleanup = self._pending.pop(prepared)
            try:
                check_cancelled(context.cancelled)
                if epoch != self._epoch or not context.valid() or not stage.valid():
                    raise ValueError('Credentials changed while loading. Try again.')
                self._epoch += 1
                self._retire_pending()
                return stage.publish(context)
            finally:
                cleanup()

    def discard(self, prepared):
        with self._lock:
            pending = self._pending.pop(prepared, None)
            if pending is not None:
                pending[-1]()

    def load(self, request, password, context=CredentialContext()):
        prepared = self.prepare_load(request, password, context)
        try:
            return self.unlock(prepared)
        finally:
            self.discard(prepared)

    def restore(self, *, create=False, context=CredentialContext()):
        with self._publication():
            check_cancelled(context.cancelled)
            if not context.valid():
                raise ValueError('Credential restoration is no longer current. Try again.')
            self._epoch += 1
            self._retire_pending()
            return self._backend.restore(create=create)

    def lock(self, key=None):
        """Revoke access and pending loads after the host resolves unsaved edits."""
        with self._lock:
            self._epoch += 1
            try:
                self._retire_pending()
            finally:
                self._backend.lock(key)


class LocalCryptService:
    """Open independent resource sessions using a platform-owned copy reference."""
    def __init__(self, open_resource):
        self._open_resource = open_resource

    def open(self, location):
        return self._open_resource(location)


class RcloneService:
    """Retained composition root; browser navigation stays with each browser."""
    def __init__(self, credentials, localcrypt, remotes, transfers):
        self.credentials = credentials
        self.localcrypt = localcrypt
        self.remotes = remotes
        self.transfers = transfers
