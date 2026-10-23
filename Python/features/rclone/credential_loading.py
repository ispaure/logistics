"""Portable credential loading contracts; passwords never belong in requests/results."""
from dataclasses import dataclass, field
from typing import Callable


class CredentialBusyError(ValueError):
    """Publication was refused without waiting for another credential change."""


@dataclass(frozen=True)
class CredentialContext:
    cancelled: Callable[[], bool] = field(default=lambda: False, repr=False)
    valid: Callable[[], bool] = field(default=lambda: True, repr=False)


@dataclass(frozen=True)
class CredentialResult:
    key: object
    remotes: tuple[str, ...]
    saved: bool
    generation: int | None = None


@dataclass(frozen=True, eq=False)
class PreparedCredentials:
    """Opaque service-owned admission; contains no password or decoded settings."""
    request: object = field(repr=False)


@dataclass
class CredentialStage:
    publish: Callable[[CredentialContext], CredentialResult] = field(repr=False)
    valid: Callable[[], bool] = field(repr=False)
    close: Callable[[], None] = field(repr=False)
