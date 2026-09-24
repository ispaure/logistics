"""
Detection helpers for the Logistics Calibre feature.
"""

from pathlib import Path

from commonUtils import configUtils

from models.local_folder import LocalFolder


CALIBRE_SECTION = "Calibre"
CALIBRE_LIBRARY_KEY = "calibre_lib_sub_path"
FOLDER_CONFIG_NAME = "remoteConfig.ini"


def get_library_path(folder: LocalFolder) -> Path | None:
    """
    Return the configured Calibre library path for a LocalFolder.

    The path is read from the folder's remoteConfig.ini file.
    """

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    sub_path = configUtils.config_section_map(config_path, CALIBRE_SECTION, CALIBRE_LIBRARY_KEY)

    if sub_path is None:
        return None

    return Path(folder.path, sub_path)


def has_library(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder has a configured Calibre library."""

    return get_library_path(folder) is not None