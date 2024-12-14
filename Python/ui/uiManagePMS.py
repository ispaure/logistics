import wrappers.cmdShellWrapper as cmdShellWrapper
import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils.pySideUtils import *
import config
from pathlib import Path
import sys
import os
import commonUtils.fileUtils as fileUtils
import wrappers.uiShellWrapper as uiShellWrapper
from logisticsUtils import zipUtils


def get_remote_cls_pmsdata(remote_cls):
    """
    Get the remote class of the -PMSData of the current remote
    """
    return rcloneWrapper.get_remote_class(str(Path(config.LogisticsConfig().path_remote_network_mount, remote_cls.name + '-PMSDATA')))


def open_dir_remote_cls_pmsdata(remote_cls):
    """
    Opens the folder in explorer or finder of the current remote's -PMSDATA
    """
    fileUtils.open_dir_path(get_remote_cls_pmsdata(remote_cls).directory_path)


def open_dir_local_cls_pmsdata(remote_cls):
    """
    Opens the folder in explorer or finder of the current remote's -PMSDATA
    """
    fileUtils.open_dir_path(get_local_cls_pmsdata(remote_cls).directory_path)


def clear_local_pmsdata(remote_cls):
    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    if os.path.exists(local_cls_pmsdata.directory_path):
        # Wipe contents within -PMSDATA directory
        rem_dir_lst = fileUtils.get_dirs_path_list(local_cls_pmsdata.directory_path)
        for rem_dir in rem_dir_lst:
            fileUtils.delete_dir(rem_dir)
        rem_file_lst = fileUtils.get_file_path_list(local_cls_pmsdata.directory_path)
        for rem_file in rem_file_lst:
            fileUtils.delete_file(rem_file)


def get_local_cls_pmsdata(remote_cls):
    return rcloneWrapper.get_remote_class(str(Path(config.LogisticsConfig().path_remote_local, remote_cls.name + '-PMSDATA')))


def pull_pms(remote_cls):
    remote_cls_pmsdata = get_remote_cls_pmsdata(remote_cls)  # Get remote class for the -PMSDATA

    source_path = remote_cls_pmsdata.name + ':'
    destination_path = str(Path(config.LogisticsConfig().path_remote_local, remote_cls_pmsdata.name))

    rcloneWrapper.rclone_sync(source_path, destination_path)


def push_pms(remote_cls):
    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    source_path = local_cls_pmsdata.directory_path
    destination_path = local_cls_pmsdata.name + ':'

    rcloneWrapper.rclone_sync(source_path, destination_path)


def unpackage_pms(remote_cls):

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    # If folder to unpackage not there, cancel proceeding
    if not os.path.exists(local_cls_pmsdata.directory_path):
        return False

    # Make Plex Media Server directory in Location Used By Software (if it doesn't exist yet)
    pms_data_path = config.LogisticsConfig().pms_data_path
    if not os.path.exists(pms_data_path):
        Path(pms_data_path).mkdir(parents=True, exist_ok=True)

    if sys.platform == 'win32':
        # Determine archive path
        seven_zip_archive_path = str(Path(local_cls_pmsdata.directory_path, 'pms_data.7z.001'))

        # Make sure archive file exists, else throw error
        if not os.path.exists(seven_zip_archive_path):
            msg = 'The 7z file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
            uiShellWrapper.show_dialog_box('Unpackage Plex Media Server', msg)
            return False

        # Find registry file, else throws warning
        pms_reg_file_path = str(Path(local_cls_pmsdata.directory_path, 'pms_registry.reg'))

        if not os.path.exists(pms_reg_file_path):
            # Display Error Message
            msg = 'The registry file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
            msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to ' \
                   'be manually configured. Press OK to proceed or Cancel to Cancel'
            result = uiShellWrapper.show_dialog_box('Unpackage Plex Media Server', msg)

            # If user decides to cancel
            if not result:
                return False

            # If user continues
            command = ''
        else:
            # Could find registry file, so add it to registry.
            command = 'reg import "{}"'.format(pms_reg_file_path)

        # Extract archive contents to Local AppData, using 7-zip. In terminal window so that we can visualize as
        # this can take long. Also adds proper things to registry
        # Create 7z extract part in command
        seven_zip_exec_path = str(Path(config.LogisticsConfig().path_logistics, 'Software', '7-zip', '7z'))
        command += '\n"{sz_path}" x -y "{sz_archive_path}" -o"{pms_data_path}"'.format(sz_path=seven_zip_exec_path,
                                                                                       sz_archive_path=seven_zip_archive_path,
                                                                                       pms_data_path=pms_data_path)

        # Wipe contents within Plex Media Server Data in Local AppData before extraction
        fileUtils.delete_dir_contents(pms_data_path)

        # Put command in file and run
        cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)
    else:
        # Determine archive path
        zip_archive_path = str(Path(local_cls_pmsdata.directory_path, 'pms_data_mac.zip'))

        # Make sure archive file exists, else throw error
        if not os.path.exists(zip_archive_path):
            msg = 'The zip file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
            uiShellWrapper.show_dialog_box('Unpackage Plex Media Server', msg)
            return False

        # Find plist file, else throws warning
        pms_plist_file_path = str(Path(local_cls_pmsdata.directory_path, 'com.plexapp.plexmediaserver.plist'))

        if not os.path.exists(pms_plist_file_path):
            # Display Error Message
            msg = 'The plist file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
            msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to ' \
                   'be manually configured. Press OK to proceed or Cancel to Cancel'
            result = uiShellWrapper.show_dialog_box('Unpackage Plex Media Server', msg)
            if not result:
                return False
        else:
            # Copy plist file to proper location
            plist_destination_path = str(Path(os.environ['HOME'], 'Library', 'Preferences', 'com.plexapp.plexmediaserver.plist'))
            fileUtils.copy_file(pms_plist_file_path, plist_destination_path)

        # Wipe contents within Plex Media Server Data in Local AppData
        fileUtils.delete_dir_contents(pms_data_path)

        # Extract archive contents to User's Application Support, using <name of software>.
        print('Extracting PMSDATA archive to Application Support... Please wait!')
        zipUtils.unzip_file(zip_archive_path, pms_data_path[0:-len(pms_data_path.split('/')[-1])])
        print('Files extracted! Finished')


def package_pms(remote_cls):

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    # If AppData plex media server folder unreachable, cancel proceeding
    if not os.path.exists(config.LogisticsConfig().pms_data_path):
        msg = 'Cannot backup the Plex Media Server because directory path is invalid. Aborting!'
        uiShellWrapper.show_dialog_box('Package Plex Media Server', msg)
        return False

    # Create local -PMSDATA directory (if it doesn't exist yet)
    if not os.path.exists(local_cls_pmsdata.directory_path):
        Path(local_cls_pmsdata.directory_path).mkdir(parents=True, exist_ok=True)

    # Fetch information from registry and store in registry file
    # Compress (in file chunks) the Plex Media Server Directory contents in Local AppData

    if sys.platform == 'win32':
        # Wipe (some) contents within -PMSDATA directory; registry file and archive
        file_lst = fileUtils.get_file_path_list(local_cls_pmsdata.directory_path)
        for file in file_lst:
            if 'pms_data.' in file.split('\\')[-1] or '.reg' in file.split('\\')[-1]:
                fileUtils.delete_file(file)
        # Create command
        plex_registry_loc = 'HKEY_CURRENT_USER\\Software\\Plex, Inc.\\Plex Media Server'
        plex_registry_path = str(Path(local_cls_pmsdata.directory_path, 'pms_registry.reg'))
        seven_zip_exec_path = str(Path(config.LogisticsConfig().path_logistics, 'Software', '7-zip', '7z'))
        seven_zip_archive_path = str(Path(local_cls_pmsdata.directory_path, 'pms_data.7z'))
        command = 'reg export "{}" "{}"'.format(plex_registry_loc, plex_registry_path)
        command += '\n"{}" a -y -mx1 -v5000000000 "{}"'.format(seven_zip_exec_path, seven_zip_archive_path)
        # Get list of folders to include in 7z. Then add to end of last line
        dir_lst = fileUtils.get_dirs_path_list(config.LogisticsConfig().pms_data_path)
        for directory in dir_lst:
            command += ' "' + directory + '"'

        # Put command in file and run
        cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)
    else:
        # Wipe (some) contents within -PMSDATA directory; registry file and archive
        file_lst = fileUtils.get_file_path_list(local_cls_pmsdata.directory_path)
        for file in file_lst:
            if 'pms_data_mac.' in file.split('\\')[-1]:
                fileUtils.delete_file(file)
            elif '.plist' in file.split('\\')[-1]:
                fileUtils.delete_file(file)

        # Copy plist file to -PMSDATA
        plist_source_path = str(Path(os.environ['HOME'], 'Library', 'Preferences', 'com.plexapp.plexmediaserver.plist'))
        plist_dest_path = str(Path(local_cls_pmsdata.directory_path, 'com.plexapp.plexmediaserver.plist'))
        fileUtils.copy_file(plist_source_path, plist_dest_path)

        # Compress to zip
        zip_archive_path = str(Path(local_cls_pmsdata.directory_path, 'pms_data_mac.zip'))
        pms_data_path = config.LogisticsConfig().pms_data_path
        print('Compressing Plex Media Server to archive...')  # TODO: Make it work on macOS (archive file)
        zipUtils.zip_file(pms_data_path, zip_archive_path)
        print('Completed process!')


class ManagePMS(Window):
    def __init__(self, remote_cls):
        super().__init__('Manage PMS [{}]'.format(remote_cls.name))

        # Set dimensions
        self.width = 500
        self.height = 250

        # CREATE UI ELEMENTS FOR PMSDATA CONFIG WINDOW -----------------------------------------------------------------

        if sys.platform == 'win32':
            os_pref_folder_name = 'AppData'
        else:
            os_pref_folder_name = 'Application Support'

        if remote_cls.type == 'Local':

            # Open PMSData (Local) button
            button('Open Local -PMSDATA', self.dlg, QRect(0, 3, 200, 30), open_dir_local_cls_pmsdata, remote_cls)

            # Clear LocalPMS button
            button('Clear Local -PMSDATA', self.dlg, QRect(300, 3, 200, 30), clear_local_pmsdata, remote_cls)

            # Label: Restore PLEX Media Server Data from Cloud
            Label('Restore PLEX Media Server Data from Cloud:', self.dlg, QRect(10, 43, 400, 20))

            # Buttons
            button('1. Pull {}-PMSDATA from Remote to Local'.format(remote_cls.name), self.dlg, QRect(0, 65, 500, 30), pull_pms, remote_cls)
            button('2. Unpackage Local {}-PMSDATA to {} PMS'.format(remote_cls.name, os_pref_folder_name), self.dlg, QRect(0, 95, 500, 30), unpackage_pms, remote_cls)

            # Label: Restore PLEX Media Server Data from Cloud
            Label('Backup PLEX Media Server Data to Cloud:', self.dlg, QRect(10, 150, 400, 20))
            # Buttons
            button('1. Package {} PMS to Local {}-PMSDATA'.format(os_pref_folder_name, remote_cls.name), self.dlg, QRect(0, 172, 500, 30), package_pms, remote_cls)
            button('2. PUSH {}-PMSDATA from Local to Remote'.format(remote_cls.name), self.dlg, QRect(0, 202, 500, 30), push_pms, remote_cls)

        elif remote_cls.type == 'Remote':
            # Open PMSData (Remote) button
            button('Open Remote -PMSDATA', self.dlg, QRect(0, 3, 200, 30), open_dir_remote_cls_pmsdata, remote_cls)

        # --------------------------------------------------------------------------------------------------------------
