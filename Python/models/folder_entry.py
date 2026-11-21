"""
Logical folder model for the new Logistics UI.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from dataclasses import dataclass
from typing import Any

from .local_folder import LocalFolder


@dataclass
class FolderEntry:
    """
    Represents one logical Logistics folder across local and remote storage.

    A folder may exist locally, remotely, or in both places. Remote source
    context is intentionally opaque to the core model. storage_scope captures the
    selected workspace view without removing either transfer endpoint.
    """

    name: str
    local: LocalFolder | None = None
    remote_name: str | None = None
    remote_source: str | None = None
    remote_context: Any = None
    storage_scope: str | None = None

    @property
    def has_local(self) -> bool:
        """Return whether this folder currently exists under Server/Local."""

        return self.local is not None

    @property
    def has_remote(self) -> bool:
        """Return whether this folder currently has a configured remote."""

        return self.remote_name is not None
