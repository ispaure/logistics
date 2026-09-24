"""
Discovery helpers for folders managed by Logistics.
"""

from pathlib import Path

import config

from commonUtils import dirUtils

from .local_folder import LocalFolder
from .remote_folder import RemoteFolder


def get_local_folders() -> list[LocalFolder]:
    """Return all folders currently present under Server/Local."""

    local_root = Path(config.LogisticsConfig().path_remote_local)
    local_root.mkdir(parents=True, exist_ok=True)

    local_directory = dirUtils.Directory(local_root)

    return [LocalFolder(directory.path) for directory in local_directory.list_directories()]


def get_remote_folders() -> list[RemoteFolder]:
    """Return all folders currently present under the remote/network mount root."""

    remote_root = Path(config.LogisticsConfig().path_remote_network_mount)
    remote_root.mkdir(parents=True, exist_ok=True)

    remote_directory = dirUtils.Directory(remote_root)

    return [RemoteFolder(directory.path) for directory in remote_directory.list_directories()]