"""
FUSE dependency handling and on-demand remote opening for the Logistics rclone feature.
"""

import os
import shlex
import shutil
from pathlib import Path

import config

from commonUtils import ui
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper
from models.remote_folder import RemoteFolder

from . import mounts


MACFUSE_INSTALLER_NAME = 'macfuse-5.0.5.dmg'
WINFSP_INSTALLER_NAME = 'winfsp-1.11.22176.msi'


def get_dependency_name() -> str:
    """Return the platform-specific filesystem dependency name."""

    match get_os():
        case OS.MAC:
            return 'macFUSE'
        case OS.WIN:
            return 'WinFsp'
        case OS.LINUX:
            return 'FUSE'
        case _:
            return 'FUSE'


def is_installed() -> bool:
    """Return whether the platform has the filesystem support required by rclone mount."""

    match get_os():
        case OS.MAC:
            return _is_macfuse_installed()

        case OS.WIN:
            return _is_winfsp_installed()

        case OS.LINUX:
            return _is_linux_fuse_available()

        case _:
            return False


def get_installer_path() -> Path | None:
    """Return the bundled platform installer path, when Logistics provides one."""

    logistics_cfg = config.LogisticsConfig()

    match get_os():
        case OS.MAC:
            return logistics_cfg.path_logistics_software_mac / MACFUSE_INSTALLER_NAME

        case OS.WIN:
            return logistics_cfg.path_logistics_software_win / WINFSP_INSTALLER_NAME

        case OS.LINUX:
            return None

        case _:
            return None


def launch_installer() -> bool:
    """Launch the bundled macFUSE or WinFsp installer for the current platform."""

    dependency_name = get_dependency_name()
    installer_path = get_installer_path()

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

    log(Severity.INFO, 'FUSE', f'Launching {dependency_name} installer: "{installer_path}"')

    match get_os():
        case OS.MAC:
            command = f'open {shlex.quote(str(installer_path))}'

        case OS.WIN:
            command = f'msiexec.exe /i "{installer_path}"'

        case _:
            return False

    cmdShellWrapper.exec_cmd(command, wait_for_output=False)
    return True


def mount_and_open_remote(remote_name: str) -> bool:
    """Mount one rclone remote on demand and open its mounted directory."""

    if not is_installed():
        launch_installer()
        return False

    mount_path = mounts.ensure_remote_mounted(remote_name, attr_timeout=2, wait_timeout=10)

    if mount_path is None:
        ui.display_msg_box_ok(
            'Remote Mount Failed',
            f'Could not mount rclone remote "{remote_name}".\n\n'
            f'Expected mount location:\n{mounts.get_remote_mount_path(remote_name)}'
        )
        return False

    RemoteFolder(mount_path).open()
    return True


def _is_macfuse_installed() -> bool:
    """Return whether macFUSE appears to be installed."""

    return Path('/Library/Filesystems/macfuse.fs').is_dir()


def _is_winfsp_installed() -> bool:
    """Return whether WinFsp appears to be installed in one of its standard locations."""

    install_roots = []

    program_files_x86 = os.environ.get('ProgramFiles(x86)')
    program_files = os.environ.get('ProgramFiles')

    if program_files_x86:
        install_roots.append(Path(program_files_x86) / 'WinFsp')

    if program_files:
        install_roots.append(Path(program_files) / 'WinFsp')

    return any((root / 'bin').is_dir() for root in install_roots)


def _is_linux_fuse_available() -> bool:
    """Return whether the standard Linux FUSE device and helper are available."""

    if not Path('/dev/fuse').exists():
        return False

    return shutil.which('fusermount3') is not None or shutil.which('fusermount') is not None
