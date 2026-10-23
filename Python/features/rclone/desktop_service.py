"""Desktop service composition over the existing credential and CLI authorities."""
from .service import CredentialService, LocalCryptService, RcloneService
from .desktop_credentials import DesktopCredentials
from .remote_access import DesktopRemoteLocation, RemoteService
from .transfers.service import TransferService




def _open_localcrypt(connection):
    from .localcrypt.backend import CryptResources
    return CryptResources(connection)


def _open_remote(location):
    if not isinstance(location, DesktopRemoteLocation):
        raise TypeError('Choose an explicit credential config and remote.')
    from .remote_resources import RemoteResources
    from . import executable
    binary = executable.ensure_rclone()
    if binary is None:
        raise ValueError('The rclone executable is required to browse remotes.')
    return RemoteResources(location.config, location.remote, binary=binary)


def _transfer_plan(request):
    from .transfers.desktop import build_plan
    return build_plan(request, service.credentials)


service = RcloneService(CredentialService(DesktopCredentials()),
                        LocalCryptService(_open_localcrypt), RemoteService(_open_remote),
                        TransferService(_transfer_plan))
