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
from .credential_loading import CredentialBusyError, CredentialContext, CredentialStage, PreparedCredentials


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
    def retain(self, request): ...
    def forget(self, key: object | None = None): ...


@dataclass(frozen=True)
class _PendingLoad:
    stage: CredentialStage
    context: CredentialContext
    epoch: int
    cleanup: Callable[[], None]


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
            raise CredentialBusyError()
        try:
            yield
        finally:
            self._lock.release()

    def _invalidate_pending(self):
        """Reject in-flight preparation and erase every registered staged load."""
        self._epoch += 1
        pending, self._pending = self._pending, WeakKeyDictionary()
        failure = None
        for load in list(pending.values()):
            try:
                load.cleanup()
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
                self._pending[prepared] = _PendingLoad(stage, context, epoch, cleanup)
                return prepared
        except BaseException:
            stage.close()
            raise

    def unlock(self, prepared):
        """Publish exactly once on the platform's required thread/worker."""
        with self._publication():
            if not isinstance(prepared, PreparedCredentials) or prepared not in self._pending:
                raise ValueError('This credential load is closed or belongs to another runtime.')
            load = self._pending.pop(prepared)
            try:
                check_cancelled(load.context.cancelled)
                if load.epoch != self._epoch or not load.context.valid() or not load.stage.valid():
                    raise ValueError('Credentials changed while loading. Try again.')
                self._invalidate_pending()
                return load.stage.publish(load.context)
            finally:
                load.cleanup()

    def discard(self, prepared):
        with self._lock:
            pending = self._pending.pop(prepared, None)
            if pending is not None:
                pending.cleanup()

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
            self._invalidate_pending()
            return self._backend.restore(create=create)

    def lock(self, key=None):
        """Revoke access and pending loads after the host resolves unsaved edits."""
        with self._lock:
            try:
                self._invalidate_pending()
            finally:
                self._backend.lock(key)

    def retain(self, request, context=CredentialContext()):
        """Retain platform-approved material without changing unlocked grants."""
        with self._publication():
            check_cancelled(context.cancelled)
            if not context.valid():
                raise ValueError('Credential retention is no longer current. Try again.')
            return self._backend.retain(request)

    def forget(self, key=None, context=CredentialContext()):
        """Retire staged loads, revoke access and erase the selected saved material.

        Forgetting is serialized with publication. Once started it finishes even
        if the initiating view closes; failures may leave partial storage cleanup.
        """
        with self._lock:
            check_cancelled(context.cancelled)
            if not context.valid():
                raise ValueError('Credential forgetting is no longer current. Try again.')
            try:
                self._invalidate_pending()
            finally:
                result = self._backend.forget(key)
            return result


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
