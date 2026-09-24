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
from features.rclone import configuration, credentials, mounts

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
    match get_os():
        case OS.WIN:
            return Path(config.LogisticsConfig().path_logistics_software_win, 'rclone-2026', 'rclone.exe')
        case OS.MAC:
            return Path(config.LogisticsConfig().path_logistics_software_mac, 'rclone', 'rclone')
        case OS.LINUX:
            match get_arch():
                case Arch.X86_64:
                    return Path(config.LogisticsConfig().path_logistics_software_linux, 'rclone-v1.73.0-linux-amd64', 'rclone')
                case Arch.ARM_64:
                    return Path(config.LogisticsConfig().path_logistics_software_linux, 'rclone-v1.73.1-linux-arm64', 'rclone')


def get_all_remote_class():
    remote_cls_lst = []

    path_remote_local = config.LogisticsConfig().path_remote_local
    if not os.path.exists(path_remote_local):
        os.makedirs(path_remote_local)

    local_remote_directory = dirUtils.Directory(path_remote_local)
    dir_lst: List[dirUtils.Directory] = local_remote_directory.list_directories()
    for directory in dir_lst:
        remote_cls_lst.append(get_remote_class(directory.path))

    path_remote_network = config.LogisticsConfig().path_remote_network_mount
    if not os.path.exists(path_remote_network):
        os.makedirs(path_remote_network)

    mount_path_lst = get_rclone_remote_mount_paths()
    mount_path_lst.sort()
    for mount_path in mount_path_lst:
        remote_cls_lst.append(get_remote_class(mount_path))

    return remote_cls_lst


def rclone_sync(source_path: Union[str, Path], destination_path: Union[str, Path], query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None):
    source_path_str = str(source_path)
    destination_path_str = str(destination_path)

    baseline = '"{rclone_path}"'.format(rclone_path=get_rclone_path())
    baseline += ' sync --progress --copy-links '

    if track_renames:
        baseline += '--track-renames '

    if '-VM' in source_path_str:
        baseline += '--transfers=1 '
    else:
        baseline += '--transfers=10 '

    if bw_limit is not None:
        baseline += '--bwlimit {}M '.format(bw_limit)

    if dry_run:
        baseline += '--dry-run '

    baseline += f'"{source_path_str}" "{destination_path_str}"'

    if not os.path.exists(destination_path):
        match get_os():
            case OS.WIN:
                if destination_path_str[1] == ':':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

            case OS.MAC | OS.LINUX:
                if destination_path_str[0] == '/':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query:
        output_lines = cmdShellWrapper.exec_cmd(baseline, wait_for_output=True)
        query_dict = rclone_sync_process_query(source_path_str, destination_path_str, output_lines)
        return query_dict

    cmdShellWrapper.exec_cmd(baseline, wait_for_output=wait_for_output, in_new_window=True)
    return None


def rclone_sync_process_query(source_path: Union[str, Path], destination_path: Union[str, Path], output_lines):
    """
    Method used internally to process the output lines in something that actually means something.
    This is intended to analyze output lines from a rclone sync with --dry-run as one of the arguments!
    """
    source_path_str = str(source_path)
    destination_path_str = str(destination_path)

    query_dict = {}
    copy_lst = []

    for output_line in output_lines:
        if 'Skipped copy as --dry-run is set' in output_line:

            notice_loc = output_line.find('NOTICE: ')
            file_path_begin_loc = notice_loc + len('NOTICE: ')
            file_path_end_loc = output_line[file_path_begin_loc:].find(':')
            file_path_to_copy = output_line[file_path_begin_loc:file_path_begin_loc + file_path_end_loc]

            match get_os():
                case OS.WIN:
                    if source_path_str[1] == ':':
                        file_path_source = str(Path(source_path_str, file_path_to_copy))
                    else:
                        file_path_source = source_path_str + file_path_to_copy.replace('\\', '/')

                    if destination_path_str[1] == ':':
                        file_path_destination = str(Path(destination_path_str, file_path_to_copy))
                    else:
                        file_path_destination = destination_path_str + file_path_to_copy.replace('\\', '/')

                case OS.MAC:
                    if source_path_str[0] == '/':
                        file_path_source = str(Path(source_path_str, file_path_to_copy))
                    else:
                        file_path_source = source_path_str + file_path_to_copy

                    if destination_path_str[0] == '/':
                        file_path_destination = str(Path(destination_path_str, file_path_to_copy))
                    else:
                        file_path_destination = destination_path_str + file_path_to_copy

            copy_lst.append([file_path_source, file_path_destination])

    query_dict['COPY'] = copy_lst

    return query_dict