"""
User-facing FUSE actions for rclone remotes.
"""

import shlex
from pathlib import Path

from commonUtils import ui
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper
from models.remote_folder import RemoteFolder

from features.fuse import detection, mounts


def launch_installer() -> bool:
    """Launch the bundled macFUSE or WinFsp installer for the current platform."""

    dependency_name = detection.get_dependency_name()
    installer_path = detection.get_installer_path()

    if installer_path is None:
        ui.display_msg_box_ok(
            f'{dependency_name} Required',
            'The FUSE support required by rclone mount is not currently available. '
            'No bundled installer is provided for this platform.'
        )
        return False

    if not installer_path.is_file():
        ui.display_msg_box_ok(
            f'{dependency_name} Installer Missing',
            f'Could not find the bundled installer:\n\n{installer_path}'
        )
        return False

    log(
        Severity.INFO,
        'FUSE',
        f'Launching {dependency_name} installer: "{installer_path}"'
    )

    match get_os():
        case OS.MAC:
            command = f'open {shlex.quote(str(installer_path))}'
        case OS.WIN:
            command = f'msiexec.exe /i "{installer_path}"'
        case _:
            return False

    cmdShellWrapper.exec_cmd(command, wait_for_output=False)
    return True


def mount_and_open_remote(
    remote_name: str,
    config_path: str | Path
) -> bool:
    """Mount one rclone remote on demand and open its mounted directory."""

    if not detection.is_installed():
        launch_installer()
        return False

    mount_path = mounts.ensure_remote_mounted(
        remote_name,
        config_path,
        attr_timeout=2,
        wait_timeout=10
    )

    if mount_path is None:
        ui.display_msg_box_ok(
            'Remote Mount Failed',
            f'Could not mount rclone remote "{remote_name}".\n\n'
            f'Expected mount location:\n'
            f'{mounts.get_remote_mount_path(remote_name)}'
        )
        return False

    RemoteFolder(mount_path).open()
    return True
