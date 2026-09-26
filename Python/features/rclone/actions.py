"""
Actions for the Logistics rclone feature.
"""

from pathlib import Path

import config

from commonUtils import dirUtils
from commonUtils.debugUtils import Severity, log

from features.rclone import sync as rclone_sync
from models.local_folder import LocalFolder


def pull_remote(remote_name: str, config_path: str | Path) -> None:
    """Pull an rclone remote to its matching local Logistics folder."""

    source_path = remote_name + ':'
    destination_path = Path(
        config.LogisticsConfig().path_remote_local,
        remote_name
    )

    rclone_sync.rclone_sync(
        source_path,
        destination_path,
        config_path=config_path
    )


def push_to_cloud(
    folder: LocalFolder,
    config_path: str | Path,
    track_renames: bool = False
) -> None:
    """Push a local Logistics folder to its rclone remote."""

    source_path = folder.path
    destination_path = folder.name + ':'

    rclone_sync.rclone_sync(
        source_path,
        destination_path,
        config_path=config_path,
        track_renames=track_renames
    )


def push_specific_directory(
    folder: LocalFolder,
    config_path: str | Path,
    directory_path: str,
    bandwidth_limit: str | None = None
) -> bool:
    """Push a specific directory into a Logistics folder's rclone remote."""

    directory = dirUtils.Directory(Path(directory_path))

    if not directory.is_dir():
        log(
            Severity.ERROR,
            'Push Individual Folder',
            'The path you have given is not a valid directory!',
            popup=True
        )
        return False

    if bandwidth_limit == '':
        bandwidth_limit = None

    specific_directory_name = directory.path.name
    destination_path = folder.name + ':' + specific_directory_name

    rclone_sync.rclone_sync(
        directory.path,
        destination_path,
        config_path=config_path,
        bw_limit=bandwidth_limit
    )

    return True
