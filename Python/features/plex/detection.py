"""
Detection helpers for the Logistics Plex feature.
"""

from collections.abc import Collection

from models.logistics_folder import LogisticsFolder


PMS_DATA_SUFFIX = "-PMSDATA"


def is_pms_data_folder(folder: LogisticsFolder) -> bool:
    """Return whether a Logistics folder represents Plex Media Server data."""

    return folder.name.endswith(PMS_DATA_SUFFIX)


def has_pms_data_remote(folder: LogisticsFolder, remote_names: Collection[str]) -> bool:
    """Return whether a corresponding Plex Media Server data remote exists for a folder."""

    return f"{folder.name}{PMS_DATA_SUFFIX}" in remote_names
