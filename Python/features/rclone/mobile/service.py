"""Compose native credentials, resource sessions and transfers for one client."""
from features.rclone.service import CredentialService, LocalCryptService, RcloneService
from features.rclone.remote_access import NativeRemoteLocation, RemoteService
from features.rclone.localcrypt.mobile.locations import LocalCryptLocation, OfflineCryptLocation
from .credentials import NativeCredentials


def native_service(client):
    """One composition per client; grants follow the shared native generation."""
    if '_rclone_service' not in client.__dict__:
        credentials = CredentialService(NativeCredentials(client))

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
            return build_plan(client, request, credentials)

        from features.rclone.transfers.service import TransferService
        client._rclone_service = RcloneService(
            credentials=credentials,
            localcrypt=LocalCryptService(open_resource),
            remotes=RemoteService(open_remote),
            transfers=TransferService(transfer_plan))
    return client._rclone_service
