# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from pathlib import Path
from typing import List, Union

import config

from commonUtils import dirUtils, fileUtils, ui, zipUtils
from commonUtils.debugUtils import print_debug_msg
from features.rclone import configuration, credentials, executable, mounts, sync


show_verbose = True


def clear_mounts():
    mounts.clear_mounts()


def clear_rclone_conf():
    """
    Deletes the local rclone.conf file, essentially clearing it.
    """
    fileUtils.File(get_rclone_conf_path()).delete_file()


def get_rclone_conf_path() -> Path:
    return configuration.get_rclone_conf_path()


def get_remote_credentials_dict(remote_credentials_dir):
    return credentials.get_remote_credentials_dict(remote_credentials_dir)


def get_logistics_remote_credentials_zip_lst() -> List[fileUtils.File]:
    return credentials.get_logistics_remote_credentials_zip_lst()


def get_rclone_conf_remote_credentials_dict():
    return configuration.get_rclone_conf_remote_credentials_dict()


def get_rclone_remote_mount_paths():
    return mounts.get_rclone_remote_mount_paths()


def add_logistics_remote_to_rclone_conf():
    credentials.add_logistics_remote_to_rclone_conf()


def add_remote_to_rclone_conf(remote_credentials_dir: Path):
    credentials.add_remote_to_rclone_conf(remote_credentials_dir)


def add_remote_from_zip_to_rclone_conf(zip_path, zip_pw):

    # Figure out extraction directory
    logistics_cfg = config.LogisticsConfig()
    extract_dir = Path(logistics_cfg.temp_path, 'UnpackCredentials')

    # Extract archive
    try:
        zipUtils.unzip_file(zip_path, extract_dir, zip_pw)
    except:
        ui.display_msg_box_ok('Load Remote Credential', 'Password is invalid')
        return False

    # Load credentials
    add_remote_to_rclone_conf(extract_dir)

    # Delete files in extract dir now that they have been added to rclone
    dirUtils.Directory(extract_dir).delete_contents()

    # Debug Done
    print_debug_msg('Successfully loaded remote credentials!', show_verbose)


def mount_remote(remote_name, mount_path, timeout=None):
    return mounts.mount_remote(remote_name, mount_path, timeout)


def mount_all_rclone_conf_remotes(timeout=None, wait_until_mounted=False):
    return mounts.mount_all_rclone_conf_remotes(timeout, wait_until_mounted)


def get_rclone_path():
    return executable.get_rclone_path()


def rclone_sync(source_path: Union[str, Path], destination_path: Union[str, Path], query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None):
    return sync.rclone_sync(source_path, destination_path, query, wait_for_output, dry_run, track_renames, bw_limit)


def rclone_sync_process_query(source_path: Union[str, Path], destination_path: Union[str, Path], output_lines):
    return sync.rclone_sync_process_query(source_path, destination_path, output_lines)