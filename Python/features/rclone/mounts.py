"""
Mount management for the Logistics rclone feature.
"""

import time
from pathlib import Path

import config

from commonUtils import dirUtils, linkUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from . import configuration, executable


def clear_mounts() -> None:
    """
    Clear stale Logistics rclone mount directories on Windows.

    rclone network mounts normally clean themselves up, but stale mount
    directories can remain on Windows if the application exits unexpectedly.
    """

    if get_os() != OS.WIN:
        return

    logistics_cfg = config.LogisticsConfig()
    mount_directory = dirUtils.Directory(logistics_cfg.path_remote_network_mount)

    if not mount_directory.is_dir():
        return

    directories = mount_directory.list_directories()

    for directory in directories:
        if directory.path.is_symlink():
            linkUtils.delete_symbolic_link(directory.path)

        elif not directory.path.is_junction() and directory.is_dir_empty():
            directory.delete()


def mount_remote(remote_name, mount_path, timeout=None) -> None:
    """Mount a specific rclone remote at the given path."""

    log(Severity.INFO, "mount_remote", f'Mounting "{remote_name}" at path "{mount_path}"...')

    rclone_path = executable.get_rclone_path()
    mount_cmd = f'"{rclone_path}" mount '

    if timeout is not None:
        mount_cmd += f"--attr-timeout={timeout}s "

    mount_cmd += f"{remote_name}: {mount_path}"

    match get_os():
        case OS.MAC | OS.LINUX:
            Path(mount_path).mkdir(parents=True, exist_ok=True)

    cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False)


def get_rclone_remote_mount_paths() -> list[str]:
    """Return the expected mount paths for supported rclone.conf remotes."""

    network_remote_mount_path = config.LogisticsConfig().path_remote_network_mount
    rclone_conf_remote_credentials = configuration.get_rclone_conf_remote_credentials_dict()

    mount_paths = []

    for remote_name in rclone_conf_remote_credentials:
        if "Dropbox" in remote_name or "gdrive" in remote_name:
            continue

        mount_paths.append(str(Path(network_remote_mount_path, remote_name)))

    return mount_paths


def mount_all_rclone_conf_remotes(timeout=None, wait_until_mounted=False) -> None:
    """Mount all supported rclone.conf remotes."""

    network_remote_mount_path = Path(config.LogisticsConfig().path_remote_network_mount)
    network_remote_mount_path.mkdir(parents=True, exist_ok=True)

    mount_paths = get_rclone_remote_mount_paths()

    if not mount_paths:
        log(Severity.WARNING, "mount_all_rclone_conf_remotes", "No rclone remotes found to mount")
        return

    for mount_path in mount_paths:
        remote_name = Path(mount_path).name
        mount_remote(remote_name, mount_path, timeout)

    if not wait_until_mounted:
        log(Severity.DEBUG, "mount_all_rclone_conf_remotes", "Mount commands started, proceeding without waiting")
        return

    log(Severity.INFO, "mount_all_rclone_conf_remotes", "Waiting for all rclone remotes to mount")

    while not all(Path(path).exists() for path in mount_paths):
        time.sleep(0.01)

    log(Severity.INFO, "mount_all_rclone_conf_remotes", "All rclone remotes successfully mounted")


def initialize() -> None:
    """Initialize the optional rclone mounting capability."""

    clear_mounts()
    mount_all_rclone_conf_remotes(timeout=2)