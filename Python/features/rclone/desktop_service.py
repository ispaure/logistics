"""Desktop service composition over the existing credential and CLI authorities."""
from pathlib import Path
from . import session
from .service import CredentialGrant, CredentialService, LocalCryptService, RcloneService
from .remote_access import DesktopRemoteLocation, RemoteService
from .transfers.service import TransferService


class DesktopCredentials:
    lock_scope = 'package'

    def capture(self, key):
        key = Path(key)
        return CredentialGrant(key, session.revocation_check(key))

    def lock(self, key=None):
        paths = [Path(key)] if key is not None else session.paths()
        # Attempt every revocation even if a view's cleanup callback fails.
        failure = None
        for path in paths:
            from .remote_resources import invalidate_config
            # Saved config bytes are retained; existing views must still
            # retire. Explicitly reopening a saved config creates new access.
            for revoke in (lambda: session.forget(path),
                           lambda: invalidate_config(path.with_suffix('.conf'))):
                try:
                    revoke()
                except Exception as error:
                    failure = failure or error
        if failure is not None:
            raise failure


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
