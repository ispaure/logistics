"""Native composition; credential authority remains process-wide across scenes."""
from dataclasses import dataclass
from pathlib import Path
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
        return prepare(self.client, request, password)

    def restore(self, *, create=False):
        from features.rclone.credential_loading import CredentialResult
        names = self.client.restore(create=True) if create else self.client.restore()
        return CredentialResult(self.client.package_name, tuple(names), True)

    def lock(self, key=None):
        if key is not None:
            raise ValueError('This runtime locks all loaded packages together.')
        self.client.lock()


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
