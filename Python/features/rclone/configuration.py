"""
rclone configuration handling for the Logistics rclone feature.
"""

from pathlib import Path

from commonUtils import fileUtils
from commonUtils.fileTypes import txtType


def get_rclone_conf_path() -> Path:
    """Return the current user's rclone configuration file path, creating it if needed."""

    rclone_conf_dir = Path(fileUtils.get_user_home_dir(), ".config", "rclone")
    rclone_conf_dir.mkdir(parents=True, exist_ok=True)

    rclone_conf_path = Path(rclone_conf_dir, "rclone.conf")

    if not rclone_conf_path.is_file():
        rclone_conf_path.touch()

    return rclone_conf_path


def get_rclone_conf_remote_credentials_dict() -> dict:
    """Return the remote entries currently defined in rclone.conf."""

    def wrap_up_entry(current_entry_lines, credentials):
        credentials[current_entry_lines[0][1:-1]] = current_entry_lines
        return credentials

    rclone_conf_file = txtType.TXTFile(get_rclone_conf_path())
    rclone_conf_file.read_lines()

    credentials = {}
    current_entry_lines = []

    for line in rclone_conf_file.line_lst:
        if not line:
            continue

        if line[0] == "[":
            if current_entry_lines:
                credentials = wrap_up_entry(current_entry_lines, credentials)

            current_entry_lines = [line]
        else:
            current_entry_lines.append(line)

    if current_entry_lines:
        credentials = wrap_up_entry(current_entry_lines, credentials)

    return credentials


def clear_rclone_conf():
    """
    Deletes the local rclone.conf file, essentially clearing it.
    """
    fileUtils.File(get_rclone_conf_path()).delete_file()
