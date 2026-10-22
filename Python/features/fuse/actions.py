"""
User-facing FUSE actions for rclone remotes.
"""

import subprocess
from pathlib import Path

from commonUtils import ui
from commonUtils.runtime.diagnostics import Severity, log
from commonUtils.runtime.platform import OS, get_os
from models.remote_folder import RemoteFolder

from features.fuse import detection, mounts
from services import software


def launch_installer() -> bool:
    """Launch the bundled macFUSE or WinFsp installer for the current platform."""

    dependency_name = detection.get_dependency_name()
    installer_path = detection.get_installer_path()

    if installer_path is None:
        ui.display_msg_box_ok(
            f'{dependency_name} Required',
            'The FUSE support required by rclone mount is not currently available. '
            'Install FUSE through your distribution package manager and ensure /dev/fuse '
            'and fusermount3 (or fusermount) are available, then retry the mount.'
        )
        return False

    installer_path = software.ensure_software('macfuse' if get_os() == OS.MAC else 'winfsp', install=True)
    if installer_path is None:
        return False

    log(
        Severity.INFO,
        'FUSE',
        f'Launching {dependency_name} installer: "{installer_path}"'
    )

    match get_os():
        case OS.MAC:
            arguments = ['open', str(installer_path)]
        case OS.WIN:
            arguments = ['msiexec.exe', '/i', str(installer_path)]
        case _:
            return False

    try:
        subprocess.Popen(arguments)
    except OSError as error:
        ui.display_msg_box_ok(f'{dependency_name} Installer Failed', str(error))
        return False
    return True


def mount_and_open_remote(
    remote_name: str,
    config_path: str | Path
) -> bool:
    """Mount one rclone remote on demand and open its mounted directory."""

    if not detection.is_installed():
        launch_installer()
        return False

    # Dependency prompts belong to the GUI thread, before starting the worker.
    from features.rclone.executable import ensure_rclone
    rclone_path = ensure_rclone()
    if rclone_path is None:
        return False
    from desktop.dialogs.tool_dialog import ToolDialog

    class MountDialog(ToolDialog):
        def __init__(self):
            super().__init__('Open remote mount', f'Mount {remote_name} and check that it responds.',
                             'Mount and open', False)

        def _execute(self):
            if self.busy:
                return
            self._run_background(
                lambda report, cancelled: mounts.ensure_remote_mounted(
                    remote_name, config_path, attr_timeout=2, wait_timeout=10,
                    rclone_path=rclone_path, cancelled=cancelled), self._mounted,
                cancel_text='Cancel after mount attempt')

        def _mounted(self, mount_path):
            if self.task.cancelled.is_set():
                self.task.message.setText('Cancelled. A completed mount remains mounted; no folder was opened.')
            elif mount_path is None:
                self.task.message.setText(f'Mount did not become ready. Expected location: {mounts.get_remote_mount_path(remote_name, config_path)}')
            else:
                RemoteFolder(mount_path).open()
                self.task.message.setText(f'Opened {mount_path}')

    dialog = MountDialog()
    dialog._execute()
    dialog.exec()
    dialog.deleteLater()
    return True
