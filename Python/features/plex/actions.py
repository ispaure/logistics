"""
Actions for the Logistics Plex feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
import subprocess
import shutil
from zipfile import BadZipFile

import config

from commonUtils import ui
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os

from features.plex import detection as plex_detection
from features.plex import folders as plex_folders
from features.rclone import sync as rclone_sync


# ----------------------------------------------------------------------------------------------------------------------
# FOLDER ACTIONS

def get_remote_cls_pmsdata(remote_cls):
    """Return the remote -PMSDATA folder associated with a Logistics folder."""

    return plex_folders.get_remote_pms_data_folder(remote_cls)


def get_local_cls_pmsdata(remote_cls):
    """Return the local -PMSDATA folder associated with a Logistics folder."""

    return plex_folders.get_local_pms_data_folder(remote_cls)


def open_dir_remote_cls_pmsdata(remote_cls):
    """Open the remote -PMSDATA folder."""

    get_remote_cls_pmsdata(remote_cls).open()


def open_dir_local_cls_pmsdata(remote_cls):
    """Open the local -PMSDATA folder."""

    get_local_cls_pmsdata(remote_cls).open()


def clear_local_pmsdata(remote_cls):
    """Delete the contents of the local -PMSDATA folder."""

    path = Path(get_local_cls_pmsdata(remote_cls).path)
    if path.is_symlink() or path.is_junction():
        raise ValueError(f'Cannot clear a linked package directory: {path}')
    if path.exists():
        for child in path.iterdir():
            if child.is_symlink() or child.is_junction() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)


# ----------------------------------------------------------------------------------------------------------------------
# SYNC ACTIONS

def pull_pms(remote_cls, config_path: str | Path):
    """Pull the remote -PMSDATA folder to its local location."""

    remote_cls_pmsdata = get_remote_cls_pmsdata(remote_cls)

    source_path = remote_cls_pmsdata.name + ':'
    destination_path = Path(config.LogisticsConfig().path_remote_local, remote_cls_pmsdata.name)

    rclone_sync.rclone_sync(
        source_path,
        destination_path,
        config_path=config_path
    )


def push_pms(remote_cls, config_path: str | Path):
    """Push the local -PMSDATA folder to its remote location."""

    local_cls_pmsdata = get_local_cls_pmsdata(remote_cls)

    source_path = local_cls_pmsdata.path
    destination_path = local_cls_pmsdata.name + ':'

    rclone_sync.rclone_sync(
        source_path,
        destination_path,
        config_path=config_path
    )


# ----------------------------------------------------------------------------------------------------------------------
# PACKAGE ACTIONS

def _seven_zip(platform):
    if platform != OS.WIN:
        return None
    directory = Path(config.LogisticsConfig().path_logistics_software_win, '7-zip')
    for name in ('7z.exe', '7z'):
        if (directory / name).is_file():
            return directory / name
    raise FileNotFoundError(f'7-Zip was not found in {directory}')


def unpackage_pms(remote_cls) -> bool:
    """Restore staged data; failed extraction leaves the installation intact."""
    from features.plex import packages
    tool = 'Unpackage Plex Media Server'
    try:
        package = Path(get_local_cls_pmsdata(remote_cls).path)
        destination = plex_detection.get_pms_data_path()
        if destination is None:
            raise ValueError('Could not determine the Plex Media Server data directory.')
        platform = get_os()
        preferences = None
        if platform in (OS.WIN, OS.MAC):
            preferences = package / ('pms_registry.reg' if platform == OS.WIN else packages.PLIST_NAME)
            if not preferences.is_file():
                if not ui.display_msg_box_ok_cancel(tool, 'Server settings are missing. Restore data without them?'):
                    return False
                preferences = None
        previous = packages.restore_data(package, destination, platform,
                                         _seven_zip(platform), preferences)
        if previous is not None:
            log(Severity.INFO, tool, f'Previous server data retained at: {previous}')
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, BadZipFile) as error:
        log(Severity.ERROR, tool, f'Restore failed: {error}', popup=True)
        return False
    log(Severity.INFO, tool, 'Plex Media Server data restored.')
    return True


def package_pms(remote_cls) -> bool:
    """Build the complete package before replacing previous archive files."""
    from features.plex import packages
    tool = 'Package Plex Media Server'
    try:
        source = plex_detection.get_pms_data_path()
        if source is None:
            raise ValueError('Could not determine the Plex Media Server data directory.')
        destination = Path(get_local_cls_pmsdata(remote_cls).path)
        platform = get_os()
        preferences = Path.home() / 'Library/Preferences' / packages.PLIST_NAME if platform == OS.MAC else None
        packages.package_data(source, destination, platform, _seven_zip(platform), preferences)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, BadZipFile) as error:
        log(Severity.ERROR, tool, f'Packaging failed: {error}', popup=True)
        return False
    log(Severity.INFO, tool, 'Plex Media Server packaging completed.')
    return True
