"""Read-only remote access service; navigation and readers belong to their hosts."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, ContextManager, BinaryIO


@dataclass(frozen=True)
class DesktopRemoteLocation:
    config: Path
    remote: str


@dataclass(frozen=True)
class NativeRemoteLocation:
    remote: str
    identity: str | None = None
    generation: int | None = None


class RemoteSession(Protocol):
    root: Path
    remote: str

    def list(self, path='', *, cancelled: Callable[[], bool] = lambda: False) -> list[dict]: ...
    def check(self) -> None: ...
    def entry(self, path: str | Path) -> dict: ...
    def operation(self, cancelled: Callable[[], bool]) -> ContextManager: ...
    def relative(self, path: str | Path) -> str: ...
    def open(self, path: str | Path) -> ContextManager[BinaryIO]: ...
    def acquire(self) -> Callable: ...
    def close(self) -> None: ...


class RemoteService:
    """Open a generation-bound session using the platform's remote reference."""
    def __init__(self, open_resource: Callable[[object], RemoteSession]):
        self._open_resource = open_resource

    def open(self, location) -> RemoteSession:
        return self._open_resource(location)
