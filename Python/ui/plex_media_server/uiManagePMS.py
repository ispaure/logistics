import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
import wrappers.rcloneWrapper as rcloneWrapper
from commonUtils import ui
import config
from pathlib import Path
import commonUtils.fileUtils as fileUtils
from commonUtils import dirUtils, zipUtils
from commonUtils.osUtils import *
from commonUtils.debugUtils import *


def get_remote_cls_pmsdata(remote_cls):
    """
    Get the remote class of the -PMSData of the current remote
    """
    return rcloneWrapper.get_remote_class(
        Path(config.LogisticsConfig().path_remote_network_mount, remote_cls.name + '-PMSDATA')
    )


def open_dir_remote_cls_pmsdata(remote_cls):
    """
    Opens the folder in explorer or finder of the current remote's -PMSDATA
    """
    get_remote_cls_pmsdata(remote_cls).open()


def open_dir_local_cls_pmsdata(remote_cls):
    """
    Opens the folder in explorer or finder of the current remote's -PMSDATA
    """
    get_local_cls_pmsdata(remote_cls).open()


def clear_local_pmsdata(remote_cls):
    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    if os.path.exists(local_cls_pmsdata.path):
        # Wipe contents within -PMSDATA directory
        rem_dir_lst: List[dirUtils.Directory] = local_cls_pmsdata.list_directories()
        for rem_dir in rem_dir_lst:
            rem_dir.delete()
        rem_file_lst = local_cls_pmsdata.list_files()
        for file in rem_file_lst:
            file.delete_file()


def get_local_cls_pmsdata(remote_cls):
    return rcloneWrapper.get_remote_class(
        Path(config.LogisticsConfig().path_remote_local, remote_cls.name + '-PMSDATA')
    )


def pull_pms(remote_cls):
    remote_cls_pmsdata = get_remote_cls_pmsdata(remote_cls)  # Get remote class for the -PMSDATA

    source_path = remote_cls_pmsdata.name + ':'
    destination_path = Path(config.LogisticsConfig().path_remote_local, remote_cls_pmsdata.name)

    rcloneWrapper.rclone_sync(source_path, destination_path)


def push_pms(remote_cls):
    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    source_path = local_cls_pmsdata.path
    destination_path = local_cls_pmsdata.name + ':'

    rcloneWrapper.rclone_sync(source_path, destination_path)


def unpackage_pms(remote_cls):

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA

    # If folder to unpackage not there, cancel proceeding
    if not os.path.exists(local_cls_pmsdata.path):
        return False

    # Make Plex Media Server directory in Location Used By Software (if it doesn't exist yet)
    pms_data_path = config.LogisticsConfig().pms_data_path
    if not os.path.exists(pms_data_path):
        pms_data_path.mkdir(parents=True, exist_ok=True)

    pms_data_directory = dirUtils.Directory(pms_data_path)

    match get_os():
        case OS.WIN:
            # Determine archive path
            seven_zip_archive_path = Path(local_cls_pmsdata.path, 'pms_data.7z.001')

            # Make sure archive file exists, else throw error
            if not os.path.exists(seven_zip_archive_path):
                msg = 'The 7z file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
                log(Severity.ERROR, 'Unpackage Plex Media Server', msg, popup=True)
                return False

            # Find registry file, else throws warning
            pms_reg_file_path = Path(local_cls_pmsdata.path, 'pms_registry.reg')

            if not os.path.exists(pms_reg_file_path):
                # Display Error Message
                msg = 'The registry file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
                msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to ' \
                       'be manually configured. Press OK to proceed or Cancel to Cancel'
                result = ui.display_msg_box_ok_cancel('Unpackage Plex Media Server', msg)

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
            seven_zip_exec_path = Path(config.LogisticsConfig().path_logistics_software_win, '7-zip', '7z')
            command += '\n"{sz_path}" x -y "{sz_archive_path}" -o"{pms_data_path}"'.format(
                sz_path=seven_zip_exec_path,
                sz_archive_path=seven_zip_archive_path,
                pms_data_path=pms_data_path
            )

            # Wipe contents within Plex Media Server Data in Local AppData before extraction
            pms_data_directory.delete_contents()

            # Put command in file and run
            # cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=config.LogisticsConfig().temp_cmd)
            cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)

        case OS.MAC:
            # Determine archive path
            zip_archive_path = Path(local_cls_pmsdata.path, 'pms_data_mac.zip')

            # Make sure archive file exists, else throw error
            if not os.path.exists(zip_archive_path):
                msg = 'The zip file to extract cannot be found within {}. Aborting!'.format(local_cls_pmsdata.name)
                log(Severity.ERROR, 'Unpackage Plex Media Server', msg, popup=True)
                return False

            # Find plist file, else throws warning
            pms_plist_file_path = Path(local_cls_pmsdata.path, 'com.plexapp.plexmediaserver.plist')

            if not os.path.exists(pms_plist_file_path):
                # Display Error Message
                msg = 'The plist file to add cannot be found within {}.'.format(local_cls_pmsdata.name)
                msg += '\nThe Plex Media Server contents can still be extracted, but some server settings will need to ' \
                       'be manually configured. Press OK to proceed or Cancel to Cancel'
                result = ui.display_msg_box_ok_cancel('Unpackage Plex Media Server', msg)
                if not result:
                    return False
            else:
                # Copy plist file to proper location
                plist_destination_path = Path(
                    os.environ['HOME'], 'Library', 'Preferences', 'com.plexapp.plexmediaserver.plist'
                )
                fileUtils.copy_file(pms_plist_file_path, plist_destination_path)

            # Wipe contents within Plex Media Server Data in Local AppData
            pms_data_directory.delete_contents()

            # Extract archive contents to User's Application Support, using <name of software>.
            print('Extracting PMSDATA archive to Application Support... Please wait!')
            zipUtils.unzip_file(zip_archive_path, pms_data_path.parent)
            print('Files extracted! Finished')


def package_pms(remote_cls) -> bool:
    tool_name = 'Package Plex Media Server'
    log(Severity.INFO, tool_name, 'Starting Plex Media Server packaging.')

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)  # Get local class for the -PMSDATA
    pms_data_path = config.LogisticsConfig().pms_data_path
    pms_package_path = Path(local_cls_pmsdata.path)

    # If AppData plex media server folder unreachable, cancel proceeding
    if not os.path.exists(pms_data_path):
        msg = f'Plex Media Server directory is invalid or unreachable: "{pms_data_path}". Aborting!'
        log(Severity.ERROR, tool_name, msg, popup=True)
        return False

    # Create local -PMSDATA directory (if it doesn't exist yet)
    if not pms_package_path.exists():
        log(Severity.DEBUG, tool_name, f'Creating package directory: "{pms_package_path}"')
        pms_package_path.mkdir(parents=True, exist_ok=True)

    # Fetch information from registry and store in registry file
    # Compress (in file chunks) the Plex Media Server Directory contents in Local AppData

    match get_os():
        case OS.WIN:
            log(Severity.DEBUG, tool_name, 'Packaging Windows Plex Media Server data.')

            # Wipe (some) contents within -PMSDATA directory; registry file and archive
            file_lst = local_cls_pmsdata.list_files()
            for file in file_lst:
                if 'pms_data.' in file.file_name or file.ext == 'reg':
                    log(Severity.DEBUG, tool_name, f'Deleting previous package file: "{file.path}"')
                    file.delete_file()

            # Create command
            plex_registry_loc = 'HKEY_CURRENT_USER\\Software\\Plex, Inc.\\Plex Media Server'
            plex_registry_path = pms_package_path / 'pms_registry.reg'
            seven_zip_exec_path = Path(config.LogisticsConfig().path_logistics_software_win, '7-zip', '7z')
            seven_zip_archive_path = pms_package_path / 'pms_data.7z'

            command = 'reg export "{}" "{}"'.format(plex_registry_loc, plex_registry_path)
            command += '\n"{}" a -y -mx1 -v5000000000 "{}"'.format(seven_zip_exec_path, seven_zip_archive_path)

            # Get list of folders to include in 7z. Then add to end of last line
            pms_data_directory = dirUtils.Directory(pms_data_path)
            dir_lst: List[dirUtils.Directory] = pms_data_directory.list_directories()
            for directory in dir_lst:
                command += f' "{directory.path}"'

            log(Severity.INFO, tool_name, f'Creating Plex archive at "{seven_zip_archive_path}".')

            # Put command in file and run
            # cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=config.LogisticsConfig().temp_cmd)
            cmdShellWrapper.exec_cmd(command, wait_for_output=False, in_new_window=True)

        case OS.MAC:
            log(Severity.DEBUG, tool_name, 'Packaging macOS Plex Media Server data.')

            # Wipe (some) contents within -PMSDATA directory; plist file and archive
            file_lst = local_cls_pmsdata.list_files()
            for file in file_lst:
                if 'pms_data_mac.' in file.file_name or file.ext == 'plist':
                    log(Severity.DEBUG, tool_name, f'Deleting previous package file: "{file.path}"')
                    file.delete_file()

            # Copy plist file to -PMSDATA
            plist_source_path = Path(
                os.environ['HOME'],
                'Library',
                'Preferences',
                'com.plexapp.plexmediaserver.plist',
            )
            plist_dest_path = pms_package_path / 'com.plexapp.plexmediaserver.plist'

            log(Severity.DEBUG, tool_name, f'Copying Plex preferences from "{plist_source_path}" to "{plist_dest_path}".')
            fileUtils.copy_file(plist_source_path, plist_dest_path)

            # Compress to zip
            zip_archive_path = pms_package_path / 'pms_data_mac.zip'

            log(Severity.INFO, tool_name, f'Compressing Plex Media Server data to "{zip_archive_path}".')
            zipUtils.zip_file(pms_data_path, zip_archive_path)
            log(Severity.INFO, tool_name, 'Completed Plex Media Server packaging.')

    return True


class ManagePMS(ui.pyside.Window):
    def __init__(self, remote_cls):
        super().__init__('Manage PMS [{}]'.format(remote_cls.name))

        # Set dimensions
        self.width = 500
        self.height = 250

        # CREATE UI ELEMENTS FOR PMSDATA CONFIG WINDOW -----------------------------------------------------------------

        match get_os():
            case OS.WIN:
                os_pref_folder_name = 'AppData'
            case OS.MAC:
                os_pref_folder_name = 'Application Support'
            case _:
                log(Severity.CRITICAL, 'uiManagePMS', 'Unsupported Platform!')
                return

        match remote_cls.type:
            case 'Local':

                # Open PMSData (Local) button
                ui.pyside.button('Open Local -PMSDATA', self.dlg, ui.pyside.QRect(0, 3, 200, 30),
                                 open_dir_local_cls_pmsdata, remote_cls)

                # Clear LocalPMS button
                ui.pyside.button('Clear Local -PMSDATA', self.dlg, ui.pyside.QRect(300, 3, 200, 30),
                                 clear_local_pmsdata, remote_cls)

                # Label: Restore PLEX Media Server Data from Cloud
                ui.pyside.Label('Restore PLEX Media Server Data from Cloud:', self.dlg,
                                ui.pyside.QRect(10, 43, 400, 20))

                # Buttons
                ui.pyside.button('1. Pull {}-PMSDATA from Remote to Local'.format(remote_cls.name), self.dlg,
                                 ui.pyside.QRect(0, 65, 500, 30), pull_pms, remote_cls)
                ui.pyside.button(
                    '2. Unpackage Local {}-PMSDATA to {} PMS'.format(remote_cls.name, os_pref_folder_name),
                    self.dlg, ui.pyside.QRect(0, 95, 500, 30), unpackage_pms, remote_cls
                )

                # Label: Restore PLEX Media Server Data from Cloud
                ui.pyside.Label('Backup PLEX Media Server Data to Cloud:', self.dlg,
                                ui.pyside.QRect(10, 150, 400, 20))

                # Buttons
                ui.pyside.button(
                    '1. Package {} PMS to Local {}-PMSDATA'.format(os_pref_folder_name, remote_cls.name),
                    self.dlg, ui.pyside.QRect(0, 172, 500, 30), package_pms, remote_cls
                )
                ui.pyside.button('2. PUSH {}-PMSDATA from Local to Remote'.format(remote_cls.name), self.dlg,
                                 ui.pyside.QRect(0, 202, 500, 30), push_pms, remote_cls)

            case 'Remote':
                # Open PMSData (Remote) button
                ui.pyside.button('Open Remote -PMSDATA', self.dlg, ui.pyside.QRect(0, 3, 200, 30),
                                 open_dir_remote_cls_pmsdata, remote_cls)

        # --------------------------------------------------------------------------------------------------------------
