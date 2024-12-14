
import commonUtils.fileUtils as fileUtils
import config as config
from pathlib import Path
import sys
import os
from commonUtils.debugUtils import print_debug_msg as print_debug_msg
import wrappers.cmdShellWrapper as cmdShellWrapper
import time
import wrappers.uiShellWrapper as uiShellWrapper
import random
from logisticsUtils import zipUtils

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
    fileUtils.delete_file(get_rclone_conf_path())


def get_rclone_conf_path():
    """Returns path to the user's rclone configuration file. If it doesn't exist, a blank one is created"""
    if sys.platform == 'win32':
        rclone_conf_dir = str(Path(os.environ['USERPROFILE'], '.config', 'rclone'))
    else:
        rclone_conf_dir = str(Path(os.environ['HOME'], '.config', 'rclone'))

    if not os.path.exists(rclone_conf_dir):
        os.makedirs(rclone_conf_dir)

    rclone_conf_file_pth = str(Path(rclone_conf_dir, 'rclone.conf'))
    if not os.path.exists(rclone_conf_file_pth):
        open(rclone_conf_file_pth, 'a').close()

    return rclone_conf_file_pth


def get_remote_credentials_dict(remote_credentials_dir):
    """
    Gets a dict of the remote credentials available in Server/Logistics/RemoteCredentials
    """

    # Get a list of files in directory
    file_lst = fileUtils.get_file_path_list(remote_credentials_dir)

    file_lst_filtered_txt = []
    filtered_ext = '.txt'
    for file in file_lst:
        if file[-len(filtered_ext):] == filtered_ext:
            file_lst_filtered_txt.append(file)

    remote_credentials_dict = {}
    for file in file_lst_filtered_txt:
        file_line_lst = fileUtils.read_file(file)
        remote_name = file_line_lst[0][1:-1]
        remote_credentials_dict[remote_name] = file_line_lst

    return remote_credentials_dict


def get_logistics_remote_credentials_zip_lst():
    """
    Gets a list of the paths to the remote credentials zip files available in Server/Logistics/RemoteCredentials
    """
    logistics_cfg = config.LogisticsConfig()

    # Get a list of files in directory
    remote_credentials_dir = str(Path(logistics_cfg.path_logistics, 'RemoteCredentials'))
    file_lst = fileUtils.get_file_path_list(remote_credentials_dir)

    file_lst_filtered_txt = []
    filtered_ext = '.zip'
    for file in file_lst:
        if file[-len(filtered_ext):] == filtered_ext:
            file_lst_filtered_txt.append(file)

    return file_lst_filtered_txt


def get_rclone_conf_remote_credentials_dict():
    """
    Gets a dict of the remote credentials available in rclone.conf of current user
    """
    def wrap_up_entry(current_entry_line_lst, rclone_credentials_dict):
        rclone_credentials_dict[current_entry_line_lst[0][1:-1]] = current_entry_line_lst
        return rclone_credentials_dict

    rclone_conf = get_rclone_conf_path()

    # Read file
    rclone_conf_line_lst = fileUtils.read_file(rclone_conf)

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
    remote_credentials_dir = str(Path(logistics_cfg.path_logistics, 'RemoteCredentials'))
    add_remote_to_rclone_conf(remote_credentials_dir)


def add_remote_to_rclone_conf(remote_credentials_dir):
    """
    Adds the remotes found in the logistics folder to the rclone conf (if they are missing from there)
    """
    rclone_conf_path = get_rclone_conf_path()
    rclone_remote_credential_dict = get_rclone_conf_remote_credentials_dict()
    logistics_remote_credential_dict = get_remote_credentials_dict(remote_credentials_dir)

    for key, value in logistics_remote_credential_dict.items():
        if key not in rclone_remote_credential_dict.keys():  # If the key is not there, need to add the list of lines
            fileUtils.append_line_lst_to_file(logistics_remote_credential_dict[key], rclone_conf_path)
            # Add a blank line
            fileUtils.append_line_lst_to_file([''], rclone_conf_path)


def add_remote_from_zip_to_rclone_conf(zip_path, zip_pw):

    # Figure out extraction directory
    logistics_cfg = config.LogisticsConfig()
    extract_dir = str(Path(logistics_cfg.path_logistics, 'RemoteCredentials', 'Unpack'))

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

    # Determine Command Line for Mount...
    if sys.platform == 'win32':
        rclone_exec_pth = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone', 'rclone'))
    else:
        rclone_exec_pth = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone_macos', 'rclone'))

    # Create mount command
    mount_cmd = rclone_exec_pth + ' mount '

    if timeout is not None:
        mount_cmd += '--attr-timeout={}s '.format(timeout)

    mount_cmd += '{remote_name}: {mount_path}'.format(remote_name=remote_name, mount_path=mount_path)

    # If on MacOS, mount path must exist before it can be mounted!
    if sys.platform != 'win32':
        if not os.path.exists(mount_path):
            os.makedirs(mount_path)

    # Execute commands
    cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False, in_new_window=False)

    # Wait a little bit
    time.sleep(0.125)
    # If didn't mount, try to mount a 2nd time
    if not os.path.exists(mount_path):
        cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False, in_new_window=False)
        time.sleep(0.25)
        if not os.path.exists(mount_path):
            cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False, in_new_window=False)

    # Debug Message (After Mount)
    print_debug_msg('Successfully mounted!', show_verbose)


def mount_all_rclone_conf_remotes(timeout=None):
    """
    Mounts all rclone.conf remotes on disk
    """
    # Get mount path
    network_remote_mount_path = config.LogisticsConfig().path_remote_network_mount

    # Create mount path if it doesn't exist yet
    if not os.path.exists(network_remote_mount_path):
        os.makedirs(network_remote_mount_path)

    # Get rclone conf remote dictionary
    rclone_conf_remote_credential_dict = get_rclone_conf_remote_credentials_dict()

    # List of mounted paths
    mount_path_lst = []

    for key in rclone_conf_remote_credential_dict.keys():
        if 'Dropbox' not in key:
            mount_path = str(Path(network_remote_mount_path, key))
            mount_remote(key, mount_path, timeout)
            mount_path_lst.append(mount_path)

    # Wait until all paths have been mounted before proceeding
    max_wait = 10
    current_wait = 0
    while not check_path_valid_lst(mount_path_lst):
        if current_wait < max_wait:
            current_wait += 0.08
            time.sleep(0.08)
        else:
            break


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
    if sys.platform == 'win32':
        return str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone', 'rclone.exe'))
    else:
        return str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone_macos', 'rclone'))


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
    dir_lst = fileUtils.get_dirs_path_list(path_remote_network)
    dir_lst.sort()
    for directory in dir_lst:
        remote_cls_lst.append(get_remote_class(directory))

    return remote_cls_lst


def rclone_sync(source_path, destination_path, query=False, wait_for_output=False, dry_run=False, track_renames=False, bw_limit=None, exit_on_done=False):
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

    baseline += '"{source_path}" "{destination_path}"'.format(source_path=source_path,
                                                              destination_path=destination_path)

    if exit_on_done:
        if sys.platform == 'win32':
            baseline += '\nexit'
        else:
            return False
            # TODO: Add MacOS Version of This!

    # If directory doesn't exist on destination yet, might need to create it
    if not os.path.exists(destination_path):
        if sys.platform == 'win32':
            if destination_path[1] == ':':
                Path(destination_path).mkdir(parents=True, exist_ok=True)
        else:
            if destination_path[0] == '/':
                Path(destination_path).mkdir(parents=True, exist_ok=True)

    if query:
        output_lines = cmdShellWrapper.exec_cmd(baseline, wait_for_output=True, in_new_window=False)
        query_dict = rclone_sync_process_query(source_path, destination_path, output_lines)
        return query_dict
    else:
        cmdShellWrapper.exec_cmd(baseline, wait_for_output=wait_for_output, in_new_window=True)


def rclone_sync_ghetto(local_path, local_package_path, cloud_path, parallel_amt):
    """
    Copy local files which are not synced to Cloud to a package path (ideally an external storage) which can then
    be transported to another location for backup (ideal for uploading a large chunk of data when time is sparse).

    NOTE: This does not delete files on Cloud and might not work 100% so one should always run a regular sync after
    this is done to ensure there is nothing missing.

    :param local_path: Local path to compare to cloud path
    :type local_path: str
    :param local_package_path: Path where files that haven't been copied will be moved to
    :type local_package_path: str
    :param cloud_path: Path to remote in cloud to compare with local path
    :type cloud_path: str
    :param parallel_amt: Will define how many .bat files there will be in local_package_path (parallel uploads later)
    :type parallel_amt: Int
    """
    # Show important information
    print('Local Path to Package: ' + local_path)
    print('Local Package Path: ' + local_package_path)
    print('Parallel Operations Amount: ' + str(parallel_amt))

    # Run Sync Dryrun to get log of files not currently on Cloud
    print('Running Rclone Sync Dryrun (To see what is missing from Cloud)...')
    print('This can take a bit of time. Be patient!')
    query_data = rclone_sync(source_path=local_path, destination_path=cloud_path, query=True, dry_run=True)
    print('Done with Dryrun!')

    # Create destination folder (if missing)
    if not os.path.exists(local_package_path):
        print('Creating destination folder...')
        Path(local_package_path).mkdir(parents=True, exist_ok=True)
    else:
        print('Detected existing destination folder!')

    # Get existing software folders
    rclone_dir_win32 = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone'))
    rclone_dir_macos = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'rclone_macos'))
    # Get expected rclone folders for destination package (will be used to run rclone from other machine)
    rclone_dir_win32_copy = str(Path(local_package_path, 'rclone'))
    rclone_dir_macos_copy = str(Path(local_package_path, 'rclone_macos'))
    # Copy files, regardless if they are there or not already
    fileUtils.copy_file(str(Path(rclone_dir_win32, 'git-log.txt')), str(Path(rclone_dir_win32_copy, 'git-log.txt')))
    fileUtils.copy_file(str(Path(rclone_dir_win32, 'rclone.1')), str(Path(rclone_dir_win32_copy, 'rclone.1')))
    fileUtils.copy_file(str(Path(rclone_dir_win32, 'rclone.exe')), str(Path(rclone_dir_win32_copy, 'rclone.exe')))
    fileUtils.copy_file(str(Path(rclone_dir_win32, 'README.html')), str(Path(rclone_dir_win32_copy, 'README.html')))
    fileUtils.copy_file(str(Path(rclone_dir_win32, 'README.txt')), str(Path(rclone_dir_win32_copy, 'README.txt')))
    fileUtils.copy_file(str(Path(rclone_dir_macos, 'git-log.txt')), str(Path(rclone_dir_macos_copy, 'git-log.txt')))
    fileUtils.copy_file(str(Path(rclone_dir_macos, 'rclone.1')), str(Path(rclone_dir_macos_copy, 'rclone.1')))
    fileUtils.copy_file(str(Path(rclone_dir_macos, 'rclone')), str(Path(rclone_dir_macos_copy, 'rclone')))
    fileUtils.copy_file(str(Path(rclone_dir_macos, 'README.html')), str(Path(rclone_dir_macos_copy, 'README.html')))
    fileUtils.copy_file(str(Path(rclone_dir_macos, 'README.txt')), str(Path(rclone_dir_macos_copy, 'README.txt')))

    # Get important variables
    if sys.platform == 'win32':
        script_file_path = str(Path(local_package_path, 'run_backup.bat'))
        rclone_exec_path = str(Path(local_package_path, 'rclone', 'rclone.exe'))
    else:
        script_file_path = str(Path(local_package_path, 'run_backup.command'))
        rclone_exec_path = str(Path(local_package_path, 'rclone_macos', 'rclone'))

    # If not created yet, create text file
    script_file_path_lst = []
    for value in range(parallel_amt):
        script_file_path_item = script_file_path.replace('run_backup', 'run_backup_' + str(value))
        script_file_path_lst.append(script_file_path_item)
        if not os.path.exists(script_file_path_item):
            fileUtils.write_file(script_file_path_item, '')

    # Process Files from List
    for file in query_data['COPY']:
        local_file_path = file[0]
        local_file_package_path = file[0].replace(local_path, local_package_path)
        remote_file_path = file[1]

        if sys.platform == 'win32':
            local_file_name = local_file_path.split('\\')[-1]
        else:
            local_file_name = local_file_path.split('/')[-1]
        remote_file_dir = remote_file_path[:-len(local_file_name)]
        local_file_package_path_dir_only = local_file_package_path[:-len(local_file_name)]
        if local_file_package_path_dir_only[-1] == '\\' or local_file_package_path_dir_only[-1] == '/':
            local_file_package_path_dir_only = local_file_package_path_dir_only[:-1]

        print('')
        print('Processing Local File Path: ' + local_file_path)
        print('Intended Local Package File Path: ' + local_file_package_path)
        print('Intended Future Cloud Destination Path: ' + remote_file_path)

        if not os.path.exists(local_file_package_path):
            print('Rclone sync file to package dir...')
            # fileUtils.copy_file(local_file_path, local_file_package_path)
            if not os.path.exists(local_file_package_path_dir_only):
                print('Creating directory: ' + local_file_package_path_dir_only)
                fileUtils.make_dir(local_file_package_path_dir_only)
            rclone_sync(local_file_path, local_file_package_path_dir_only, query=True)
            print('Rclone sync file succeeded!')
            print('Adding to script file...')
            rclone_command = '"{rclone_exec_path}" sync --progress "{source}" "{destination}"'.format(rclone_exec_path=rclone_exec_path, source=local_file_package_path, destination=remote_file_dir)
            try:
                fileUtils.write_file_append(random.choice(script_file_path_lst), rclone_command)
            except:
                print('Could not add to script file. Must be non-regular character in name')
                # TODO: Make it work for files with strange characters.
            print('Added to script file!')
        else:
            print('File already exists, bypassing copy...')

    # Show completed!
    print('Done Package Push to Cloud Procedure!')


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
            if sys.platform == 'win32':

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

            else:

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
