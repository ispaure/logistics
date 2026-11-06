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


def push_seasons(folder: LocalFolder, config_path: str | Path, *, cancelled=None, executable_path=None, review=False):
    """Push matching seasons, counting a reviewed launch once it is accepted."""
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.transfers.launch import SyncOutcome, SyncState
    from features.rclone.transfers.workflow import sync_transfer

    for source in _season_paths(folder, directory):
        if cancelled is not None and cancelled():
            return False
        relative = source.resolve().relative_to(Path(folder.path).resolve()).as_posix()
        destination = f'{folder.name}:{relative}'
        log(Severity.INFO, 'YouTube Sync', f'Pushing {source} to {destination}')
        result = sync_transfer(source, destination, operation='Push', review=review,
                               config_path=config_path, wait_for_output=not review,
                               **({'cancelled': cancelled} if cancelled is not None else {}),
                               **({'executable_path': executable_path} if executable_path is not None else {}))
        if not isinstance(result, SyncOutcome):
            return False
        if result.state is not SyncState.SUCCEEDED and not (review and result.state is SyncState.STARTED):
            return False
    return True


def push_config(folder: LocalFolder, config_path: str | Path, *, review=False):
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.transfers.workflow import sync_transfer
    relative = directory.relative_to(folder.path).as_posix()
    return sync_transfer(directory, f'{folder.name}:{relative}',
                         config_path=config_path, operation='Push', review=review)


def pull_config(folder: LocalFolder, config_path: str | Path, *, review=False):
    directory = _config_directory(folder)
    if directory is None:
        return False
    from features.rclone.transfers.workflow import sync_transfer
    relative = directory.relative_to(folder.path).as_posix()
    return sync_transfer(f'{folder.name}:{relative}', directory,
                         config_path=config_path, operation='Pull', review=review)
