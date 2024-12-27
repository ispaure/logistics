
import commonUtils.fileUtils as fileUtils
from pathlib import Path
import os
import sys
import config
import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
import time
import wrappers.rcloneWrapper as rcloneWrapper
import ui.uiManagePMS as uiManagePMS
import ui.uiLocalPush as uiLocalPush
import ui.uiYoutubeDL as uiYoutubeDL
import commands as commands


def interaction_01(remote_cls):
    interaction_dict = {}
    if 'Server-' in remote_cls.name[0:len('Server-')]:  # Visually remove "Server-" from name if possible
        interaction_dict['Name'] = remote_cls.name[len('Server-'):]
    else:
        interaction_dict['Name'] = remote_cls.name
    interaction_dict['Action'] = interaction_01_action
    return interaction_dict


def interaction_01_action(remote_cls):
    print('Opening Directory')
    print(remote_cls.directory_path)
    fileUtils.open_dir_path(remote_cls.directory_path)


def interaction_02(remote_cls):
    interaction_dict = {}

    # Only scan for local shares (can't work over rclone)
    if remote_cls.type == 'Local':
        # Detect ComicRack (on Windows)
        if sys.platform == 'win32' and remote_cls.comic_rack_roaming is not None:
            interaction_dict['Name'] = 'Open ComicRack'
            interaction_dict['Action'] = interaction_02_action_comic_rack
            return interaction_dict
        # Detect YacReaderLibrary (on macOS)
        elif remote_cls.yac_reader_library_ini is not None:
            interaction_dict['Name'] = 'Open YACReaderLibrary'
            interaction_dict['Action'] = interaction_02_action_yac_reader_library
            return interaction_dict

    interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = None
    return interaction_dict


def interaction_02_action_comic_rack(remote_cls):
    # Determine ComicRack Preference Links
    cyo_appdata_local_dir_path = str(Path(os.environ['USERPROFILE'], 'AppData', 'Local', 'cYo'))
    cyo_appdata_roaming_dir_path = str(Path(os.environ['USERPROFILE'], 'AppData', 'Roaming', 'cYo'))

    # If paths are invalid, do not proceed!
    if cyo_appdata_local_dir_path is None or cyo_appdata_roaming_dir_path is None:
        return False

    # If they exist already, delete
    fileUtils.delete_symbolic_link(cyo_appdata_local_dir_path)
    fileUtils.delete_symbolic_link(cyo_appdata_roaming_dir_path)
    fileUtils.delete_symbolic_link(cyo_appdata_local_dir_path)
    fileUtils.delete_symbolic_link(cyo_appdata_roaming_dir_path)

    time.sleep(0.2)

    # Create links...
    fileUtils.create_symbolic_link(remote_cls.comic_rack_local, cyo_appdata_local_dir_path)
    fileUtils.create_symbolic_link(remote_cls.comic_rack_roaming, cyo_appdata_roaming_dir_path)

    time.sleep(0.2)

    # Start software
    exec_path = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'ComicRack', 'ComicRack.exe'))
    cmdShellWrapper.exec_cmd('start ' + exec_path, wait_for_output=False)


def interaction_02_action_yac_reader_library(remote_cls):
    # If YACReader not installed, unzip in /Applications
    install_path = str(Path('/Applications', 'YACReader.app'))
    if not os.path.exists(install_path):
        zip_path = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'YACReader.app.zip'))
        fileUtils.unzip_file(zip_path, install_path)
    # If YACReaderLibrary not installed, unzip in /Applications
    install_path = str(Path('/Applications', 'YACReaderLibrary.app'))
    if not os.path.exists(install_path):
        zip_path = str(Path(config.LogisticsConfig().path_logistics, 'Software', 'YACReaderLibrary.app.zip'))
        fileUtils.unzip_file(zip_path, install_path)

    yac_prefs_dir = config.LogisticsConfig().yac_lib_prefs_dir
    # Create Directory where to put the library file
    fileUtils.make_dir(yac_prefs_dir)

    # Copy YACReaderLibrary ini file to Application Support
    fileUtils.copy_file(remote_cls.yac_reader_library_ini, str(Path(yac_prefs_dir, 'YACReaderLibrary.ini')))

    # Open YACReader
    cmdShellWrapper.exec_cmd(str(Path('/Applications', 'YACReaderLibrary.app', 'Contents', 'MacOS', 'YACReaderLibrary')), wait_for_output=False)


def interaction_03(remote_cls):
    interaction_dict = {}
    if remote_cls.calibre_lib_path is not None and remote_cls.type == 'Local':
        interaction_dict['Name'] = 'Open Calibre'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = interaction_03_action
    return interaction_dict


def interaction_03_action(remote_cls):
    if remote_cls.calibre_lib_path is not None and remote_cls.type == 'Local':
        commands.open_calibre(remote_cls.calibre_lib_path)


def interaction_04(remote_cls):
    interaction_dict = {}
    if remote_cls.type == 'Local':
        interaction_dict['Name'] = 'PUSH'
    elif remote_cls.type == 'Remote':
        interaction_dict['Name'] = 'PULL'
    interaction_dict['Action'] = interaction_04_action
    return interaction_dict


def interaction_04_action(remote_cls):
    action = None

    # Will need to create new .bat or .sh file and launch it separately, so we can see output

    rclone_path = rcloneWrapper.get_rclone_path()

    # Determine rclone sync command
    if remote_cls.type == 'Local':
        local_push_cls = uiLocalPush.LocalPushUI(remote_cls)
        local_push_cls.display_ui()

    elif remote_cls.type == 'Remote':
        source_path = remote_cls.name + ':'
        destination_path = str(Path(config.LogisticsConfig().path_remote_local, remote_cls.name))
        rcloneWrapper.rclone_sync(source_path, destination_path)
    else:
        print('Remote Type Invalid. Not proceeding in case this would screw up something big.')
        return False


def interaction_05(remote_cls):
    interaction_dict = {}
    if remote_cls.name + '-PMSDATA' in rcloneWrapper.get_rclone_conf_remote_credentials_dict().keys():
        interaction_dict['Name'] = 'Manage PMS'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = interaction_05_action
    return interaction_dict


def interaction_05_action(remote_cls):
    """
    When interaction 5 is triggered, UI to Manage PMS Opens
    """
    if remote_cls.name + '-PMSDATA' in rcloneWrapper.get_rclone_conf_remote_credentials_dict().keys():
        manage_pms_cls = uiManagePMS.ManagePMS(remote_cls)
        manage_pms_cls.display_ui()
    else:
        print('NOPE')


def interaction_06(remote_cls):
    interaction_dict = {}
    if remote_cls.youtube_dl_cfg_path is not None and remote_cls.type == 'Local':
        interaction_dict['Name'] = 'Youtube DL'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = interaction_06_action
    return interaction_dict


def interaction_06_action(remote_cls):
    if remote_cls.youtube_dl_cfg_path is not None and remote_cls.type == 'Local':
        youtube_dl_cls = uiYoutubeDL.YoutubeDLUI(remote_cls)
        youtube_dl_cls.display_ui()


interaction_fn_lst = [interaction_01,
                      interaction_02,
                      interaction_03,
                      interaction_05,
                      interaction_06,
                      interaction_04]


def get_remote_cls_lst_interactions(remote_cls_lst):
    interaction_complete_lst = []
    remote_amt = 0
    for remote_cls in remote_cls_lst:
        if not remote_cls.is_pms_data:
            remote_amt += 1
            for interaction in interaction_fn_lst:
                interaction_complete_lst.append([interaction, remote_cls])

    return interaction_complete_lst, remote_amt
