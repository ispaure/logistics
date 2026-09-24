"""
Detection helpers for the Logistics YouTube downloader feature.
"""

from pathlib import Path

from commonUtils import configUtils

from models.local_folder import LocalFolder


FOLDER_CONFIG_NAME = "remoteConfig.ini"

YOUTUBE_DOWNLOAD_SECTION = "Youtube-Download"
CONFIG_SUB_PATH_KEY = "config_sub_path"


def get_config_sub_path(folder: LocalFolder) -> str | None:
    """Return the configured YouTube downloader sub-path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    return configUtils.config_section_map(config_path, YOUTUBE_DOWNLOAD_SECTION, CONFIG_SUB_PATH_KEY)


def get_config_path(folder: LocalFolder) -> Path | None:
    """Return the configured YouTube downloader directory for a LocalFolder."""

    sub_path = get_config_sub_path(folder)

    if sub_path is None:
        return None

    return Path(folder.path, sub_path.replace("\\", "/"))


def has_config(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder has YouTube downloader configuration."""

    return get_config_path(folder) is not None