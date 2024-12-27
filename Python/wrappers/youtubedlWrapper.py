
import config
import commonUtils.fileUtils as fileUtils
import os
from commonUtils import pySideUtils
from commonUtils.debugUtils import print_debug_msg as print_debug_msg
from pathlib import Path
import commonUtils.wrappers.cmdShellWrapper as cmdShellWrapper
import subprocess
import sys
from wrappers import rcloneWrapper as rcloneWrapper


show_verbose = True
params = '--format best --write-info-json --write-thumbnail --add-metadata --no-overwrites --ignore-errors --no-overwrites --restrict-filenames -f "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio" --merge-output-format mp4'


def reinstall_youtube_dl():
    """
    Reinstall Youtube DL, to make sure have new version
    """
    subprocess.check_call([sys.executable, "-m", "pip", "install", 'youtube-dl'])
    # Install Updated packages
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", '--force-reinstall', 'https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz', '--user'])
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
    config_directory = youtube_dl_cfg_path

    # If that directory doesn't exist, throw error
    if not os.path.isdir(config_directory):
        msg = 'The specified directory for Youtube Download config files does not exist: \n' + config_directory
        msg += '\nAborting!'
        pySideUtils.display_msg_box_ok(tool_name, msg)
        return False

    # Get each config file
    config_dir_file_lst = fileUtils.get_file_path_list(config_directory)

    # Filter the config file (making sure it only keeps .ini)
    filtered_file_lst = []
    filtered_ext = '.ini'
    for file in config_dir_file_lst:
        if file[-len(filtered_ext):] == filtered_ext:
            filtered_file_lst.append(file)

    # Download from each config file
    for filtered_file in filtered_file_lst:
        download(youtube_dl_cfg_path, filtered_file)


def download(youtube_dl_cfg_path, config_file_path, playlist_reverse=True, playlist_end=None, master_branch=True):
    """
    Downloads videos as specified in the config file at path.
    :param config_file_path: Path of config file for videos to download
    :type config_file_path: str
    """

    # Display in Log what is being done
    print_debug_msg('Preparing Youtube Download of Playlist/Channel from config file at path: ' + config_file_path, show_verbose)

    # Determine split char
    if sys.platform == 'win32':
        split_char = '\\'
    else:
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

    # Get Download Directory...
    download_dir = str(Path(os.path.dirname(youtube_dl_cfg_path), channel_name, 'Season ' + str(season_number)))

    # Create string for download command...
    if not master_branch:
        yt_dl_cmd_str = 'youtube-dl '
    else:
        if sys.platform == 'win32':
            yt_dl_cmd_str = 'python -m yt_dlp '
        else:
            yt_dl_cmd_str = 'python3 -m yt_dlp '
    yt_dl_cmd_str += '{download_url} '.format(download_url=download_url)
    if playlist_reverse:
        yt_dl_cmd_str += '--playlist-reverse '
    if playlist_end is not None:
        yt_dl_cmd_str += '--playlist-end ' + str(playlist_end) + ' '
    yt_dl_cmd_str += '{params} {extra_params} '.format(params=params, extra_params=additional_params)

    if sys.platform == 'win32':
        yt_dl_cmd_str += '--ffmpeg-location "' + str(Path(config.LogisticsConfig().path_logistics, 'Software', 'ffmpeg_win', 'ffmpeg.exe')) + '" '
    else:
        yt_dl_cmd_str += '--ffmpeg-location "' + str(Path(config.LogisticsConfig().path_logistics, 'Software', 'ffmpeg_macos', 'ffmpeg')) + '" '

    # Creates a log file listing the completed downloads
    yt_dl_cmd_str += '--download-archive "' + str(Path(youtube_dl_cfg_path, 'CompleteLists', config_path_name + '_complete.lst')) + '" '

    # Sets the download file name
    yt_dl_cmd_str += '-o ' + '"' + download_dir + split_char + '%(channel)s - s0' + str(season_number) + 'e%(autonumber)s - %(title).50s.%(ext)s' + '" '

    # Sets the auto numbering to start at X number (so it continues after the existing files)
    # Find how many files are already there, and start after
    if os.path.exists(download_dir):
        existing_files_lst = fileUtils.get_file_path_list(download_dir)
        count = 1
        for existing_file in existing_files_lst:
            if ' - s' and '.mp4' in existing_file:
                count += 1
    else:
        count = 1

    yt_dl_cmd_str += '--autonumber-start ' + str(count)

    if sys.platform == 'win32':
        yt_dl_cmd_str += '\nexit'

    # Send command to be executed
    print_debug_msg('Executing command string: \n' + yt_dl_cmd_str, show_verbose)
    cmdShellWrapper.exec_cmd(yt_dl_cmd_str, wait_for_output=True, in_new_window=config.LogisticsConfig().temp_cmd)
    print_debug_msg('Successfully executed!', show_verbose)


def push_seasons(remote_cls):
    print('Pushing Seasons')

    # Get list of existing channel dirs
    channel_dir_lst = fileUtils.get_dirs_path_list(os.path.dirname(remote_cls.youtube_dl_cfg_path))

    # Initialize push list
    push_dir_lst = []

    # Determine split char
    if sys.platform == 'win32':
        split_char = '\\'
    else:
        split_char = '/'

    # If these channel dirs have a subdir with season in it, add to push list
    for channel_dir in channel_dir_lst:
        channel_dir_sub_lst = fileUtils.get_dirs_path_list(channel_dir)
        for channel_dir_sub in channel_dir_sub_lst:
            if 'Season' in channel_dir_sub.split(split_char)[-1]:
                push_dir_lst.append(channel_dir_sub)

    # Push Season folders
    for push_dir in push_dir_lst:
        source = push_dir
        destination = remote_cls.name + ':' + push_dir.replace(remote_cls.directory_path, '')[1:].replace('\\', '/')
        print('Pushing {} to {}'.format(source, destination))
        rcloneWrapper.rclone_sync(source,
                                  destination,
                                  wait_for_output=True,
                                  exit_on_done=True)
        print('Push complete!')


def push_config(remote_cls):
    print('Push Config')
    rcloneWrapper.rclone_sync(remote_cls.youtube_dl_cfg_path,
                              remote_cls.name + ':' + remote_cls.youtube_dl_cfg_sub_path)


def pull_config(remote_cls):
    print('Pull Config')
    rcloneWrapper.rclone_sync(remote_cls.name + ':' + remote_cls.youtube_dl_cfg_sub_path,
                              remote_cls.youtube_dl_cfg_path)
