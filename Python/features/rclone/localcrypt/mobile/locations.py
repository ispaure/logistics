"""References for managed LocalCrypt trees and individual offline copies."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

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
    cipher_identity: str | None = None


@dataclass(frozen=True)
class OfflineCryptLocation:
    copies: object
    key: str
