"""
Folder helpers for the Logistics Plex feature.
"""

from pathlib import Path

import config

from models.local_folder import LocalFolder
from models.logistics_folder import LogisticsFolder
from models.remote_folder import RemoteFolder

from .detection import PMS_DATA_SUFFIX


def get_pms_data_name(folder: LogisticsFolder) -> str:
    """Return the PMS data folder name associated with a Logistics folder."""

    return f"{folder.name}{PMS_DATA_SUFFIX}"


def get_local_pms_data_folder(folder: LogisticsFolder) -> LocalFolder:
    """Return the LocalFolder containing Plex Media Server package data."""

    folder_name = get_pms_data_name(folder)
    folder_path = Path(config.LogisticsConfig().path_remote_local, folder_name)

    return LocalFolder(folder_path)


def get_remote_pms_data_folder(folder: LogisticsFolder) -> RemoteFolder:
    """Return the RemoteFolder containing Plex Media Server package data."""

    folder_name = get_pms_data_name(folder)
    folder_path = Path(config.LogisticsConfig().path_remote_network_mount, folder_name)

    return RemoteFolder(folder_path)