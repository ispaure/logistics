"""
Actions for the Logistics Comics feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
from pathlib import Path

import config

from commonUtils import dirUtils, fileUtils, linkUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.wrappers import cmdShellWrapper

from features.comics import detection
from models.local_folder import LocalFolder


# ----------------------------------------------------------------------------------------------------------------------
# COMICRACK ACTIONS

def open_comic_rack(folder: LocalFolder) -> bool:
    """Configure and open ComicRack for a LocalFolder."""

    comic_rack_local = detection.get_comic_rack_local_path(folder)
    comic_rack_roaming = detection.get_comic_rack_roaming_path(folder)

    if comic_rack_local is None or comic_rack_roaming is None:
        return False

    cyo_appdata_local_dir_path = Path(os.environ['USERPROFILE'], 'AppData', 'Local', 'cYo')
    cyo_appdata_roaming_dir_path = Path(os.environ['USERPROFILE'], 'AppData', 'Roaming', 'cYo')

    linkUtils.update_symbolic_link(comic_rack_local, cyo_appdata_local_dir_path)
    linkUtils.update_symbolic_link(comic_rack_roaming, cyo_appdata_roaming_dir_path)

    exec_path = Path(config.LogisticsConfig().path_logistics_software_win, 'ComicRack', 'ComicRack.exe')
    cmdShellWrapper.exec_cmd(f'start "" "{exec_path}"', wait_for_output=False)

    return True


# ----------------------------------------------------------------------------------------------------------------------
# YACREADER ACTIONS

def open_yac_reader_library(folder: LocalFolder) -> bool:
    """Configure and open YACReaderLibrary for a LocalFolder."""

    yac_reader_library_ini = detection.get_yac_reader_library_ini_path(folder)

    if yac_reader_library_ini is None:
        return False

    # If YACReader not installed, unzip in /Applications
    install_path = Path('/Applications', 'YACReader.app')
    if not install_path.exists():
        zip_path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReader.app.zip')
        fileUtils.unzip_file(zip_path, install_path)

    # If YACReaderLibrary not installed, unzip in /Applications
    install_path = Path('/Applications', 'YACReaderLibrary.app')
    if not install_path.exists():
        zip_path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReaderLibrary.app.zip')
        fileUtils.unzip_file(zip_path, install_path)

    yac_prefs_dir_path = detection.get_yac_reader_library_prefs_path()

    if yac_prefs_dir_path is None:
        log(
            Severity.CRITICAL,
            'open_yac_reader_library',
            'YACReaderLibrary preferences directory is not configured for this platform'
        )
        return False

    yac_prefs_dir = dirUtils.Directory(yac_prefs_dir_path)
    yac_prefs_dir.make_dir()

    fileUtils.copy_file(yac_reader_library_ini, Path(yac_prefs_dir_path, 'YACReaderLibrary.ini'))

    exec_path = Path('/Applications', 'YACReaderLibrary.app', 'Contents', 'MacOS', 'YACReaderLibrary')
    cmdShellWrapper.exec_cmd(str(exec_path), wait_for_output=False)

    return True
