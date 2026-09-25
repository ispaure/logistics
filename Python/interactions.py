from commonUtils.osUtils import OS, get_os

from features.calibre import detection as calibre_detection
from features.comics import actions as comics_actions
from features.comics import detection as comics_detection
from features.perforce import actions as perforce_actions
from features.perforce import detection as perforce_detection
from features.plex import detection as plex_detection
from features.rclone import actions as rclone_actions
from features.rclone import configuration as rclone_configuration
from features.youtube_downloader import detection as youtube_downloader_detection
from models.interaction import Interaction
from models.local_folder import LocalFolder
from models.remote_folder import RemoteFolder

from ui.calibre import uiManageCalibre
from ui.debug.popup import uiYoutubeDL
from ui.plex_media_server import uiManagePMS
from ui.rclone.popup import uiLocalPush


def inter_open_dir(remote_cls):
    if remote_cls.name.startswith('Server-'):
        name = remote_cls.name[len('Server-'):]
    else:
        name = remote_cls.name

    return Interaction(name, inter_open_dir_action, remote_cls)


def inter_open_dir_action(remote_cls):
    print('Opening Directory')
    print(remote_cls.path)
    remote_cls.open()


def inter_comic_rack_yac_reader(remote_cls):
    if isinstance(remote_cls, LocalFolder):
        if get_os() == OS.WIN and comics_detection.has_comic_rack(remote_cls):
            return Interaction('Open ComicRack', inter_comic_rack_action, remote_cls)

        if comics_detection.has_yac_reader_library(remote_cls):
            return Interaction('Open YACReaderLibrary', inter_yac_reader_action, remote_cls)

    return Interaction('N/A', None)


def inter_comic_rack_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return comics_actions.open_comic_rack(remote_cls)


def inter_yac_reader_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return comics_actions.open_yac_reader_library(remote_cls)


def inter_calibre_manage(remote_cls):
    if isinstance(remote_cls, LocalFolder) and calibre_detection.has_library(remote_cls):
        return Interaction('Manage Calibre', inter_calibre_manage_action, remote_cls)

    return Interaction('N/A', None)


def inter_calibre_manage_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder) or not calibre_detection.has_library(remote_cls):
        return False

    manage_calibre_cls = uiManageCalibre.ManageCalibre(remote_cls)
    manage_calibre_cls.display_ui()


def inter_rclone_push_pull(remote_cls):
    if isinstance(remote_cls, LocalFolder):
        return Interaction('PUSH', inter_rclone_push_pull_action, remote_cls)

    if isinstance(remote_cls, RemoteFolder):
        return Interaction('PULL', inter_rclone_push_pull_action, remote_cls)

    return Interaction('N/A', None)


def inter_rclone_push_pull_action(remote_cls):
    if isinstance(remote_cls, LocalFolder):
        local_push_cls = uiLocalPush.LocalPushUI(remote_cls)
        local_push_cls.display_ui()
        return

    if isinstance(remote_cls, RemoteFolder):
        return rclone_actions.pull_from_cloud(remote_cls)

    return False


def inter_manage_pms(remote_cls):
    remote_names = rclone_configuration.get_rclone_conf_remote_credentials_dict().keys()

    if plex_detection.has_pms_data_remote(remote_cls, remote_names):
        return Interaction('Manage PMS', inter_manage_pms_action, remote_cls)

    return Interaction('N/A', None)


def inter_manage_pms_action(remote_cls):
    remote_names = rclone_configuration.get_rclone_conf_remote_credentials_dict().keys()

    if not plex_detection.has_pms_data_remote(remote_cls, remote_names):
        return False

    manage_pms_cls = uiManagePMS.ManagePMS(remote_cls)
    manage_pms_cls.display_ui()


def inter_youtube_downloader(remote_cls):
    if isinstance(remote_cls, LocalFolder) and youtube_downloader_detection.has_config(remote_cls):
        return Interaction('Youtube DL', inter_youtube_downloader_action, remote_cls)

    return Interaction('N/A', None)


def inter_youtube_downloader_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder) or not youtube_downloader_detection.has_config(remote_cls):
        return False

    youtube_dl_cls = uiYoutubeDL.YoutubeDLUI(remote_cls)
    youtube_dl_cls.display_ui()


def inter_perforce(remote_cls):
    if get_os() == OS.LINUX and isinstance(remote_cls, LocalFolder) and perforce_detection.has_p4d_server(remote_cls):
        return Interaction('Launch P4D', inter_perforce_action, remote_cls)

    return Interaction('N/A', None)


def inter_perforce_action(remote_cls):
    if not isinstance(remote_cls, LocalFolder):
        return False

    return perforce_actions.launch_server(remote_cls)


interaction_fn_lst = [
    inter_open_dir,
    inter_comic_rack_yac_reader,
    inter_calibre_manage,
    inter_manage_pms,
    inter_youtube_downloader,
    inter_perforce,
    inter_rclone_push_pull,
]


def get_remote_cls_lst_interactions(remote_cls_lst):
    interaction_complete_lst = []
    remote_amt = 0

    for remote_cls in remote_cls_lst:
        if plex_detection.is_pms_data_folder(remote_cls):
            continue

        remote_amt += 1

        for interaction_fn in interaction_fn_lst:
            interaction_complete_lst.append(interaction_fn(remote_cls))

    return interaction_complete_lst, remote_amt