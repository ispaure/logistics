"""Run configured downloads and expose the optional remote sync workflow."""

from configparser import Error as ConfigError
from pathlib import Path
import subprocess
import sys

from commonUtils.debugUtils import Severity, log
from features.youtube_downloader.settings import DownloadSettings, download_arguments, find_ffmpeg
from .sync import push_seasons, push_config, pull_config


def update_yt_dlp() -> bool:
    """Attempt a bounded update in the running environment; failure is nonfatal."""
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'],
                       check=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as error:
        log(Severity.WARNING, 'Update yt-dlp', f'Could not update yt-dlp. Still proceeding.\n{error}')
        return False
    return True


def download_all(youtube_dl_cfg_path) -> bool:
    """Validate the config directory before updating and downloading each INI."""
    directory = Path(youtube_dl_cfg_path)
    if not directory.is_dir():
        log(Severity.ERROR, 'Batch Youtube Downloader',
            f'Download config directory does not exist: {directory}', popup=True)
        return False
    files = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == '.ini'),
                   key=lambda path: path.name.casefold())
    if not files:
        return True
    update_yt_dlp()
    success = True
    for path in files:
        if not download(directory, path):
            success = False
    return success


def download(youtube_dl_cfg_path, config_file_path, playlist_reverse=True, playlist_end=None) -> bool:
    """Run a single download and report its process exit status."""
    try:
        directory = Path(youtube_dl_cfg_path)
        if not directory.is_dir():
            raise FileNotFoundError(f'Download config directory does not exist: {directory}')
        settings = DownloadSettings.read(Path(config_file_path))
        arguments = download_arguments(settings, directory, find_ffmpeg(), playlist_reverse, playlist_end)
        settings.destination(directory).mkdir(parents=True, exist_ok=True)
        (directory / 'CompleteLists').mkdir(exist_ok=True)
        log(Severity.INFO, 'Youtube Downloader', f'Downloading {settings.channel}, season {settings.season}.')
        subprocess.run(arguments, check=True)
    except (OSError, ValueError, KeyError, ConfigError, subprocess.SubprocessError) as error:
        log(Severity.ERROR, 'Youtube Downloader', f'Download failed: {error}', popup=True)
        return False
    log(Severity.INFO, 'Youtube Downloader', 'Download command completed.')
    return True
