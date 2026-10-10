"""Optional rclone synchronization for download configuration and season folders."""

from pathlib import Path

from commonUtils.runtime.diagnostics import Severity, log
from models.local_folder import LocalFolder
from . import detection


def _config_directory(folder):
    directory = detection.get_config_path(folder)
    if directory is None:
        log(Severity.ERROR, 'YouTube Sync', f'No download configuration found for "{folder.name}"')
    return directory


def _season_paths(folder, directory):
    """Yield season directories inside the local folder, excluding linked paths."""
    root = Path(folder.path).resolve()
    for channel in sorted(directory.parent.iterdir()):
        if channel == directory or channel.is_symlink() or channel.is_junction() or not channel.is_dir():
            continue
        for season in sorted(channel.iterdir()):
            if (season.name.startswith('Season ') and season.name[7:].isdigit()
                    and season.is_dir() and not season.is_symlink() and not season.is_junction()
                    and season.resolve().is_relative_to(root)):
                yield season


def push_seasons(folder: LocalFolder, config_path: str | Path, *, cancelled=None, executable_path=None):
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.sync import rclone_sync

    for source in _season_paths(folder, directory):
        if cancelled is not None and cancelled():
            return False
        relative = source.resolve().relative_to(Path(folder.path).resolve()).as_posix()
        destination = f'{folder.name}:{relative}'
        log(Severity.INFO, 'YouTube Sync', f'Pushing {source} to {destination}')
        if rclone_sync(source, destination, config_path=config_path, wait_for_output=True,
                       **({'cancelled': cancelled} if cancelled is not None else {}),
                       **({'executable_path': executable_path} if executable_path is not None else {})) is False:
            return False
    return True


def push_config(folder: LocalFolder, config_path: str | Path):
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.sync import rclone_sync

    return rclone_sync(directory, f'{folder.name}:{detection.get_config_sub_path(folder)}',
                       config_path=config_path)


def pull_config(folder: LocalFolder, config_path: str | Path):
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.sync import rclone_sync

    return rclone_sync(f'{folder.name}:{detection.get_config_sub_path(folder)}', directory,
                       config_path=config_path)
