"""Native credential adapter; publication remains process-wide across scenes."""
from contextlib import contextmanager
from features.rclone.service import CredentialGrant
from features.rclone.credential_loading import CredentialBusyError, CredentialResult, CredentialStage


class NativeCredentials:
    # The native clear operation locks all loaded packages, not one named remote.
    lock_scope = 'all'

    def __init__(self, client):
        self.client = client

    def capture(self, key):
        generation = self.client.generation
        return CredentialGrant(key, lambda: self.client.generation != generation)

    def prepare(self, request, password):
        from .credential_loading import prepare
        stage = prepare(self.client, request, password)
        publish, valid = stage.publish, stage.valid
        def commit(context):
            with self._publication(blocking=False):
                # Recheck after taking the shared lock: another scene may have
                # published between service admission and native commit.
                if not valid():
                    raise ValueError('Credentials changed while loading. Try again.')
                return publish(context)
        return CredentialStage(publish=commit, valid=valid, close=stage.close)

    def restore(self, *, create=False):
        with self._publication(blocking=False):
            names = self.client.restore(create=True) if create else self.client.restore()
            return CredentialResult(self.client.package_name, tuple(names), True, self.client.generation)

    def lock(self, key=None):
        if key is not None:
            raise ValueError('This runtime locks all loaded packages together.')
        self.client.lock()

    def retain(self, request):
        from .credential_retention import retain
        with self._publication(blocking=False):
            return retain(self.client, request)

    def forget(self, key=None):
        from .credential_retention import forget
        with self._publication(blocking=True):
            return forget(self.client, key)

    @contextmanager
    def _publication(self, *, blocking):
        # All native scenes share credential state. Hold its publication lock
        # through storage work so a different scene cannot restore/retain midway.
        state = getattr(self.client, 'credential_state', None)
        lock = state.lock if state is not None else None
        if lock is not None and not lock.acquire(blocking=blocking):
            raise CredentialBusyError()
        try:
            yield
        finally:
            if lock is not None:
                lock.release()
