import sys
from pathlib import Path
from typing import List

import config

from commonUtils import configUtils, dirUtils, fileUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper
from features.youtube_downloader import detection as youtube_downloader_detection
from models.local_folder import LocalFolder


show_verbose = True
params = (
    '--format best --write-info-json --write-thumbnail --add-metadata --no-overwrites --ignore-errors '
    '--no-overwrites --restrict-filenames -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio" '
    '--merge-output-format mp4'
)


def update_yt_dlp():
    """
    Update yt-dlp in the Python environment currently running Logistics.
    """
    tool_name = 'Update yt-dlp'
    python_exec = f'"{sys.executable}"'

    log(Severity.INFO, tool_name, f'Updating yt-dlp using Python environment: {sys.executable}')

    command = f'{python_exec} -m pip install --upgrade yt-dlp'

    try:
        cmdShellWrapper.exec_cmd(command, wait_for_output=True)
    except Exception as exception:
        log(Severity.WARNING, tool_name, f'Could not update yt-dlp. Still proceeding.\n{exception}')


def download_all(youtube_dl_cfg_path):
    """
    Downloads all missing videos from config files in config dir.
    """
    tool_name = 'Batch Youtube Downloader'

    # Update yt-dlp
    update_yt_dlp()

    # Get config directory where all download configs are stored
    config_directory = dirUtils.Directory(Path(youtube_dl_cfg_path))

    if not config_directory.path.is_dir():
        msg = f'The specified directory for Youtube Download config files does not exist:\n{config_directory.path}\nAborting!'
        log(Severity.ERROR, tool_name, msg, popup=True)
        return False

    # Get each .INI config file
    config_file_lst: List[fileUtils.File] = config_directory.list_files(filter_extension='ini')

    # Download from each config file
    for config_file in config_file_lst:
        download(youtube_dl_cfg_path, str(config_file.path))


def download(youtube_dl_cfg_path, config_file_path, playlist_reverse=True, playlist_end=None):
    """
    Downloads videos as specified in the config file at path.

    :param config_file_path: Path of config file for videos to download
    :type config_file_path: str
    """
    tool_name = 'Youtube Downloader'

    # Display in log what is being done
    log(Severity.INFO, tool_name, 'Preparing Youtube Download of Playlist/Channel from config file at path: ' + str(config_file_path))

    config_file_path = Path(config_file_path)
    youtube_dl_cfg_path = Path(youtube_dl_cfg_path)

    # From config file, get the info for the download
    config_path_name = config_file_path.stem
    channel_name = configUtils.config_section_map(config_file_path, 'Youtube-DL', 'channel_name')
    download_url = configUtils.config_section_map(config_file_path, 'Youtube-DL', 'download_url')
    season_number = configUtils.config_section_map(config_file_path, 'Youtube-DL', 'season_number')
    additional_params = configUtils.config_section_map(config_file_path, 'Youtube-DL', 'additional_params')

    # Print loaded info
    log(Severity.INFO, tool_name, 'Loaded configuration!')
    log(Severity.DEBUG, tool_name, 'Channel Name: ' + channel_name)
    log(Severity.DEBUG, tool_name, 'Download URL: ' + download_url)
    log(Severity.DEBUG, tool_name, 'Season Number: ' + season_number)
    log(Severity.DEBUG, tool_name, 'Additional Parameters: ' + additional_params)

    # Get download directory
    download_dir = dirUtils.Directory(youtube_dl_cfg_path.parent / channel_name / ('Season ' + str(season_number)))

    # Create string for download command
    yt_dl_cmd_str = f'"{sys.executable}" -m yt_dlp '
    yt_dl_cmd_str += f'{download_url} '

    if playlist_reverse:
        yt_dl_cmd_str += '--playlist-reverse '

    if playlist_end is not None:
        yt_dl_cmd_str += f'--playlist-end {playlist_end} '

    yt_dl_cmd_str += f'{params} {additional_params} '

    match get_os():
        case OS.WIN:
            ffmpeg_path = Path(config.LogisticsConfig().path_logistics_software, 'ffmpeg_win', 'ffmpeg.exe')
        case OS.MAC:
            ffmpeg_path = Path(config.LogisticsConfig().path_logistics_software, 'ffmpeg_macos', 'ffmpeg')
        case _:
            log(Severity.CRITICAL, tool_name, 'Platform unsupported!')
            return

    yt_dl_cmd_str += f'--ffmpeg-location "{ffmpeg_path}" '

    # Create a log file listing the completed downloads
    complete_list_path = youtube_dl_cfg_path / 'CompleteLists' / f'{config_path_name}_complete.lst'
    yt_dl_cmd_str += f'--download-archive "{complete_list_path}" '

    # Set the download file name
    match get_os():
        case OS.WIN:
            split_char = '\\'
        case _:
            split_char = '/'

    yt_dl_cmd_str += f'-o "{download_dir.path}{split_char}%(channel)s - s0{season_number}e%(autonumber)s - %(title).50s.%(ext)s" '

    # Set auto numbering to continue after existing files
    count = 1

    if download_dir.path.exists():
        existing_file_lst: List[fileUtils.File] = download_dir.list_files()

        for existing_file in existing_file_lst:
            if ' - s' in str(existing_file.path) and '.mp4' in str(existing_file.path):
                count += 1

    yt_dl_cmd_str += f'--autonumber-start {count}'

    if get_os() == OS.WIN:
        yt_dl_cmd_str += '\nexit'

    # Send command to be executed
    log(Severity.DEBUG, tool_name, 'Executing command string: \n' + yt_dl_cmd_str)
    cmdShellWrapper.exec_cmd(yt_dl_cmd_str, wait_for_output=True, in_new_window=True)
    log(Severity.INFO, tool_name, 'Successfully executed!')


def push_seasons(folder: LocalFolder, config_path: str | Path):
    from features.rclone import sync as rclone_sync

    print('Pushing Seasons')

    youtube_dl_cfg_path = youtube_downloader_detection.get_config_path(folder)

    if youtube_dl_cfg_path is None:
        log(Severity.ERROR, 'push_seasons', f'No Youtube Download configuration found for "{folder.name}"')
        return False

    # Get list of existing channel dirs
    channel_root_directory = dirUtils.Directory(youtube_dl_cfg_path.parent)
    channel_dir_lst: List[dirUtils.Directory] = channel_root_directory.list_directories()

    # Initialize push list
    push_dir_lst: List[dirUtils.Directory] = []

    # If these channel dirs have a subdir with season in it, add to push list
    for channel_dir in channel_dir_lst:
        channel_dir_sub_lst: List[dirUtils.Directory] = channel_dir.list_directories()

        for channel_dir_sub in channel_dir_sub_lst:
            if 'Season' in channel_dir_sub.name:
                push_dir_lst.append(channel_dir_sub)

    # Push Season folders
    for push_dir in push_dir_lst:
        source = push_dir.path
        destination = folder.name + ':' + source.relative_to(folder.path).as_posix()

        print(f'Pushing {source} to {destination}')
        rclone_sync.rclone_sync(
            source,
            destination,
            config_path=config_path,
            wait_for_output=True
        )
        print('Push complete!')


def push_config(folder: LocalFolder, config_path: str | Path):
    from features.rclone import sync as rclone_sync

    print('Push Config')

    youtube_dl_cfg_path = youtube_downloader_detection.get_config_path(folder)
    youtube_dl_cfg_sub_path = youtube_downloader_detection.get_config_sub_path(folder)

    if youtube_dl_cfg_path is None or youtube_dl_cfg_sub_path is None:
        log(Severity.ERROR, 'push_config', f'No Youtube Download configuration found for "{folder.name}"')
        return False

    rclone_sync.rclone_sync(
        youtube_dl_cfg_path,
        folder.name + ':' + youtube_dl_cfg_sub_path,
        config_path=config_path
    )


def pull_config(folder: LocalFolder, config_path: str | Path):
    from features.rclone import sync as rclone_sync

    print('Pull Config')

    youtube_dl_cfg_path = youtube_downloader_detection.get_config_path(folder)
    youtube_dl_cfg_sub_path = youtube_downloader_detection.get_config_sub_path(folder)

    if youtube_dl_cfg_path is None or youtube_dl_cfg_sub_path is None:
        log(Severity.ERROR, 'pull_config', f'No Youtube Download configuration found for "{folder.name}"')
        return False

    rclone_sync.rclone_sync(
        folder.name + ':' + youtube_dl_cfg_sub_path,
        youtube_dl_cfg_path,
        config_path=config_path
    )
