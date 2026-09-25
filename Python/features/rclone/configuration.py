"""
rclone configuration handling for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils import fileUtils
from commonUtils.fileTypes import txtType


def get_rclone_conf_path() -> Path:
    """Return the current user's rclone configuration file path."""

    return Path(fileUtils.get_user_home_dir(), '.config', 'rclone', 'rclone.conf')


def ensure_rclone_conf() -> Path:
    """Ensure the current user's rclone configuration file exists and return its path."""

    rclone_conf_path = get_rclone_conf_path()
    rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
    rclone_conf_path.touch(exist_ok=True)

    return rclone_conf_path


def get_rclone_remote_names() -> list[str]:
    """Return the remote names currently defined in rclone.conf."""

    rclone_conf_path = get_rclone_conf_path()

    if not rclone_conf_path.is_file():
        return []

    rclone_conf_file = txtType.TXTFile(rclone_conf_path)
    rclone_conf_file.read_lines()

    remote_names = []

    for line in rclone_conf_file.line_lst:
        stripped_line = line.strip()

        if stripped_line.startswith('[') and stripped_line.endswith(']'):
            remote_names.append(stripped_line[1:-1])

    return remote_names


def clear_rclone_conf() -> None:
    """Delete the local rclone.conf file if it exists."""

    rclone_conf_path = get_rclone_conf_path()

    if not rclone_conf_path.is_file():
        return

    fileUtils.File(rclone_conf_path).delete_file()
