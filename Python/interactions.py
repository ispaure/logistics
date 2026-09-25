from pathlib import Path

import config

from commonUtils.osUtils import OS, get_os

from features.calibre import detection as calibre_detection
from features.comics import actions as comics_actions
from features.comics import detection as comics_detection
from features.perforce import actions as perforce_actions
from features.perforce import detection as perforce_detection
from features.plex import detection as plex_detection
from features.rclone import configuration as rclone_configuration
from features.rclone import sync as rclone_sync
from features.youtube_downloader import detection as youtube_downloader_detection
from models.local_folder import LocalFolder
from models.remote_folder import RemoteFolder

from ui.calibre import uiManageCalibre
from ui.debug.popup import uiYoutubeDL
from ui.plex_media_server import uiManagePMS
from ui.rclone.popup import uiLocalPush


def inter_open_dir(remote_cls):
    interaction_dict = {}

    if 'Server-' in remote_cls.name[0:len('Server-')]:
        interaction_dict['Name'] = remote_cls.name[len('Server-'):]
    else:
        interaction_dict['Name'] = remote_cls.name

    interaction_dict['Action'] = inter_open_dir_action
    return interaction_dict


def inter_open_dir_action(remote_cls):
    print('Opening Directory')
    print(remote_cls.path)
    remote_cls.open()


def inter_comic_rack_yac_reader(remote_cls):
    interaction_dict = {}

    if isinstance(remote_cls, LocalFolder):

        if get_os() == OS.WIN and comics_detection.has_comic_rack(remote_cls):
            interaction_dict['Name'] = 'Open ComicRack'
            interaction_dict['Action'] = inter_comic_rack_action
            return interaction_dict

        elif comics_detection.has_yac_reader_library(remote_cls):
            interaction_dict['Name'] = 'Open YACReaderLibrary'
            interaction_dict['Action'] = inter_yac_reader_action
            return interaction_dict

    interaction_dict['Name'] = 'N/A'
    interaction_dict['Action'] = None
    return interaction_dict


def inter_comic_rack_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return comics_actions.open_comic_rack(remote_cls)


def inter_yac_reader_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return comics_actions.open_yac_reader_library(remote_cls)


def inter_calibre_manage(remote_cls):
    interaction_dict = {}

    if isinstance(remote_cls, LocalFolder) and calibre_detection.has_library(remote_cls):
        interaction_dict['Name'] = 'Manage Calibre'
    else:
        interaction_dict['Name'] = 'N/A'

    interaction_dict['Action'] = inter_calibre_manage_action
    return interaction_dict


def inter_calibre_manage_action(remote_cls):
    if isinstance(remote_cls, LocalFolder) and calibre_detection.has_library(remote_cls):
        manage_calibre_cls = uiManageCalibre.ManageCalibre(remote_cls)
        manage_calibre_cls.display_ui()
    else:
        print('NOT HAVE CALIBRE LIBRARIES')


def inter_rclone_push_pull(remote_cls):
    interaction_dict = {}

    if isinstance(remote_cls, LocalFolder):
        interaction_dict['Name'] = 'PUSH'

    elif isinstance(remote_cls, RemoteFolder):
        interaction_dict['Name'] = 'PULL'

    else:
        interaction_dict['Name'] = 'N/A'

    interaction_dict['Action'] = inter_rclone_push_pull_action
    return interaction_dict


def inter_rclone_push_pull_action(remote_cls):
    if isinstance(remote_cls, LocalFolder):
        local_push_cls = uiLocalPush.LocalPushUI(remote_cls)
        local_push_cls.display_ui()

    elif isinstance(remote_cls, RemoteFolder):
        source_path = remote_cls.name + ':'
        destination_path = Path(config.LogisticsConfig().path_remote_local, remote_cls.name)
        rclone_sync.rclone_sync(source_path, destination_path)

    else:
        print('Folder type invalid. Not proceeding in case this would screw up something big.')
        return False


def inter_manage_pms(remote_cls):
    interaction_dict = {}

    remote_names = rclone_configuration.get_rclone_conf_remote_credentials_dict().keys()

    if plex_detection.has_pms_data_remote(remote_cls, remote_names):
        interaction_dict['Name'] = 'Manage PMS'
    else:
        interaction_dict['Name'] = 'N/A'

    interaction_dict['Action'] = inter_manage_pms_action
    return interaction_dict


def inter_manage_pms_action(remote_cls):
    remote_names = rclone_configuration.get_rclone_conf_remote_credentials_dict().keys()

    if plex_detection.has_pms_data_remote(remote_cls, remote_names):
        manage_pms_cls = uiManagePMS.ManagePMS(remote_cls)
        manage_pms_cls.display_ui()
    else:
        print('NOPE')


def interaction_06(remote_cls):
    interaction_dict = {}

    if isinstance(remote_cls, LocalFolder) and youtube_downloader_detection.has_config(remote_cls):
        interaction_dict['Name'] = 'Youtube DL'
    else:
        interaction_dict['Name'] = 'N/A'

    interaction_dict['Action'] = interaction_06_action
    return interaction_dict


def interaction_06_action(remote_cls):
    if isinstance(remote_cls, LocalFolder) and youtube_downloader_detection.has_config(remote_cls):
        youtube_dl_cls = uiYoutubeDL.YoutubeDLUI(remote_cls)
        youtube_dl_cls.display_ui()


def interaction_07(remote_cls):
    interaction_dict = {}

    if get_os() == OS.LINUX and isinstance(remote_cls, LocalFolder) and perforce_detection.has_p4d_server(remote_cls):
        interaction_dict['Name'] = 'Launch P4D'
    else:
        interaction_dict['Name'] = 'N/A'

    interaction_dict['Action'] = interaction_07_action
    return interaction_dict


def interaction_07_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return perforce_actions.launch_server(remote_cls)


interaction_fn_lst = [
    inter_open_dir,
    inter_comic_rack_yac_reader,
    inter_calibre_manage,
    inter_manage_pms,
    interaction_06,
    interaction_07,
    inter_rclone_push_pull,
]


def get_remote_cls_lst_interactions(remote_cls_lst):
    interaction_complete_lst = []
    remote_amt = 0

    for remote_cls in remote_cls_lst:
        if plex_detection.is_pms_data_folder(remote_cls):
            continue

        remote_amt += 1

        for interaction in interaction_fn_lst:
            interaction_complete_lst.append([interaction, remote_cls])

    return interaction_complete_lst, remote_amt