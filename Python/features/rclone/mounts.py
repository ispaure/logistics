"""
Mount management for the Logistics rclone feature.
"""

import os
import shlex
import shutil
import time
from pathlib import Path

import config

from commonUtils import dirUtils, linkUtils
from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os
from commonUtils.wrappers import cmdShellWrapper

from . import configuration, executable


READY_MARKER = '__LOGISTICS_RCLONE_MOUNT_READY__'


def clear_mounts() -> None:
    """
    Clear stale Logistics rclone mount directories on Windows.

    rclone network mounts normally clean themselves up, but stale mount
    directories can remain on Windows if the application exits unexpectedly.
    Active junction/mount points are left alone.
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


def get_remote_mount_path(remote_name: str) -> Path:
    """Return the expected local mount path for one rclone remote."""

    return config.LogisticsConfig().path_remote_network_mount / remote_name


def is_mount_path_mounted(mount_path: Path) -> bool:
    """Return whether a path is currently acting as a filesystem mount point."""

    if not mount_path.exists():
        return False

    if os.path.ismount(mount_path):
        return True

    if get_os() == OS.WIN and linkUtils.is_junction(mount_path):
        return True

    return False


def is_remote_mounted(remote_name: str) -> bool:
    """Return whether one rclone remote is mounted at its Logistics mount path."""

    return is_mount_path_mounted(get_remote_mount_path(remote_name))


def is_mount_path_ready(mount_path: Path, probe_timeout: float = 2) -> bool:
    """
    Return whether a mounted path is responsive enough to browse.

    A FUSE mount point can become visible to the OS before the mounted filesystem
    is actually ready to service directory requests. It can also remain visible
    briefly as a stale mount after the backing rclone process has failed.

    Probe a directory listing through the mount instead of treating ismount()
    alone as proof that Finder/Explorer can open it.
    """

    if not is_mount_path_mounted(mount_path):
        return False

    match get_os():
        case OS.MAC | OS.LINUX:
            command = (
                f'ls -A {_quote_shell_arg(mount_path)} >/dev/null '
                f'&& printf "{READY_MARKER}\\n"'
            )

        case OS.WIN:
            command = (
                f'dir /b {_quote_shell_arg(mount_path)} >NUL 2>NUL '
                f'&& echo {READY_MARKER}'
            )

        case _:
            return False

    output = cmdShellWrapper.exec_cmd(
        command,
        wait_for_output=True,
        time_out=probe_timeout
    )

    return READY_MARKER in output


def is_remote_ready(remote_name: str, probe_timeout: float = 2) -> bool:
    """Return whether one rclone remote is mounted and its root can be read."""

    return is_mount_path_ready(
        get_remote_mount_path(remote_name),
        probe_timeout=probe_timeout
    )


def mount_remote(remote_name: str, mount_path: Path, timeout=None) -> bool:
    """Start mounting a specific rclone remote at the given path."""

    if is_mount_path_mounted(mount_path):
        if is_mount_path_ready(mount_path):
            log(
                Severity.DEBUG,
                'mount_remote',
                f'"{remote_name}" is already mounted and ready at "{mount_path}"'
            )
            return True

        log(
            Severity.WARNING,
            'mount_remote',
            f'"{remote_name}" has an unresponsive existing mount at "{mount_path}"'
        )
        return False

    if remote_name not in configuration.get_rclone_remote_names():
        log(Severity.ERROR, 'mount_remote', f'No rclone remote named "{remote_name}" is configured')
        return False

    log(Severity.INFO, 'mount_remote', f'Mounting "{remote_name}" at path "{mount_path}"...')

    rclone_path = executable.get_rclone_path()

    if not rclone_path.is_file():
        log(Severity.ERROR, 'mount_remote', f'rclone executable does not exist: "{rclone_path}"')
        return False

    mount_path.parent.mkdir(parents=True, exist_ok=True)

    if get_os() in (OS.MAC, OS.LINUX):
        mount_path.mkdir(parents=True, exist_ok=True)

    command_parts = [
        _quote_shell_arg(rclone_path),
        'mount',
    ]

    if timeout is not None:
        command_parts.append(f'--attr-timeout={timeout}s')

    command_parts.extend([
        _quote_shell_arg(f'{remote_name}:'),
        _quote_shell_arg(mount_path),
    ])

    if get_os() in (OS.MAC, OS.LINUX):
        # rclone's daemon mode waits for the background mount to complete its
        # startup before the launcher exits. This avoids opening Finder against
        # a mount point that has merely appeared but is not ready yet.
        command_parts.append('--daemon')

    command = ' '.join(command_parts)

    if get_os() in (OS.MAC, OS.LINUX):
        cmdShellWrapper.exec_cmd(
            command,
            wait_for_output=True,
            time_out=15
        )
    else:
        cmdShellWrapper.exec_cmd(command, wait_for_output=False)

    return True


def unmount_remote(remote_name: str, wait_timeout: float = 5) -> bool:
    """
    Unmount one Logistics rclone mount.

    This is primarily used to recover a stale/unresponsive Unix FUSE mount
    before attempting a fresh mount.
    """

    mount_path = get_remote_mount_path(remote_name)

    if not is_mount_path_mounted(mount_path):
        _remove_empty_mount_path(mount_path)
        return True

    match get_os():
        case OS.MAC:
            command = f'umount {_quote_shell_arg(mount_path)}'

        case OS.LINUX:
            fusermount = shutil.which('fusermount3') or shutil.which('fusermount')

            if fusermount is None:
                log(
                    Severity.ERROR,
                    'unmount_remote',
                    'Could not find fusermount3 or fusermount'
                )
                return False

            command = f'{_quote_shell_arg(fusermount)} -u {_quote_shell_arg(mount_path)}'

        case OS.WIN:
            log(
                Severity.WARNING,
                'unmount_remote',
                'Automatic recovery of an unresponsive WinFsp mount is not implemented'
            )
            return False

        case _:
            return False

    log(Severity.INFO, 'unmount_remote', f'Unmounting stale remote "{remote_name}" from "{mount_path}"')

    output = cmdShellWrapper.exec_cmd(
        command,
        wait_for_output=True,
        time_out=wait_timeout
    )

    deadline = time.monotonic() + wait_timeout

    while time.monotonic() < deadline:
        if not is_mount_path_mounted(mount_path):
            _remove_empty_mount_path(mount_path)
            return True

        time.sleep(0.1)

    log(
        Severity.ERROR,
        'unmount_remote',
        f'Unable to unmount "{remote_name}" from "{mount_path}". Output: {output}'
    )
    return False


def wait_until_remote_ready(remote_name: str, timeout: float = 15) -> bool:
    """Wait until one remote is both mounted and able to service a root directory read."""

    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if is_remote_ready(remote_name):
            return True

        time.sleep(0.25)

    return is_remote_ready(remote_name)


def ensure_remote_mounted(remote_name: str, attr_timeout=None, wait_timeout: float = 15) -> Path | None:
    """Ensure one rclone remote is mounted, responsive, and ready to open."""

    mount_path = get_remote_mount_path(remote_name)

    if is_remote_ready(remote_name):
        return mount_path

    if is_remote_mounted(remote_name):
        log(
            Severity.WARNING,
            'ensure_remote_mounted',
            f'Remote "{remote_name}" is mounted but unresponsive; attempting a clean remount'
        )

        if not unmount_remote(remote_name):
            return None

    if not mount_remote(remote_name, mount_path, timeout=attr_timeout):
        return None

    if wait_until_remote_ready(remote_name, timeout=wait_timeout):
        return mount_path

    if is_remote_mounted(remote_name):
        unmount_remote(remote_name)

    _remove_empty_mount_path(mount_path)

    log(
        Severity.ERROR,
        'mount_remote',
        f'Timed out waiting for "{remote_name}" to become readable at "{mount_path}"'
    )
    return None


def get_rclone_remote_mount_paths() -> list[str]:
    """Return the expected mount paths for supported rclone.conf remotes."""

    network_remote_mount_path = config.LogisticsConfig().path_remote_network_mount
    remote_names = configuration.get_rclone_remote_names()

    mount_paths = []

    for remote_name in remote_names:
        if 'Dropbox' in remote_name or 'gdrive' in remote_name:
            continue

        mount_paths.append(str(network_remote_mount_path / remote_name))

    return mount_paths


def mount_all_rclone_conf_remotes(timeout=None, wait_until_mounted=False) -> None:
    """
    Mount all supported rclone.conf remotes.

    Retained as an explicit utility. Logistics no longer calls this automatically at startup.
    """

    mount_paths = get_rclone_remote_mount_paths()

    if not mount_paths:
        log(Severity.WARNING, 'mount_all_rclone_conf_remotes', 'No rclone remotes found to mount')
        return

    for mount_path_str in mount_paths:
        mount_path = Path(mount_path_str)
        mount_remote(mount_path.name, mount_path, timeout)

    if not wait_until_mounted:
        log(Severity.DEBUG, 'mount_all_rclone_conf_remotes', 'Mount commands started, proceeding without waiting')
        return

    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'Waiting for all rclone remotes to become ready')

    while not all(is_remote_ready(Path(path).name) for path in mount_paths):
        time.sleep(0.25)

    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'All rclone remotes successfully mounted')


def initialize() -> None:
    """
    Initialize rclone mount support without mounting remotes.

    Remotes are mounted on demand from the Folders UI. Startup only removes stale
    Windows mount directories left behind by interrupted previous sessions.
    """

    clear_mounts()


def _quote_shell_arg(value: str | Path) -> str:
    """Quote one shell argument for the current platform."""

    value_str = str(value)

    if get_os() == OS.WIN:
        return f'"{value_str}"'

    return shlex.quote(value_str)


def _remove_empty_mount_path(mount_path: Path) -> None:
    """Remove a failed Unix mount directory when it is still an ordinary empty directory."""

    if get_os() == OS.WIN or not mount_path.is_dir() or os.path.ismount(mount_path):
        return

    try:
        mount_path.rmdir()
    except OSError:
        pass
