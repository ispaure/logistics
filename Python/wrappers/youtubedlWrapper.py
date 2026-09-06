import os
import subprocess
import sys
from pathlib import Path
from typing import List

import config
from commonUtils import fileUtils, dirUtils, pySideUtils
from commonUtils.debugUtils import *
from commonUtils.debugUtils import print_debug_msg
from commonUtils.osUtils import *
from commonUtils.wrappers import cmdShellWrapper
from . import rcloneWrapper


show_verbose = True
params = '--format best --write-info-json --write-thumbnail --add-metadata --no-overwrites --ignore-errors --no-overwrites --restrict-filenames -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio" --merge-output-format mp4'


def reinstall_youtube_dl():
    """
    Reinstall Youtube DL, to make sure have new version
    """
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'youtube-dl'])

    # Install Updated packages
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '--force-reinstall',
            'https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz', '--user',
        ])
    except:
        print('Could not install plugin, still proceeding')


def download_all(youtube_dl_cfg_path):
    """
    Downloads all missing videos from config files in config dir
    """
    tool_name = 'Batch Youtube Downloader'

    # Reinstall Youtube DL
    reinstall_youtube_dl()

    # Get config directory (where all download configs are stored)
    config_directory = dirUtils.Directory(Path(youtube_dl_cfg_path))

    # If that directory doesn't exist, throw error
    if not os.path.isdir(config_directory.path):
        msg = 'The specified directory for Youtube Download config files does not exist: \n' + str(config_directory.path)
        msg += '\nAborting!'
        pySideUtils.display_msg_box_ok(tool_name, msg)
        return False

    # Get each .INI config file
    config_file_lst: List[fileUtils.File] = config_directory.list_files(filter_extension='ini')

    # Download from each config file
    for config_file in config_file_lst:
        download(youtube_dl_cfg_path, str(config_file.path))


def download(youtube_dl_cfg_path, config_file_path, playlist_reverse=True, playlist_end=None, master_branch=True):
    """
    Downloads videos as specified in the config file at path.

    :param config_file_path: Path of config file for videos to download
    :type config_file_path: str
    """

    # Display in Log what is being done
    print_debug_msg(
        'Preparing Youtube Download of Playlist/Channel from config file at path: ' + config_file_path,
        show_verbose,
    )

    # Determine split char
    match get_os():
        case OS.WIN:
            split_char = '\\'
        case _:
            split_char = '/'

    # From Config File, get the info for the download
    config_path_name = config_file_path.split(split_char)[-1].split('.')[0]
    channel_name = config.config_section_map('Youtube-DL', 'channel_name', config_file_path)
    download_url = config.config_section_map('Youtube-DL', 'download_url', config_file_path)
    season_number = config.config_section_map('Youtube-DL', 'season_number', config_file_path)
    additional_params = config.config_section_map('Youtube-DL', 'additional_params', config_file_path)

    # Print Loaded Infos
    print_debug_msg('Loaded configuration!', show_verbose)
    print_debug_msg('Channel Name: ' + channel_name, show_verbose)
    print_debug_msg('Download URL: ' + download_url, show_verbose)
    print_debug_msg('Season Number: ' + season_number, show_verbose)
    print_debug_msg('Additional Parameters: ' + additional_params, show_verbose)

    # Get Download Directory
    download_dir = dirUtils.Directory(Path(os.path.dirname(youtube_dl_cfg_path), channel_name, 'Season ' + str(season_number)))

    # Create string for download command
    if not master_branch:
        yt_dl_cmd_str = 'youtube-dl '
    else:
        match get_os():
            case OS.WIN:
                yt_dl_cmd_str = 'python -m yt_dlp '
            case OS.MAC:
                yt_dl_cmd_str = 'python3 -m yt_dlp '
            case _:
                log(Severity.CRITICAL, 'youtubedlWrapper', 'Platform unsupported!')
                return

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
            log(Severity.CRITICAL, 'youtubedlWrapper', 'Platform unsupported!')
            return

    yt_dl_cmd_str += f'--ffmpeg-location "{ffmpeg_path}" '

    # Creates a log file listing the completed downloads
    complete_list_path = Path(youtube_dl_cfg_path, 'CompleteLists', config_path_name + '_complete.lst')
    yt_dl_cmd_str += f'--download-archive "{complete_list_path}" '

    # Sets the download file name
    yt_dl_cmd_str += (
        f'-o "{download_dir.path}{split_char}%(channel)s - s0{season_number}'
        f'e%(autonumber)s - %(title).50s.%(ext)s" '
    )

    # Sets the auto numbering to start at X number (so it continues after the existing files)
    # Find how many files are already there, and start after
    if os.path.exists(download_dir.path):
        existing_file_lst: List[fileUtils.File] = download_dir.list_files()
        count = 1

        for existing_file in existing_file_lst:
            if ' - s' and '.mp4' in str(existing_file.path):
                count += 1
    else:
        count = 1

    yt_dl_cmd_str += f'--autonumber-start {count}'

    if get_os() == OS.WIN:
        yt_dl_cmd_str += '\nexit'

    # Send command to be executed
    print_debug_msg('Executing command string: \n' + yt_dl_cmd_str, show_verbose)
    # cmdShellWrapper.exec_cmd(yt_dl_cmd_str, wait_for_output=True, in_new_window=config.LogisticsConfig().temp_cmd)
    cmdShellWrapper.exec_cmd(yt_dl_cmd_str, wait_for_output=True, in_new_window=True)
    print_debug_msg('Successfully executed!', show_verbose)


def push_seasons(remote_cls):
    print('Pushing Seasons')

    # Get list of existing channel dirs
    channel_root_directory = dirUtils.Directory(Path(remote_cls.youtube_dl_cfg_path).parent)
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
        destination = remote_cls.name + ':' + source.relative_to(remote_cls.path).as_posix()

        print(f'Pushing {source} to {destination}')
        rcloneWrapper.rclone_sync(source, destination, wait_for_output=True)
        print('Push complete!')


def push_config(remote_cls):
    print('Push Config')
    rcloneWrapper.rclone_sync(
        remote_cls.youtube_dl_cfg_path,
        remote_cls.name + ':' + remote_cls.youtube_dl_cfg_sub_path,
    )


def pull_config(remote_cls):
    print('Pull Config')
    rcloneWrapper.rclone_sync(
        remote_cls.name + ':' + remote_cls.youtube_dl_cfg_sub_path,
        remote_cls.youtube_dl_cfg_path,
    )
