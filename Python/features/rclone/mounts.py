"""
Mount management for the Logistics rclone feature.
"""

import config

from commonUtils import dirUtils, linkUtils
from commonUtils.osUtils import OS, get_os

from pathlib import Path

from commonUtils import dirUtils, linkUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from . import executable


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
        # Symbolic links can always be safely removed without touching their targets.
        if directory.path.is_symlink():
            linkUtils.delete_symbolic_link(directory.path)

        # Empty real directories can also be safely removed.
        elif not directory.path.is_junction() and directory.is_dir_empty():
            directory.delete()


def mount_remote(remote_name, mount_path, timeout=None) -> None:
    """
    Mount a specific rclone remote at the given path.
    """

    log(
        Severity.INFO,
        "mount_remote",
        f'Mounting "{remote_name}" at path "{mount_path}"...',
    )

    rclone_path = executable.get_rclone_path()

    mount_cmd = f'"{rclone_path}" mount '

    if timeout is not None:
        mount_cmd += f"--attr-timeout={timeout}s "

    mount_cmd += f"{remote_name}: {mount_path}"

    # On macOS and Linux, the mount path must exist before mounting.
    match get_os():
        case OS.MAC | OS.LINUX:
            Path(mount_path).mkdir(parents=True, exist_ok=True)

    cmdShellWrapper.exec_cmd(mount_cmd, wait_for_output=False)
