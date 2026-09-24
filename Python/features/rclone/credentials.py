"""
Credential management for the Logistics rclone feature.
"""

from pathlib import Path
from typing import cast

import config

from commonUtils import dirUtils, fileUtils
from commonUtils.fileTypes import txtType

from . import configuration


def get_remote_credentials_dict(remote_credentials_dir: str | Path) -> dict:
    """Return rclone remote credentials stored as TXT files in the given directory."""

    remote_credentials_directory = dirUtils.Directory(remote_credentials_dir)
    credential_files = cast(list[txtType.TXTFile], remote_credentials_directory.list_files(filter_extension="txt"))

    credentials = {}

    for file in credential_files:
        lines = file.read_lines()
        remote_name = lines[0][1:-1]
        credentials[remote_name] = lines

    return credentials


def get_logistics_remote_credentials_zip_lst() -> list[fileUtils.File]:
    """Return credential ZIP files available in the Logistics remote credentials directory."""

    logistics_cfg = config.LogisticsConfig()
    remote_credentials_directory = dirUtils.Directory(logistics_cfg.path_logistics_remote_cred)

    return remote_credentials_directory.list_files(filter_extension="zip")


def add_remote_to_rclone_conf(remote_credentials_dir: str | Path) -> None:
    """Add missing remotes from a credential directory to the user's rclone.conf."""

    rclone_conf_path = configuration.get_rclone_conf_path()
    rclone_conf_credentials = configuration.get_rclone_conf_remote_credentials_dict()
    remote_credentials = get_remote_credentials_dict(remote_credentials_dir)

    rclone_conf_file = txtType.TXTFile(rclone_conf_path)
    rclone_conf_file.read_lines()

    for remote_name, remote_lines in remote_credentials.items():
        if remote_name in rclone_conf_credentials:
            continue

        rclone_conf_file.line_lst.extend(remote_lines)
        rclone_conf_file.line_lst.append("")

    rclone_conf_file.write_lines()


def add_logistics_remote_to_rclone_conf() -> None:
    """Add Logistics-provided remote credentials to the user's rclone.conf."""

    logistics_cfg = config.LogisticsConfig()
    add_remote_to_rclone_conf(logistics_cfg.path_logistics_remote_cred)
