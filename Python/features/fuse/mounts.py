"""
Mount management for the Logistics rclone feature.
"""

import os
import shutil
import time
import subprocess
from pathlib import Path

import config

from commonUtils.debugUtils import Severity, log
from commonUtils.osUtils import OS, get_os

from features.rclone import configuration, executable
from .commands import (
    READY_MARKER, mount_arguments, probe_arguments, timeout_seconds, validate_remote_name,
)


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
    mount_directory = Path(logistics_cfg.path_remote_network_mount)

    if mount_directory.is_symlink() or mount_directory.is_junction() or not mount_directory.is_dir():
        return

    for path in mount_directory.iterdir():
        if path.is_symlink() or path.is_junction() or os.path.ismount(path):
            continue
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                continue  # Nonempty or unavailable directories remain untouched.


def get_remote_mount_path(remote_name: str) -> Path:
    """Return the expected local mount path for one rclone remote."""

    validate_remote_name(remote_name)
    return config.LogisticsConfig().path_remote_network_mount / remote_name


def is_mount_path_mounted(mount_path: Path) -> bool:
    """Return whether a path is currently acting as a filesystem mount point."""

    if not mount_path.exists():
        return False

    if os.path.ismount(mount_path):
        return True

    if get_os() == OS.WIN and mount_path.is_junction():
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

    if probe_timeout <= 0:
        return False
    try:
        result = subprocess.run(probe_arguments(mount_path), capture_output=True,
                                text=True, timeout=probe_timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and READY_MARKER in result.stdout.splitlines()


def is_remote_ready(remote_name: str, probe_timeout: float = 2) -> bool:
    """Return whether one rclone remote is mounted and its root can be read."""

    return is_mount_path_ready(
        get_remote_mount_path(remote_name),
        probe_timeout=probe_timeout
    )


def mount_remote(
    remote_name: str,
    config_path: str | Path,
    mount_path: Path,
    timeout=None
) -> bool:
    """Start mounting a specific rclone remote at the given path."""

    validate_remote_name(remote_name)
    if get_os() not in (OS.WIN, OS.MAC, OS.LINUX):
        return False
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

    if remote_name not in configuration.get_rclone_remote_names(config_path):
        log(Severity.ERROR, 'mount_remote', f'No rclone remote named "{remote_name}" is configured')
        return False

    log(Severity.INFO, 'mount_remote', f'Mounting "{remote_name}" at path "{mount_path}"...')

    rclone_path = executable.get_rclone_path()

    if not rclone_path.is_file():
        log(Severity.ERROR, 'mount_remote', f'rclone executable does not exist: "{rclone_path}"')
        return False

    arguments = mount_arguments(rclone_path, remote_name, Path(config_path),
                                mount_path, get_os(), timeout)
    if mount_path.is_symlink() or mount_path.is_junction():
        log(Severity.ERROR, 'mount_remote', f'Mount path is a link: {mount_path}')
        return False
    if mount_path.exists() and (not mount_path.is_dir() or any(mount_path.iterdir())):
        log(Severity.ERROR, 'mount_remote', f'Mount path is not an empty directory: {mount_path}')
        return False
    mount_path.parent.mkdir(parents=True, exist_ok=True)
    if get_os() in (OS.MAC, OS.LINUX):
        mount_path.mkdir(parents=True, exist_ok=True)
    try:
        if get_os() in (OS.MAC, OS.LINUX):
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=15)
            if result.returncode:
                log(Severity.ERROR, 'mount_remote', f'rclone mount failed: {result.stderr.strip()}')
                _remove_empty_mount_path(mount_path)
                return False
        else:
            subprocess.Popen(arguments, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        log(Severity.ERROR, 'mount_remote', str(error))
        _remove_empty_mount_path(mount_path)
        return False
    return True


def unmount_remote(remote_name: str, wait_timeout: float = 5) -> bool:
    """
    Unmount one Logistics rclone mount.

    This is primarily used to recover a stale/unresponsive Unix FUSE mount
    before attempting a fresh mount.
    """

    wait_timeout = timeout_seconds(wait_timeout)
    mount_path = get_remote_mount_path(remote_name)

    if not is_mount_path_mounted(mount_path):
        _remove_empty_mount_path(mount_path)
        return True

    match get_os():
        case OS.MAC:
            arguments = ['umount', str(mount_path)]

        case OS.LINUX:
            fusermount = shutil.which('fusermount3') or shutil.which('fusermount')

            if fusermount is None:
                log(
                    Severity.ERROR,
                    'unmount_remote',
                    'Could not find fusermount3 or fusermount'
                )
                return False

            arguments = [fusermount, '-u', str(mount_path)]

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

    if wait_timeout <= 0:
        return False
    deadline = time.monotonic() + wait_timeout
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=wait_timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        log(Severity.ERROR, 'unmount_remote', str(error))
        return False
    if result.returncode:
        log(Severity.ERROR, 'unmount_remote', f'Unmount failed: {result.stderr.strip()}')
        return False
    while True:
        if not is_mount_path_mounted(mount_path):
            _remove_empty_mount_path(mount_path)
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(0.1, remaining))
    log(Severity.ERROR, 'unmount_remote', f'Timed out unmounting {remote_name}')
    return False


def wait_until_remote_ready(remote_name: str, timeout: float = 15) -> bool:
    """Wait until one remote is both mounted and able to service a root directory read."""

    deadline = time.monotonic() + timeout_seconds(timeout)
    while (remaining := deadline - time.monotonic()) > 0:
        if is_remote_ready(remote_name, probe_timeout=min(2, remaining)):
            return True
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    return False


def ensure_remote_mounted(
    remote_name: str,
    config_path: str | Path,
    attr_timeout=None,
    wait_timeout: float = 15
) -> Path | None:
    """Ensure one rclone remote is mounted, responsive, and ready to open."""

    wait_timeout = timeout_seconds(wait_timeout)
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

    if not mount_remote(
        remote_name,
        config_path,
        mount_path,
        timeout=attr_timeout
    ):
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


def get_rclone_remote_mount_paths(config_path: str | Path) -> list[str]:
    """Return expected mount paths for supported remotes in one config."""

    network_remote_mount_path = config.LogisticsConfig().path_remote_network_mount
    remote_names = configuration.get_rclone_remote_names(config_path)

    mount_paths = []

    for remote_name in remote_names:
        if 'Dropbox' in remote_name or 'gdrive' in remote_name:
            continue

        validate_remote_name(remote_name)
        mount_paths.append(str(network_remote_mount_path / remote_name))

    return mount_paths


def mount_all_rclone_conf_remotes(
    config_path: str | Path,
    timeout=None,
    wait_until_mounted=False,
    wait_timeout: float = 15
) -> bool:
    """
    Mount all supported remotes from one explicit rclone config.

    Retained as an explicit utility. Logistics no longer calls this automatically at startup.
    """

    wait_timeout = timeout_seconds(wait_timeout)
    mount_paths = get_rclone_remote_mount_paths(config_path)

    if not mount_paths:
        log(Severity.WARNING, 'mount_all_rclone_conf_remotes', 'No rclone remotes found to mount')
        return True

    for mount_path_str in mount_paths:
        mount_path = Path(mount_path_str)
        if not mount_remote(mount_path.name, config_path, mount_path, timeout):
            return False

    if not wait_until_mounted:
        log(Severity.DEBUG, 'mount_all_rclone_conf_remotes', 'Mount commands started, proceeding without waiting')
        return True

    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'Waiting for all rclone remotes to become ready')

    deadline = time.monotonic() + wait_timeout
    for path in mount_paths:
        if not wait_until_remote_ready(Path(path).name, timeout=max(0, deadline - time.monotonic())):
            return False
    log(Severity.INFO, 'mount_all_rclone_conf_remotes', 'All rclone remotes successfully mounted')
    return True


def initialize() -> None:
    """
    Initialize rclone mount support without mounting remotes.

    Remotes are mounted on demand from the Folders UI. Startup only removes stale
    Windows mount directories left behind by interrupted previous sessions.
    """

    clear_mounts()


def _remove_empty_mount_path(mount_path: Path) -> None:
    """Remove a failed Unix mount directory when it is still an ordinary empty directory."""

    if (get_os() == OS.WIN or mount_path.is_symlink() or mount_path.is_junction()
            or not mount_path.is_dir() or os.path.ismount(mount_path)):
        return

    try:
        mount_path.rmdir()
    except OSError:
        pass
