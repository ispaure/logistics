"""Native composition; credential authority remains process-wide across scenes."""
from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
from features.rclone.service import CredentialGrant, CredentialService, LocalCryptService, RcloneService
from features.rclone.remote_access import NativeRemoteLocation, RemoteService


@dataclass(frozen=True)
class LocalCryptLocation:
    """Physical copy binding, constructed by the feature rather than its host."""
    root: Path
    remote: str
    namespace: str | None = None
    storage_root: Path | None = None
    create: bool = True


@dataclass(frozen=True)
class OfflineCryptLocation:
    copies: object
    key: str


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
            with self._storage_access(blocking=False):
                # Recheck after taking the shared lock: another scene may have
                # published between service admission and native commit.
                if not valid():
                    raise ValueError('Credentials changed while loading. Try again.')
                return publish(context)
        stage.publish = commit
        return stage

    def restore(self, *, create=False):
        from features.rclone.credential_loading import CredentialResult
        with self._storage_access(blocking=False):
            names = self.client.restore(create=True) if create else self.client.restore()
            return CredentialResult(self.client.package_name, tuple(names), True, self.client.generation)

    def lock(self, key=None):
        if key is not None:
            raise ValueError('This runtime locks all loaded packages together.')
        self.client.lock()

    def retain(self, request):
        from .credential_retention import retain
        with self._storage_access(blocking=False):
            return retain(self.client, request)

    def forget(self, key=None):
        from .credential_retention import forget
        with self._storage_access(blocking=True):
            return forget(self.client, key)

    @contextmanager
    def _storage_access(self, *, blocking):
        # All native scenes share credential state. Hold its publication lock
        # through storage work so a different scene cannot restore/retain midway.
        state = getattr(self.client, 'credential_state', None)
        lock = state.lock if state is not None else None
        if lock is not None and not lock.acquire(blocking=blocking):
            from features.rclone.credential_loading import CredentialBusyError
            raise CredentialBusyError('Credentials are in use. Stop the active operation, then retry saving credentials.')
        try:
            yield
        finally:
            if lock is not None:
                lock.release()


def native_service(client):
    """One composition per client; grants follow the shared native generation."""
    if '_rclone_service' not in client.__dict__:
        def open_resource(location):
            from features.rclone.localcrypt.mobile.resources import CryptFiles, DownloadedCryptFile
            if isinstance(location, OfflineCryptLocation):
                if location.copies.client is not client:
                    raise ValueError('This encrypted copy belongs to another credential client.')
                return DownloadedCryptFile(location.copies, location.key)
            if not isinstance(location, LocalCryptLocation):
                raise TypeError('Choose a managed LocalCrypt location or an existing offline copy.')
            return CryptFiles(location.root, client, location.remote,
                              namespace=location.namespace, storage_root=location.storage_root,
                              create=location.create)
        def open_remote(location):
            if not isinstance(location, NativeRemoteLocation):
                raise TypeError('Choose a native remote location.')
            from .remote_resources import NativeRemoteResources
            return NativeRemoteResources(client, location)
        def transfer_plan(request):
            from features.rclone.transfers.mobile.plan import build_plan
            return build_plan(client, request, client._rclone_service.credentials)
        from features.rclone.transfers.service import TransferService
        client._rclone_service = RcloneService(CredentialService(NativeCredentials(client)),
                                               LocalCryptService(open_resource), RemoteService(open_remote),
                                               TransferService(transfer_plan))
    return client._rclone_service
