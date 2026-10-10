"""
Detection helpers for the Logistics Comics feature.
"""

from pathlib import Path

from commonUtils.configuration import legacy as configUtils
from commonUtils.filesystem import files as fileUtils
from commonUtils.runtime.platform import OS, get_os

from models.local_folder import LocalFolder


FOLDER_CONFIG_NAME = "remoteConfig.ini"

COMIC_RACK_SECTION = "ComicRack"
COMIC_RACK_LOCAL_KEY = "appdata_local_cyo_sub_path"
COMIC_RACK_ROAMING_KEY = "appdata_roaming_cyo_sub_path"

YAC_READER_SECTION = "YACReaderLibrary"
YAC_READER_INI_KEY = "yacreaderlibrary_ini_sub_path"


def get_comic_rack_local_path(folder: LocalFolder) -> Path | None:
    """Return the configured ComicRack local AppData path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    sub_path = configUtils.config_section_map(config_path, COMIC_RACK_SECTION, COMIC_RACK_LOCAL_KEY)

    if sub_path is None:
        return None

    return Path(folder.path, sub_path)


def get_comic_rack_roaming_path(folder: LocalFolder) -> Path | None:
    """Return the configured ComicRack roaming AppData path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    sub_path = configUtils.config_section_map(config_path, COMIC_RACK_SECTION, COMIC_RACK_ROAMING_KEY)

    if sub_path is None:
        return None

    return Path(folder.path, sub_path)


def has_comic_rack(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder has the required ComicRack configuration."""

    return get_comic_rack_local_path(folder) is not None and get_comic_rack_roaming_path(folder) is not None


def get_yac_reader_library_ini_path(folder: LocalFolder) -> Path | None:
    """Return the configured YACReaderLibrary INI path for a LocalFolder."""

    config_path = Path(folder.path, FOLDER_CONFIG_NAME)

    if not config_path.is_file():
        return None

    sub_path = configUtils.config_section_map(config_path, YAC_READER_SECTION, YAC_READER_INI_KEY)

    if sub_path is None:
        return None

    return Path(folder.path, sub_path.replace("\\", "/"))


def has_yac_reader_library(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder has YACReaderLibrary configuration."""

    return get_yac_reader_library_ini_path(folder) is not None


def get_yac_reader_library_prefs_path() -> Path | None:
    """Return the YACReaderLibrary preferences directory for the current platform."""

    user_home_dir = fileUtils.get_user_home_dir()

    match get_os():
        case OS.MAC:
            return Path(user_home_dir, 'Library', 'Application Support', 'YACReader', 'YACReaderLibrary')

        case OS.LINUX:
            return Path(user_home_dir, '.local', 'share', 'YACReader', 'YACReaderLibrary')

        case _:
            return None