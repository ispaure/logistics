"""
Discovery helpers for folders managed by Logistics.
"""

from pathlib import Path

import config

from commonUtils.filesystem import directories as dirUtils

from .local_folder import LocalFolder


def get_local_folders() -> list[LocalFolder]:
    """Return all folders currently present under Server/Local."""

    local_root = Path(config.LogisticsConfig().path_remote_local)
    local_root.mkdir(parents=True, exist_ok=True)

    local_directory = dirUtils.Directory(local_root)

    return [LocalFolder(directory.path) for directory in local_directory.list_directories()]
