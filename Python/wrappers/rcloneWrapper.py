# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------

from commonUtils import fileUtils, linkUtils
from commonUtils.osUtils import *
import config as config
from pathlib import Path
import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
import time
from commonUtils import ui
from commonUtils import zipUtils
from typing import *
from commonUtils.debugUtils import *
from commonUtils import dirUtils
from commonUtils import configUtils
from commonUtils.fileTypes import txtType
from features.rclone import configuration, credentials, executable, mounts, sync
from models import folder_discovery

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


class Remote(dirUtils.Directory):
    """
    Stores the information of a remote
    """
    def __init__(self, remote_dir: Union[str, Path]):
        super().__init__(Path(remote_dir))

        logistics_cfg = config.LogisticsConfig()

        if self.path.is_relative_to(logistics_cfg.path_remote_network_mount):
            self.type = 'Remote'
        elif self.path.is_relative_to(logistics_cfg.path_remote_local):
            self.type = 'Local'
        else:
            log(Severity.CRITICAL, 'Remote.__init__', f'Remote path is not within a valid remote directory: "{self.path}"')

        pms_data_string = '-PMSDATA'
        if self.name[-len(pms_data_string):] == pms_data_string:
            self.is_pms_data = True
        else:
            self.is_pms_data = False

        self.comic_rack_local = None
        self.comic_rack_roaming = None
        self.calibre_lib_path = None
        self.yac_reader_library_ini = None
        self.youtube_dl_cfg_path = None
        self.youtube_dl_cfg_sub_path = None
        self.perforce_p4d_path = None
        self.perforce_data_path = None
        self.perforce_port = None

        config_path_loc = str(Path(self.path, 'remoteConfig.ini'))
        if self.type == 'Local':
            if os.path.exists(config_path_loc):

                sub_path = configUtils.config_section_map(config_path_loc, 'ComicRack', 'appdata_local_cyo_sub_path')
                if sub_path is not None:
                    self.comic_rack_local = str(Path(self.path, sub_path))

                sub_path = configUtils.config_section_map(config_path_loc, 'ComicRack', 'appdata_roaming_cyo_sub_path')
                if sub_path is not None:
                    self.comic_rack_roaming = str(Path(self.path, sub_path))

                sub_path = configUtils.config_section_map(config_path_loc, 'Calibre', 'calibre_lib_sub_path')
                if sub_path is not None:
                    self.calibre_lib_path = str(Path(self.path, sub_path))

                sub_path = configUtils.config_section_map(config_path_loc, 'YACReaderLibrary', 'yacreaderlibrary_ini_sub_path')
                if sub_path is not None:
                    self.yac_reader_library_ini = str(Path(self.path, sub_path.replace('\\', '/')))

                sub_path = configUtils.config_section_map(config_path_loc, 'Youtube-Download', 'config_sub_path')
                if sub_path is not None:
                    self.youtube_dl_cfg_path = str(Path(self.path, sub_path.replace('\\', '/')))
                    self.youtube_dl_cfg_sub_path = sub_path

                p4d_path = configUtils.config_section_map(config_path_loc, 'Perforce', 'p4d_path')
                if p4d_path is not None:
                    self.perforce_p4d_path = p4d_path

                data_path = configUtils.config_section_map(config_path_loc, 'Perforce', 'data_path')
                if data_path is not None:
                    self.perforce_data_path = data_path

                port_path = configUtils.config_section_map(config_path_loc, 'Perforce', 'port')
                if port_path is not None:
                    self.perforce_port = port_path


def get_remote_class(remote_dir):
    """
    Get a config class for the remote
    """
    return Remote(remote_dir)


def get_rclone_path():
    return executable.get_rclone_path()


def get_all_remote_class():
    return folder_discovery.get_local_folders() + folder_discovery.get_remote_folders()


def rclone_sync(source_path: Union[str, Path], destination_path: Union[str, Path], query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None):
    return sync.rclone_sync(source_path, destination_path, query, wait_for_output, dry_run, track_renames, bw_limit)


def rclone_sync_process_query(source_path: Union[str, Path], destination_path: Union[str, Path], output_lines):
    return sync.rclone_sync_process_query(source_path, destination_path, output_lines)