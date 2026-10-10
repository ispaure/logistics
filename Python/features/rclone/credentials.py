"""
Credential management for the Logistics rclone feature.
"""

from pathlib import Path
from typing import cast
from tempfile import TemporaryDirectory

import config

from commonUtils.filesystem import directories as dirUtils, files as fileUtils
from commonUtils import ui
from commonUtils.archives import legacy as zipUtils
from commonUtils.runtime.diagnostics import Severity, log, print_debug_msg
from commonUtils.formats import txtType

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


def get_credential_package_directories() -> tuple[Path, ...]:
    """Combine checkout credentials with Marc's existing Dropbox credential folder.

    The optional Dropbox location is read-only discovery: never create it, copy
    packages, or use it as a software source.
    """
    from commonUtils.runtime.helpers import get_marc_dropbox_root
    local = config.LogisticsConfig().path_logistics_remote_cred
    dropbox = get_marc_dropbox_root() / 'Software/GIT/logistics/RemoteCredentials'
    roots = [local]
    if dropbox.is_dir() and dropbox.resolve() != local.resolve():
        roots.append(dropbox)
    return tuple(roots)


def get_logistics_remote_credentials_zip_lst() -> list[fileUtils.File]:
    """Return packages from all existing credential roots, deduplicated by path."""
    from commonUtils.filesystem.traversal import scan_directory, natural_path_key
    paths = set()
    for root in get_credential_package_directories():
        paths.update(path.resolve() for path in scan_directory(root, mask='*.zip', recursive=True))
    return [fileUtils.File(path) for path in sorted(paths, key=natural_path_key)]


def get_loaded_credential_config_paths() -> list[Path]:
    """Return available rclone configs independently of original ZIP packages."""

    # Generated configs remain usable after the original ZIP is moved away.
    return configuration.get_all_conf_paths()


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
    config_path = configuration.get_credential_config_path(zip_path)
    workspace_root = Path(logistics_cfg.temp_path)
    workspace_root.mkdir(parents=True, exist_ok=True)
    # Per-operation private workspaces avoid mixing concurrent credential sets.
    with TemporaryDirectory(prefix='logistics-credentials-', dir=workspace_root,
                            ignore_cleanup_errors=True) as workspace:
        extract_dir = Path(workspace)
        if not zipUtils.unzip_file(zip_path, extract_dir, zip_pw):
            ui.display_msg_box_ok('Load Remote Credential',
                'Password is invalid or the credential archive could not be extracted.')
            return False
        if not write_remote_credentials_to_config(extract_dir, config_path):
            return False
        print_debug_msg(f'Successfully loaded remote credentials to "{config_path.name}"!', True)
        return True
