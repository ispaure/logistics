"""Application services for credential generations and opened LocalCrypt resources.

Platform adapters own credential publication and storage layout. An opened provider
is a resource session: its leases belong to browsers/readers, not to the account.
"""
from dataclasses import dataclass, field
from typing import Callable, Protocol


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


class CredentialService:
    """Capture unlocked access or lock it; saved-package retention is separate."""
    def __init__(self, backend: CredentialBackend):
        self._backend = backend

    @property
    def lock_scope(self):
        return self._backend.lock_scope

    def capture(self, key):
        grant = self._backend.capture(key)
        grant.check()
        return grant

    def lock(self, key=None):
        """Revoke access after the presentation host has resolved unsaved edits."""
        self._backend.lock(key)


class LocalCryptService:
    """Open independent resource sessions using a platform-owned copy reference."""
    def __init__(self, open_resource):
        self._open_resource = open_resource

    def open(self, location):
        return self._open_resource(location)


class RcloneService:
    """Retained composition root; browser navigation stays with each browser."""
    def __init__(self, credentials, localcrypt):
        from .transfers.service import TransferService
        self.credentials = credentials
        self.localcrypt = localcrypt
        self.transfers = TransferService()
