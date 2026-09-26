"""
Credential management for the Logistics rclone feature.
"""

from pathlib import Path
from typing import cast

import config

from commonUtils import dirUtils, fileUtils, ui, zipUtils
from commonUtils.debugUtils import Severity, log, print_debug_msg
from commonUtils.fileTypes import txtType

from . import configuration


def get_remote_credentials_dict(remote_credentials_dir: str | Path) -> dict:
    """Return rclone remote credentials stored as TXT files in the given directory."""

    remote_credentials_directory = dirUtils.Directory(remote_credentials_dir)
    credential_files = cast(
        list[txtType.TXTFile],
        remote_credentials_directory.list_files(filter_extension='txt')
    )

    credentials = {}

    for file in credential_files:
        lines = file.read_lines()

        if not lines:
            continue

        remote_name = lines[0][1:-1]
        credentials[remote_name] = lines

    return credentials


def get_logistics_remote_credentials_zip_lst() -> list[fileUtils.File]:
    """Return credential ZIP files available in the Logistics RemoteCredentials directory."""

    logistics_cfg = config.LogisticsConfig()
    remote_credentials_directory = dirUtils.Directory(
        logistics_cfg.path_logistics_remote_cred
    )

    return remote_credentials_directory.list_files(filter_extension='zip')


def get_loaded_credential_config_paths() -> list[Path]:
    """
    Return generated configs for currently available credential ZIP packages.

    A credential package is considered loaded when the same-named .conf exists
    in the rclone configuration directory.
    """

    loaded_configs = []

    for package in get_logistics_remote_credentials_zip_lst():
        config_path = configuration.get_credential_config_path(package.path)

        if config_path.is_file():
            loaded_configs.append(config_path)

    return sorted(loaded_configs, key=lambda path: path.name.casefold())


def write_remote_credentials_to_config(
    remote_credentials_dir: str | Path,
    config_path: str | Path
) -> bool:
    """Write one extracted credential set into one dedicated rclone config."""

    remote_credentials = get_remote_credentials_dict(remote_credentials_dir)

    if not remote_credentials:
        log(
            Severity.ERROR,
            'Load Remote Credential',
            'No rclone credential TXT files were found in the credential package.',
            popup=True
        )
        return False

    config_path = Path(config_path)
    config_file = txtType.TXTFile(config_path)
    config_file.line_lst = []

    for remote_lines in remote_credentials.values():
        config_file.line_lst.extend(remote_lines)
        config_file.line_lst.append('')

    if config_file.line_lst:
        config_file.line_lst.pop()

    config_file.write_lines()
    return True


def load_remote_from_zip_to_config(zip_path: str | Path, zip_pw: str) -> bool:
    """
    Extract one credential archive and write its dedicated same-named .conf.

    The credential ZIP is never modified or deleted.
    """

    logistics_cfg = config.LogisticsConfig()
    zip_path = Path(zip_path)
    extract_dir = Path(logistics_cfg.temp_path, 'UnpackCredentials')
    config_path = configuration.get_credential_config_path(zip_path)

    extract_directory = dirUtils.Directory(extract_dir)

    if extract_directory.is_dir():
        extract_directory.delete_contents()

    try:
        try:
            extracted = zipUtils.unzip_file(zip_path, extract_dir, zip_pw)
        except Exception:
            ui.display_msg_box_ok(
                'Load Remote Credential',
                'Password is invalid or the credential archive could not be opened.'
            )
            return False

        if not extracted:
            ui.display_msg_box_ok(
                'Load Remote Credential',
                'The credential archive could not be extracted.'
            )
            return False

        if not write_remote_credentials_to_config(extract_dir, config_path):
            return False

        print_debug_msg(
            f'Successfully loaded remote credentials to "{config_path.name}"!',
            True
        )
        return True
    finally:
        if extract_directory.is_dir():
            extract_directory.delete_contents()
