from commonUtils import fileUtils
from commonUtils.osUtils import *
from pathlib import Path
import os
import config
from commonUtils.wrappers import cmdShellWrapper
import time
from wrappers import rcloneWrapper
from ui.rclone.popup import uiLocalPush
from ui.plex_media_server import uiManagePMS
from ui.calibre import uiManageCalibre
from ui.debug.popup import uiYoutubeDL
import commands as commands
from commonUtils.debugUtils import *


def inter_open_dir(remote_cls):
    interaction_dict = {}
    if 'Server-' in remote_cls.name[0:len('Server-')]:  # Visually remove "Server-" from name if possible
        interaction_dict['Name'] = remote_cls.name[len('Server-'):]
    else:
        interaction_dict['Name'] = remote_cls.name
    interaction_dict['Action'] = inter_open_dir_action
    return interaction_dict


def inter_open_dir_action(remote_cls):
    print('Opening Directory')
    print(remote_cls.path)
    fileUtils.open_dir_path(remote_cls.path)


def inter_comic_rack_yac_reader(remote_cls):
    interaction_dict = {}

    # Only scan for local shares (can't work over rclone)
    if remote_cls.type == 'Local':
        # Detect ComicRack (on Windows)
        if get_os() == OS.WIN and remote_cls.comic_rack_roaming is not None:
            interaction_dict['Name'] = 'Open ComicRack'
            interaction_dict['Action'] = inter_comic_rack_action
            return interaction_dict
        # Detect YacReaderLibrary (on macOS)
        elif remote_cls.yac_reader_library_ini is not None:
            interaction_dict['Name'] = 'Open YACReaderLibrary'
            interaction_dict['Action'] = inter_yac_reader_action
            return interaction_dict

    interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = None
    return interaction_dict


def inter_comic_rack_action(remote_cls):
    # Determine ComicRack Preference Links
    cyo_appdata_local_dir_path: Path = Path(os.environ['USERPROFILE'], 'AppData', 'Local', 'cYo')
    cyo_appdata_roaming_dir_path: Path = Path(os.environ['USERPROFILE'], 'AppData', 'Roaming', 'cYo')

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
    exec_path: Path = Path(config.LogisticsConfig().path_logistics_software_win, 'ComicRack', 'ComicRack.exe')
    cmdShellWrapper.exec_cmd(f'start "{exec_path}"', wait_for_output=False)


def inter_yac_reader_action(remote_cls):
    # If YACReader not installed, unzip in /Applications
    install_path: Path = Path('/Applications', 'YACReader.app')
    if not os.path.exists(install_path):
        zip_path: Path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReader.app.zip')
        fileUtils.unzip_file(zip_path, install_path)

    # If YACReaderLibrary not installed, unzip in /Applications
    install_path = Path('/Applications', 'YACReaderLibrary.app')
    if not os.path.exists(install_path):
        zip_path = Path(config.LogisticsConfig().path_logistics_software_mac, 'YACReaderLibrary.app.zip')
        fileUtils.unzip_file(zip_path, install_path)

    yac_prefs_dir = config.LogisticsConfig().yac_lib_prefs_dir
    if yac_prefs_dir is None:
        log(Severity.CRITICAL, 'inter_yac_reader_action', 'YACReaderLibrary preferences directory is not configured for this platform')
        return False

    # Create Directory where to put the library file
    fileUtils.make_dir(yac_prefs_dir)

    # Copy YACReaderLibrary ini file to Application Support
    fileUtils.copy_file(remote_cls.yac_reader_library_ini, Path(yac_prefs_dir, 'YACReaderLibrary.ini'))

    # Open YACReader
    cmdShellWrapper.exec_cmd(str(Path('/Applications', 'YACReaderLibrary.app', 'Contents', 'MacOS', 'YACReaderLibrary')), wait_for_output=False)


def inter_calibre_manage(remote_cls):
    interaction_dict = {}
    if remote_cls.calibre_lib_path is not None and remote_cls.type == 'Local':
        interaction_dict['Name'] = 'Manage Calibre'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = inter_calibre_manage_action
    return interaction_dict


def inter_calibre_manage_action(remote_cls):
    if remote_cls.calibre_lib_path is not None and remote_cls.type == 'Local':
        manage_calibre_cls = uiManageCalibre.ManageCalibre(remote_cls)
        manage_calibre_cls.display_ui()
    else:
        print('NOT HAVE CALIBRE LIBRARIES')


def inter_rclone_push_pull(remote_cls):
    interaction_dict = {}
    if remote_cls.type == 'Local':
        interaction_dict['Name'] = 'PUSH'
    elif remote_cls.type == 'Remote':
        interaction_dict['Name'] = 'PULL'
    interaction_dict['Action'] = inter_rclone_push_pull_action
    return interaction_dict


def inter_rclone_push_pull_action(remote_cls):
    action = None

    # Determine rclone sync command
    if remote_cls.type == 'Local':
        local_push_cls = uiLocalPush.LocalPushUI(remote_cls)
        local_push_cls.display_ui()

    elif remote_cls.type == 'Remote':
        source_path = remote_cls.name + ':'
        destination_path: Path = Path(config.LogisticsConfig().path_remote_local, remote_cls.name)
        rcloneWrapper.rclone_sync(source_path, destination_path)
    else:
        print('Remote Type Invalid. Not proceeding in case this would screw up something big.')
        return False


def inter_manage_pms(remote_cls):
    interaction_dict = {}
    if remote_cls.name + '-PMSDATA' in rcloneWrapper.get_rclone_conf_remote_credentials_dict().keys():
        interaction_dict['Name'] = 'Manage PMS'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = inter_manage_pms_action
    return interaction_dict


def inter_manage_pms_action(remote_cls):
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


def interaction_07(remote_cls):
    interaction_dict = {}
    if get_os() == OS.LINUX and remote_cls.perforce_p4d_path is not None and remote_cls.type == 'Local':
        interaction_dict['Name'] = 'Launch P4D'
    else:
        interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = interaction_07_action
    return interaction_dict


def interaction_07_action(remote_cls):
    if get_os() == OS.LINUX and remote_cls.perforce_p4d_path is not None and remote_cls.type == 'Local':
        command = f'./{remote_cls.perforce_p4d_path} -C1 -r ./{remote_cls.perforce_data_path} -p ' \
                  f'{remote_cls.perforce_port}'
        cmdShellWrapper.exec_cmd(command, in_new_window=True, cwd=remote_cls.path)


interaction_fn_lst = [inter_open_dir,
                      inter_comic_rack_yac_reader,
                      inter_calibre_manage,
                      inter_manage_pms,
                      interaction_06,
                      interaction_07,
                      inter_rclone_push_pull]


def get_remote_cls_lst_interactions(remote_cls_lst):
    interaction_complete_lst = []
    remote_amt = 0
    for remote_cls in remote_cls_lst:
        if not remote_cls.is_pms_data:
            remote_amt += 1
            for interaction in interaction_fn_lst:
                interaction_complete_lst.append([interaction, remote_cls])

    return interaction_complete_lst, remote_amt
