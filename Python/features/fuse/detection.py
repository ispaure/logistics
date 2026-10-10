"""
Platform FUSE dependency detection for the Logistics FUSE feature.
"""

import os
import shutil
from pathlib import Path

from services import software

from commonUtils.runtime.platform import OS, get_os



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

    match get_os():
        case OS.MAC:
            return software.get_software('macfuse')[1]
        case OS.WIN:
            return software.get_software('winfsp')[1]
        case OS.LINUX:
            return None
        case _:
            return None


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
