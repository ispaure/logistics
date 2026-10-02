"""
Actions for the Logistics Comics feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
from pathlib import Path
from typing import List

import config

from commonUtils import dirUtils, fileUtils, linkUtils, zipUtils
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

    install_path = Path('/Applications', 'YACReader.app')
    if not install_path.exists():
        zip_path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReader.app.zip')
        if not zipUtils.unzip_file(zip_path, install_path):
            return False

    install_path = Path('/Applications', 'YACReaderLibrary.app')
    if not install_path.exists():
        zip_path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReaderLibrary.app.zip')
        if not zipUtils.unzip_file(zip_path, install_path):
            return False

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

    if not fileUtils.copy_file(yac_reader_library_ini, Path(yac_prefs_dir_path, 'YACReaderLibrary.ini')):
        return False

    exec_path = Path('/Applications', 'YACReaderLibrary.app', 'Contents', 'MacOS', 'YACReaderLibrary')
    cmdShellWrapper.exec_cmd(str(exec_path), wait_for_output=False)

    return True


# ----------------------------------------------------------------------------------------------------------------------
# CBZ ACTIONS

def move_cbz_to_individual_folders(target_dir) -> bool:
    """
    Put each top-level CBZ file in a folder with the same name as the CBZ.

    Useful for one-shots in Komga.
    """

    tool_name = 'Move CBZ to Individual Folders'
    log(
        Severity.INFO,
        tool_name,
        'Starting the batch creation of individual folders and moving each .CBZ file into its new folder.'
    )

    batch_target_folder = dirUtils.Directory(Path(target_dir))
    log(Severity.INFO, tool_name, f'Target Folder: "{batch_target_folder.path}"')

    file_lst: List[fileUtils.File] = batch_target_folder.list_files(
        recursive=False,
        filter_extension='cbz'
    )

    if not file_lst:
        log(Severity.WARNING, tool_name, 'Did not find a .CBZ file.')
        return False

    log(Severity.INFO, tool_name, f'Found {len(file_lst)} files to put in new folders:')
    for file in file_lst:
        log(Severity.INFO, tool_name, f' - "{file.path}"')

    for file in file_lst:
        dir_path = file.path.parent / file.name_without_ext
        new_path = dir_path / file.file_name

        log(Severity.INFO, tool_name, f'Make new directory: "{dir_path}"')
        log(Severity.INFO, tool_name, f'Move file to new location: "{new_path}"')

        if new_path.exists() or new_path.is_symlink():
            log(Severity.ERROR, tool_name, f'Destination already exists: "{new_path}". Original kept.')
            return False
        fileUtils.make_dir(dir_path)

        if not fileUtils.copy_file(file.path, new_path):
            log(Severity.ERROR, tool_name, f'Failed to copy "{file.path}". The original was not deleted.')
            return False

        if not file.delete_file():
            log(
                Severity.ERROR,
                tool_name,
                f'Copied "{file.path}" successfully, but failed to delete the original file.'
            )
            return False

    log(Severity.INFO, tool_name, 'Finished moving all .CBZ files into individual folders.')
    return True
