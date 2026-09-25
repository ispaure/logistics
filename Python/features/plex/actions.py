"""
Actions for the Logistics Plex feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

import os
from pathlib import Path
from typing import List

import config

from commonUtils import dirUtils, fileUtils, ui, zipUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from features.plex import folders as plex_folders
from features.rclone import sync as rclone_sync


# ----------------------------------------------------------------------------------------------------------------------
# FOLDER ACTIONS

def get_remote_cls_pmsdata(remote_cls):
    """Return the remote -PMSDATA folder associated with a Logistics folder."""

    return plex_folders.get_remote_pms_data_folder(remote_cls)


def get_local_cls_pmsdata(remote_cls):
    """Return the local -PMSDATA folder associated with a Logistics folder."""

    return plex_folders.get_local_pms_data_folder(remote_cls)


def open_dir_remote_cls_pmsdata(remote_cls):
    """Open the remote -PMSDATA folder."""

    get_remote_cls_pmsdata(remote_cls).open()


def open_dir_local_cls_pmsdata(remote_cls):
    """Open the local -PMSDATA folder."""

    get_local_cls_pmsdata(remote_cls).open()


def clear_local_pmsdata(remote_cls):
    """Delete the contents of the local -PMSDATA folder."""

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)

    if os.path.exists(local_cls_pmsdata.path):
        rem_dir_lst: List[dirUtils.Directory] = local_cls_pmsdata.list_directories()
        for rem_dir in rem_dir_lst:
            rem_dir.delete()

        rem_file_lst = local_cls_pmsdata.list_files()
        for file in rem_file_lst:
            file.delete_file()


# ----------------------------------------------------------------------------------------------------------------------
# SYNC ACTIONS

def pull_pms(remote_cls):
    """Pull the remote -PMSDATA folder to its local location."""

    remote_cls_pmsdata = get_remote_cls_pmsdata(remote_cls)

    source_path = remote_cls_pmsdata.name + ':'
    destination_path = Path(config.LogisticsConfig().path_remote_local, remote_cls_pmsdata.name)

    rclone_sync.rclone_sync(source_path, destination_path)


def push_pms(remote_cls):
    """Push the local -PMSDATA folder to its remote location."""

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)

    source_path = local_cls_pmsdata.path
    destination_path = local_cls_pmsdata.name + ':'

    rclone_sync.rclone_sync(source_path, destination_path)


# ----------------------------------------------------------------------------------------------------------------------
# PACKAGE ACTIONS

def unpackage_pms(remote_cls):
    """Restore Plex Media Server data from a local -PMSDATA package."""

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)

    if not os.path.exists(local_cls_pmsdata.path):
        return False

    pms_data_path = config.LogisticsConfig().pms_data_path
    if not os.path.exists(pms_data_path):
        pms_data_path.mkdir(parents=True, exist_ok=True)

    pms_data_directory = dirUtils.Directory(pms_data_path)

    match get_os():
        case OS.WIN:
            seven_zip_archive_path = Path(local_cls_pmsdata.path, 'pms_data.7z.001')

            if not os.path.exists(seven_zip_archive_path):
                msg = 'The 7z file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
                log(Severity.ERROR, 'Unpackage Plex Media Server', msg, popup=True)
                return False

            pms_reg_file_path = Path(local_cls_pmsdata.path, 'pms_registry.reg')

            if not os.path.exists(pms_reg_file_path):
                msg = 'The registry file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
                msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to '
                msg += 'be manually configured. Press OK to proceed or Cancel to Cancel'
                result = ui.display_msg_box_ok_cancel('Unpackage Plex Media Server', msg)

                if not result:
                    return False

                command = ''
            else:
                command = 'reg import "{}"'.format(pms_reg_file_path)

            seven_zip_exec_path = Path(config.LogisticsConfig().path_logistics_software_win, '7-zip', '7z')
            command += '\n"{sz_path}" x -y "{sz_archive_path}" -o"{pms_data_path}"'.format(
                sz_path=seven_zip_exec_path,
                sz_archive_path=seven_zip_archive_path,
                pms_data_path=pms_data_path
            )

            pms_data_directory.delete_contents()

            cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)

        case OS.MAC:
            zip_archive_path = Path(local_cls_pmsdata.path, 'pms_data_mac.zip')

            if not os.path.exists(zip_archive_path):
                msg = 'The zip file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
                log(Severity.ERROR, 'Unpackage Plex Media Server', msg, popup=True)
                return False

            pms_plist_file_path = Path(local_cls_pmsdata.path, 'com.plexapp.plexmediaserver.plist')

            if not os.path.exists(pms_plist_file_path):
                msg = 'The plist file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
                msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to '
                msg += 'be manually configured. Press OK to proceed or Cancel to Cancel'
                result = ui.display_msg_box_ok_cancel('Unpackage Plex Media Server', msg)

                if not result:
                    return False
            else:
                plist_destination_path = Path(os.environ['HOME'], 'Library', 'Preferences', 'com.plexapp.plexmediaserver.plist')
                fileUtils.copy_file(pms_plist_file_path, plist_destination_path)

            pms_data_directory.delete_contents()

            print('Extracting PMSDATA archive to Application Support... Please wait!')
            zipUtils.unzip_file(zip_archive_path, pms_data_path.parent)
            print('Files extracted! Finished')


def package_pms(remote_cls) -> bool:
    """Package the current Plex Media Server data into the local -PMSDATA folder."""

    tool_name = 'Package Plex Media Server'
    log(Severity.INFO, tool_name, 'Starting Plex Media Server packaging.')

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)
    pms_data_path = config.LogisticsConfig().pms_data_path
    pms_package_path = Path(local_cls_pmsdata.path)

    if not os.path.exists(pms_data_path):
        msg = f'Plex Media Server directory is invalid or unreachable: "{pms_data_path}". Aborting!'
        log(Severity.ERROR, tool_name, msg, popup=True)
        return False

    if not pms_package_path.exists():
        log(Severity.DEBUG, tool_name, f'Creating package directory: "{pms_package_path}"')
        pms_package_path.mkdir(parents=True, exist_ok=True)

    match get_os():
        case OS.WIN:
            log(Severity.DEBUG, tool_name, 'Packaging Windows Plex Media Server data.')

            file_lst = local_cls_pmsdata.list_files()
            for file in file_lst:
                if 'pms_data.' in file.file_name or file.ext == 'reg':
                    log(Severity.DEBUG, tool_name, f'Deleting previous package file: "{file.path}"')
                    file.delete_file()

            plex_registry_loc = 'HKEY_CURRENT_USER\\Software\\Plex, Inc.\\Plex Media Server'
            plex_registry_path = pms_package_path / 'pms_registry.reg'
            seven_zip_exec_path = Path(config.LogisticsConfig().path_logistics_software_win, '7-zip', '7z')
            seven_zip_archive_path = pms_package_path / 'pms_data.7z'

            command = 'reg export "{}" "{}"'.format(plex_registry_loc, plex_registry_path)
            command += '\n"{}" a -y -mx1 -v5000000000 "{}"'.format(seven_zip_exec_path, seven_zip_archive_path)

            pms_data_directory = dirUtils.Directory(pms_data_path)
            dir_lst: List[dirUtils.Directory] = pms_data_directory.list_directories()

            for directory in dir_lst:
                command += f' "{directory.path}"'

            log(Severity.INFO, tool_name, f'Creating Plex archive at "{seven_zip_archive_path}".')
            cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)

        case OS.MAC:
            log(Severity.DEBUG, tool_name, 'Packaging macOS Plex Media Server data.')

            file_lst = local_cls_pmsdata.list_files()

            for file in file_lst:
                if 'pms_data_mac.' in file.file_name or file.ext == 'plist':
                    log(Severity.DEBUG, tool_name, f'Deleting previous package file: "{file.path}"')
                    file.delete_file()

            plist_source_path = Path(os.environ['HOME'], 'Library', 'Preferences', 'com.plexapp.plexmediaserver.plist')
            plist_dest_path = pms_package_path / 'com.plexapp.plexmediaserver.plist'

            log(Severity.DEBUG, tool_name, f'Copying Plex preferences from "{plist_source_path}" to "{plist_dest_path}".')
            fileUtils.copy_file(plist_source_path, plist_dest_path)

            zip_archive_path = pms_package_path / 'pms_data_mac.zip'

            log(Severity.INFO, tool_name, f'Compressing Plex Media Server data to "{zip_archive_path}".')
            zipUtils.zip_file(pms_data_path, zip_archive_path)
            log(Severity.INFO, tool_name, 'Completed Plex Media Server packaging.')

    return True
