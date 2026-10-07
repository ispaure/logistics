"""Argument construction for mount operations and bounded directory probes."""

import math
from pathlib import Path
import sys

from commonUtils.osUtils import OS

READY_MARKER = '__LOGISTICS_RCLONE_MOUNT_READY__'


def timeout_seconds(value) -> float:
    seconds = float(value)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Timeout must be finite and nonnegative')
    return seconds


def validate_remote_name(name: str) -> None:
    if (not isinstance(name, str) or not name or name.startswith('-') or name in ('.', '..')
            or any(character in name for character in '/\\:')
            or any(ord(character) < 32 for character in name)):
        raise ValueError(f'Invalid remote folder name: {name!r}')


def mount_arguments(executable: Path, remote_name: str, config_path: Path,
                    mount_path: Path, platform: OS, attr_timeout=None) -> list[str]:
    validate_remote_name(remote_name)
    arguments = [str(executable), '--config', str(config_path), 'mount']
    if attr_timeout is not None:
        value = timeout_seconds(attr_timeout)
        arguments.append(f'--attr-timeout={value:g}s')
    arguments.extend([f'{remote_name}:', str(mount_path)])
    if platform in (OS.MAC, OS.LINUX):
        arguments.append('--daemon')
    return arguments


def probe_arguments(path: Path) -> list[str]:
    # Directory enumeration runs in a child so a stale filesystem can time out.
    code = ('import os,sys; '
            'entries=os.scandir(sys.argv[1]); next(entries,None); entries.close(); '
            f'print({READY_MARKER!r})')
    return [sys.executable, '-c', code, str(path)]
