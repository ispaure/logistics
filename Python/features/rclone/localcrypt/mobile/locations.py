"""References for managed LocalCrypt trees and individual offline copies."""
from dataclasses import dataclass
from pathlib import Path


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
