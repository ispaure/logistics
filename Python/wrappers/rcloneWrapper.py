
import commonUtils.fileUtils as fileUtils
from commonUtils.debugUtils import *
from commonUtils.osUtils import *
import config as config
from pathlib import Path
import sys
import os
from commonUtils.debugUtils import *
import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
import time
import wrappers.uiShellWrapper as uiShellWrapper
import random
from commonUtils import zipUtils
from typing import *

show_verbose = True


def clear_mounts():
    logistics_cfg = config.LogisticsConfig()
    # If mount folder exists, make sure there isn't anything left in it
    if os.path.exists(logistics_cfg.path_remote_network_mount):
        dir_lst = fileUtils.get_dirs_path_list(logistics_cfg.path_remote_network_mount)
        for directory in dir_lst:
            print('DELETE THIS: ' + directory)
            fileUtils.delete_symbolic_link(directory)


def clear_rclone_conf():
    """
    Deletes the local rclone.conf file, essentially clearing it.
    """
    fileUtils.File(get_rclone_conf_path()).delete_file()


def get_rclone_conf_path() -> Path:
    """Returns path to the user's rclone configuration file. If it doesn't exist, a blank one is created"""
    rclone_conf_dir = Path(fileUtils.get_user_home_dir(), '.config', 'rclone')

    if not os.path.exists(rclone_conf_dir):
        os.makedirs(rclone_conf_dir)

    rclone_conf_file_pth = Path(rclone_conf_dir, 'rclone.conf')
    if not rclone_conf_file_pth.is_file():
        open(str(rclone_conf_file_pth), 'a').close()

    return rclone_conf_file_pth


def get_remote_credentials_dict(remote_credentials_dir):
    """
    Gets a dict of the remote credentials available in
    Server/Logistics/RemoteCredentials.
    """
    file_lst = cast(
        List[fileUtils.TXTFile],
        fileUtils.get_file_list_from_path(
            remote_credentials_dir,
            filter_extension='txt',
        ),
    )

    remote_credentials_dict = {}
    for file in file_lst:
        file_line_lst = file.read_lines()
        remote_name = file_line_lst[0][1:-1]
        remote_credentials_dict[remote_name] = file_line_lst

    return remote_credentials_dict


def get_logistics_remote_credentials_zip_lst() -> List[fileUtils.File]:
    """
    Gets a list of remote credential ZIP files available in
    Server/Logistics/RemoteCredentials.
    """
    logistics_cfg = config.LogisticsConfig()
    return fileUtils.get_file_list_from_path(logistics_cfg.path_logistics_remote_cred, filter_extension='zip')


def get_rclone_conf_remote_credentials_dict():
    """
    Gets a dict of the remote credentials available in rclone.conf of current user
    """
    def wrap_up_entry(current_entry_line_lst, rclone_credentials_dict):
        rclone_credentials_dict[current_entry_line_lst[0][1:-1]] = current_entry_line_lst
        return rclone_credentials_dict

    rclone_conf: Path = get_rclone_conf_path()

    # Read file
    rclone_conf_file = fileUtils.TXTFile(rclone_conf)
    rclone_conf_file.read_lines()
    rclone_conf_line_lst = rclone_conf_file.line_lst

    rclone_credentials_dict = {}
    current_entry_line_lst = []
    for rclone_conf_line in rclone_conf_line_lst:
        if len(rclone_conf_line) > 0:
            if rclone_conf_line[0] == '[':

                # If there was something in current entry, add in dict
                if len(current_entry_line_lst) > 0:
                    rclone_credentials_dict = wrap_up_entry(current_entry_line_lst, rclone_credentials_dict)

                # Reset current entry by current line
                current_entry_line_lst = [rclone_conf_line]

            else:
                current_entry_line_lst.append(rclone_conf_line)

    # Wrap up remaining at end
    if len(current_entry_line_lst) > 0:
        rclone_credentials_dict = wrap_up_entry(current_entry_line_lst, rclone_credentials_dict)

    return rclone_credentials_dict


def add_logistics_remote_to_rclone_conf():
    logistics_cfg = config.LogisticsConfig()
    remote_credentials_dir = str(logistics_cfg.path_logistics_remote_cred)
    add_remote_to_rclone_conf(remote_credentials_dir)


def add_remote_to_rclone_conf(remote_credentials_dir):
    """
    Adds the remotes found in the logistics folder to the rclone conf (if they are missing from there)
    """
    rclone_conf_path = get_rclone_conf_path()
    rclone_remote_credential_dict = get_rclone_conf_remote_credentials_dict()
    logistics_remote_credential_dict = get_remote_credentials_dict(remote_credentials_dir)

    file_cls = fileUtils.TXTFile(rclone_conf_path)
    file_cls.read_lines()

    for key, value in logistics_remote_credential_dict.items():
        if key not in rclone_remote_credential_dict.keys():  # If the key is not there, need to add the list of lines

            file_cls.line_lst.extend(logistics_remote_credential_dict[key])
            file_cls.line_lst.append('')

    file_cls.write_lines()


def add_remote_from_zip_to_rclone_conf(zip_path, zip_pw):

    # Figure out extraction directory
    logistics_cfg = config.LogisticsConfig()
    extract_dir = str(Path(logistics_cfg.temp_path, 'UnpackCredentials'))

    # Extract archive
    try:
        zipUtils.unzip_file(zip_path, extract_dir, zip_pw)
    except:
        uiShellWrapper.show_dialog_box('Load Remote Credential', 'Password is invalid')
        return False

    # Load credentials
    add_remote_to_rclone_conf(extract_dir)

    # Delete files in extract dir now that they have been added to rclone
    fileUtils.delete_dir_contents(extract_dir)

    # Debug Done
    print_debug_msg('Successfully loaded remote credentials!', show_verbose)


def mount_remote(remote_name, mount_path, timeout=None):
    """
    Mounts a specific remote on disk
    """
    # Debug Message (Before Mount)
    print_debug_msg('Mounting "{}" at path "{}"...'.format(remote_name, mount_path), show_verbose)

    rclone_exec_pth = get_rclone_path()

    # Create mount command
    mount_cmd = f'"{rclone_exec_pth}"' + ' mount '

    if timeout is not None:
        mount_cmd += '--attr-timeout={}s '.format(timeout)

    mount_cmd += f'{remote_name}: {mount_path}'

    # If on macOS or Linux, mount path must exist before it can be mounted!
    match get_os():
        case OS.MAC | OS.LINUX:
            if not os.path.exists(mount_path):
                os.makedirs(mount_path, exist_ok=True)

    # Execute commands
    cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False)

    # Wait a little bit
    time.sleep(0.125)
    # If didn't mount, try to mount a 2nd time
    if not os.path.exists(mount_path):
        cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False)
        time.sleep(0.25)
        if not os.path.exists(mount_path):
            cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False)

    # Debug Message (After Mount)
    print_debug_msg('Successfully mounted!', show_verbose)


def mount_all_rclone_conf_remotes(timeout=None, wait_until_mounted=False):
    """
    Mounts all rclone.conf remotes on disk.

    Args:
        timeout: Timeout passed to mount_remote().
        wait_until_mounted: If True, wait indefinitely for all remotes to mount.
                            If False, proceed immediately after starting the mounts.
    """
    # Get mount path
    network_remote_mount_path = config.LogisticsConfig().path_remote_network_mount

    # Create mount path if it doesn't exist yet
    if not os.path.exists(network_remote_mount_path):
        log(Severity.INFO, 'mount_all_rclone_conf_remotes', f'Creating network mount directory: {network_remote_mount_path}')
        os.makedirs(network_remote_mount_path)

    # Get rclone conf remote dictionary
    rclone_conf_remote_credential_dict = get_rclone_conf_remote_credentials_dict()

    # List of mounted paths
    mount_path_lst = []

    for key in rclone_conf_remote_credential_dict.keys():
        if 'Dropbox' not in key and 'gdrive' not in key:
            mount_path = str(Path(network_remote_mount_path, key))

            log(Severity.INFO, 'mount_all_rclone_conf_remotes', f'Mounting remote: {key} -> {mount_path}')

            mount_remote(key, mount_path, timeout)
            mount_path_lst.append(mount_path)

    # No remotes were found to mount
    if not mount_path_lst:
        log(Severity.WARNING, 'mount_all_rclone_conf_remotes', 'No rclone remotes found to mount')
        return

    # Proceed immediately unless explicitly asked to wait
    if not wait_until_mounted:
        log(Severity.DEBUG, 'mount_all_rclone_conf_remotes', 'Mount commands started, proceeding without waiting')
        return

    # Wait indefinitely until all paths have been mounted
    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'Waiting for all rclone remotes to mount')

    while not check_path_valid_lst(mount_path_lst):
        time.sleep(0.05)

    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'All rclone remotes successfully mounted')


def check_path_valid_lst(path_lst):
    """
    Checks that all paths in list are valid and only returns true when all of them are
    """
    for path in path_lst:
        if not os.path.exists(path):
            return False
    return True


class Remote:
    """
    Stores the information of a remote
    """
    def __init__(self, remote_dir):
        # Get Basic Info
        self.name = remote_dir.split(fileUtils.get_split_character())[-1]
        self.directory_path = remote_dir

        # Determine if it's local or not
        if config.LogisticsConfig().path_remote_network_mount in self.directory_path:
            self.type = 'Remote'
        elif config.LogisticsConfig().path_remote_local in self.directory_path:
            self.type = 'Local'

        # Determine if is -PMSDATA
        pms_data_string = '-PMSDATA'
        if self.name[-len(pms_data_string):] == pms_data_string:
            self.is_pms_data = True
        else:
            self.is_pms_data = False

        # Attributing None in case can't assign
        self.comic_rack_local = None
        self.comic_rack_roaming = None
        self.calibre_lib_path = None
        self.yac_reader_library_ini = None
        self.youtube_dl_cfg_path = None
        self.youtube_dl_cfg_sub_path = None

        # Read Configuration File
        config_path_loc = str(Path(self.directory_path, 'remoteConfig.ini'))
        if self.type == 'Local':
            if os.path.exists(config_path_loc):

                # Comic Rack Local
                sub_path = config.config_section_map('ComicRack', 'appdata_local_cyo_sub_path', config_path_loc)
                if sub_path is not None:
                    self.comic_rack_local = str(Path(self.directory_path, sub_path))

                # Comic Rack Roaming
                sub_path = config.config_section_map('ComicRack', 'appdata_roaming_cyo_sub_path', config_path_loc)
                if sub_path is not None:
                    self.comic_rack_roaming = str(Path(self.directory_path, sub_path))

                # Calibre Library
                sub_path = config.config_section_map('Calibre', 'calibre_lib_sub_path', config_path_loc)
                if sub_path is not None:
                    self.calibre_lib_path = str(Path(self.directory_path, sub_path))

                # YAC Reader Library INI Location
                sub_path = config.config_section_map('YACReaderLibrary', 'yacreaderlibrary_ini_sub_path', config_path_loc)
                if sub_path is not None:
                    self.yac_reader_library_ini = str(Path(self.directory_path, sub_path.replace('\\', '/')))

                # Youtube Downloader
                sub_path = config.config_section_map('Youtube-Download', 'config_sub_path', config_path_loc)
                if sub_path is not None:
                    self.youtube_dl_cfg_path = str(Path(self.directory_path, sub_path.replace('\\', '/')))
                    self.youtube_dl_cfg_sub_path = sub_path


def get_remote_class(remote_dir):
    """
    Get a config class for the remote
    """
    return Remote(remote_dir)


def get_rclone_path():
    # Determine path of sync file
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

    # Get local remote classes
    path_remote_local = config.LogisticsConfig().path_remote_local
    if not os.path.exists(path_remote_local):
        os.makedirs(path_remote_local)

    dir_lst = fileUtils.get_dirs_path_list(path_remote_local)
    dir_lst.sort()
    for directory in dir_lst:
        remote_cls_lst.append(get_remote_class(directory))

    # Get network remote classes
    path_remote_network = config.LogisticsConfig().path_remote_network_mount
    if not os.path.exists(path_remote_network):
        os.makedirs(path_remote_network)

    dir_lst = fileUtils.get_dirs_path_list(path_remote_network)
    dir_lst.sort()
    for directory in dir_lst:
        remote_cls_lst.append(get_remote_class(directory))

    return remote_cls_lst


def rclone_sync(source_path, destination_path, query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None):
    # Determine Sync Command
    baseline = '"{rclone_path}"'.format(rclone_path=get_rclone_path())
    baseline += ' sync --progress --copy-links '
    if track_renames:
        baseline += '--track-renames '
    if '-VM' in source_path:
        baseline += '--transfers=1 '
    else:
        baseline += '--transfers=10 '
    if bw_limit is not None:
        baseline += '--bwlimit {}M '.format(bw_limit)
    if dry_run:
        baseline += '--dry-run '

    # Add max tps (else might say that Too many requests or write operations)
    # baseline += '--tpslimit 12 '

    baseline += f'"{source_path}" "{destination_path}"'

    # If directory doesn't exist on destination yet, might need to create it
    if not os.path.exists(destination_path):
        match get_os():
            case OS.WIN:
                if destination_path[1] == ':':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)
            case OS.MAC | OS.LINUX:
                if destination_path[0] == '/':
                    Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query:
        output_lines = cmdShellWrapper.exec_cmd(baseline, wait_for_output=True)
        query_dict = rclone_sync_process_query(source_path, destination_path, output_lines)
        return query_dict
    else:
        # cmdShellWrapper.exec_cmd(baseline, wait_for_output=wait_for_output, in_new_window=config.LogisticsConfig().temp_cmd)
        cmdShellWrapper.exec_cmd(baseline, wait_for_output=wait_for_output, in_new_window=True)
        return None


def rclone_sync_process_query(source_path, destination_path, output_lines):
    """
    Method used internally to process the output lines in something that actually means something.
    This is intended to analyze output lines from a rclone sync with --dry-run as one of the arguments!
    """
    # Create the query dict that will contain useful information
    query_dict = {}

    # Create list of copy that would have been attempted
    copy_lst = []

    for output_line in output_lines:

        # IF SKIPPED COPY
        if 'Skipped copy as --dry-run is set' in output_line:

            # DETERMINE RELATIVE FILE PATH
            notice_loc = output_line.find('NOTICE: ')
            file_path_begin_loc = notice_loc + len('NOTICE: ')
            file_path_end_loc = output_line[file_path_begin_loc:].find(':')
            file_path_to_copy = output_line[file_path_begin_loc:file_path_begin_loc + file_path_end_loc]

            # DETERMINE ABSOLUTE SOURCE PATH AND DESTINATION PATH
            match get_os():

                case OS.WIN:
                    # Determine File Path of Source
                    if source_path[1] == ':':  # Is a location on disk
                        file_path_source = str(Path(source_path, file_path_to_copy))
                    else:  # Is a rclone remote location
                        file_path_source = source_path + file_path_to_copy.replace('\\', '/')  # Rclone paths are always fwd

                    # Determine File Path of Destination
                    if destination_path[1] == ':':  # Is a location on disk
                        file_path_destination = str(Path(destination_path, file_path_to_copy))
                    else:  # Is a rclone remote location
                        file_path_destination = destination_path + file_path_to_copy.replace('\\', '/')  # Rclone paths are always fwd

                case OS.MAC:
                    # Determine File Path of Source
                    if source_path[0] == '/':  # Is a location on disk
                        file_path_source = str(Path(source_path, file_path_to_copy))
                    else:  # Is a rclone remote location
                        file_path_source = source_path + file_path_to_copy

                    # Determine File Path of Destination
                    if destination_path[0] == '/':  # Is a location on disk
                        file_path_destination = str(Path(destination_path, file_path_to_copy))
                    else:  # Is a rclone remote location
                        file_path_destination = destination_path + file_path_to_copy

            # ADD THE FINDINGS TO THE LIST
            copy_lst.append([file_path_source, file_path_destination])

    # Create keys for dict
    query_dict['COPY'] = copy_lst

    return query_dict
