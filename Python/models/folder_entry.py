"""
Logical folder model for the new Logistics UI.
"""

from dataclasses import dataclass

from .local_folder import LocalFolder


@dataclass
class FolderEntry:
    """
    Represents one logical Logistics folder across local and remote storage.

    A folder may exist locally, remotely, or in both places.
    """

    name: str
    local: LocalFolder | None = None
    remote_name: str | None = None

    @property
    def has_local(self) -> bool:
        """Return whether this folder currently exists under Server/Local."""

        return self.local is not None

    @property
    def has_remote(self) -> bool:
        """Return whether this folder currently has a configured remote."""

        return self.remote_name is not None
