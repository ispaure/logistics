"""
Detection helpers for the Logistics Plex feature.
"""

import os
from collections.abc import Collection
from pathlib import Path

from commonUtils import fileUtils
from commonUtils.osUtils import OS, get_os

from models.logistics_folder import LogisticsFolder


PMS_DATA_SUFFIX = "-PMSDATA"


def is_pms_data_folder(folder: LogisticsFolder) -> bool:
    """Return whether a Logistics folder represents Plex Media Server data."""

    return folder.name.endswith(PMS_DATA_SUFFIX)


def has_pms_data_remote(folder: LogisticsFolder, remote_names: Collection[str]) -> bool:
    """Return whether a corresponding Plex Media Server data remote exists for a folder."""

    return f"{folder.name}{PMS_DATA_SUFFIX}" in remote_names


def get_pms_data_path() -> Path | None:
    """Return the Plex Media Server data directory for the current platform."""

    user_home_dir = fileUtils.get_user_home_dir()

    match get_os():
        case OS.WIN:
            return Path(os.environ['LOCALAPPDATA'], 'Plex Media Server')

        case OS.MAC:
            return Path(user_home_dir, 'Library', 'Application Support', 'Plex Media Server')

        case OS.LINUX:
            candidates = [
                Path('/var/lib/plexmediaserver/Library/Application Support/Plex Media Server'),
                Path(user_home_dir, '.var', 'app', 'tv.plex.PlexMediaServer', 'data', 'Plex Media Server'),
                Path(user_home_dir, 'snap', 'plexmediaserver', 'common', 'Library', 'Application Support', 'Plex Media Server'),
            ]

            for path in candidates:
                if path.exists():
                    return path

            return None

        case _:
            return None