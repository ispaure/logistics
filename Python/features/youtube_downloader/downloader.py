"""Run configured downloads and expose the optional remote sync workflow."""

from configparser import Error as ConfigError
from pathlib import Path
import shutil
import sys

from commonUtils.debugUtils import Severity, log
from commonUtils.wrappers.cmdShellWrapper import run_command
from features.youtube_downloader.settings import DownloadSettings, download_arguments, find_ffmpeg
from .sync import push_seasons, push_config, pull_config


def update_yt_dlp(*, cancelled=lambda: False) -> bool:
    """Explicit, cancellable update; normal downloads never modify dependencies."""
    uv = shutil.which('uv')
    if uv is None:
        candidate = Path.home() / '.local/bin/uv'
        if candidate.is_file():
            uv = str(candidate)
    arguments = ([uv, 'pip', 'install', '--python', sys.executable, '--upgrade', 'yt-dlp']
                 if uv else [sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'])
    try:
        result = run_command(arguments, timeout=180, cancelled=cancelled)
        if not result.success:
            log(Severity.WARNING, 'Update yt-dlp', '\n'.join(result.stderr) or 'Update did not complete.')
        return result.success
    except OSError as error:
        log(Severity.WARNING, 'Update yt-dlp', f'Could not update yt-dlp.\n{error}')
        return False


def download_all(youtube_dl_cfg_path, *, cancelled=lambda: False, report=lambda done, total, message: None) -> bool:
    """Download each INI without changing installed packages."""
    directory = Path(youtube_dl_cfg_path)
    if not directory.is_dir():
        log(Severity.ERROR, 'Batch Youtube Downloader',
            f'Download config directory does not exist: {directory}', popup=True)
        return False
    files = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == '.ini'),
                   key=lambda path: path.name.casefold())
    if not files:
        return True
    success = True
    for index, path in enumerate(files):
        if cancelled():
            return False
        report(index, len(files), f'Downloading {path.stem}…')
        if not download(directory, path, cancelled=cancelled):
            success = False
    report(len(files), len(files), 'Download batch finished.')
    return success


def download(youtube_dl_cfg_path, config_file_path, playlist_reverse=True, playlist_end=None, *, cancelled=lambda: False) -> bool:
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
        result = run_command(arguments, cancelled=cancelled)
        if not result.success:
            log(Severity.ERROR, 'Youtube Downloader', '\n'.join(result.stderr) or 'Download did not complete.')
            return False
    except (OSError, ValueError, KeyError, ConfigError) as error:
        log(Severity.ERROR, 'Youtube Downloader', f'Download failed: {error}', popup=True)
        return False
    log(Severity.INFO, 'Youtube Downloader', 'Download command completed.')
    return True
