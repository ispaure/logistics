"""
Credential management for the Logistics rclone feature.
"""

from pathlib import Path

import config

from commonUtils.filesystem import files as fileUtils
from commonUtils import ui
from commonUtils.runtime.diagnostics import print_debug_msg

from . import configuration
from .diagnostics import report_failure


def get_credential_package_directories() -> tuple[Path, ...]:
    """Use Marc's existing Dropbox credential folder, otherwise the local folder.

    Select one package root without creating the optional Dropbox location.
    """
    from services.personal_paths import get_marc_dropbox_root
    local = config.LogisticsConfig().path_logistics_remote_cred
    dropbox = get_marc_dropbox_root() / 'Software/GIT/logistics/Credentials/rclone'
    if dropbox.is_dir() and dropbox.resolve() != local.resolve():
        return (dropbox,)
    return (local,)


def get_logistics_remote_credentials_zip_lst(*, directories=None, cancelled=lambda: False) -> list[fileUtils.File]:
    """Return packages from the selected credential folder."""
    from commonUtils.filesystem.traversal import scan_directory, natural_path_key
    paths = set()
    for root in get_credential_package_directories() if directories is None else directories:
        if not root.is_dir():
            continue
        paths.update(path.resolve() for path in scan_directory(
            root, mask='*.zip', recursive=True, cancelled=cancelled))
    return [fileUtils.File(path) for path in sorted(paths, key=natural_path_key)]


def get_loaded_credential_config_paths() -> list[Path]:
    """Return available rclone configs independently of original ZIP packages."""

    # Generated configs remain usable after the original ZIP is moved away.
    from . import session, desktop_catalog
    saved = configuration.get_all_conf_paths()
    active = session.paths()
    locked = [path for path in desktop_catalog.contexts()
              if path not in active and path.with_suffix('.conf') not in saved]
    return saved + active + locked


def load_remote_from_zip_to_config(zip_path: str | Path, zip_pw: str, *, remember=True) -> bool:
    """
    Validate a credential archive and publish its explicit saved config or session.

    The credential ZIP is never modified or deleted.
    """

    zip_path = Path(zip_path)
    from .desktop_service import service
    from .desktop_credentials import DesktopCredentialLoad
    config_path = configuration.get_credential_config_path(zip_path)
    if not remember:
        config_path = config_path.with_suffix('.session')
    try:
        service.credentials.load(DesktopCredentialLoad(zip_path, config_path, remember), zip_pw)
    except Exception as error:
        report_failure('load desktop credential package', error)
        ui.display_msg_box_ok('Load Remote Credential',
            'Could not load the credential ZIP. Check the password and local file access. Every credential TXT must be password-protected.')
        return False
    print_debug_msg(f'Successfully loaded remote credentials to "{config_path.name}"!', True)
    return True


def import_credential_package(source, *, cancelled=lambda: False):
    """Copy a bounded ZIP into the configured package folder without replacing one."""
    from io import BytesIO
    from zipfile import is_zipfile
    from commonUtils.persistence import atomic_write_bytes
    from commonUtils.runtime.operations import check_cancelled
    source = Path(source)
    if source.suffix.casefold() != '.zip':
        raise ValueError('Choose a .zip credential package.')
    check_cancelled(cancelled)
    with source.open('rb') as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError('Credential ZIPs are limited to 1 MiB.')
    if not is_zipfile(BytesIO(content)):
        raise ValueError('This file is not a valid ZIP archive.')
    check_cancelled(cancelled)
    root = get_credential_package_directories()[0]
    destination = root / (source.stem + '.zip')
    if destination.is_symlink():
        raise ValueError('The destination package is a symbolic link. Choose a different ZIP name.')
    if destination.exists():
        with destination.open('rb') as stream:
            existing = stream.read(1024 * 1024 + 1)
        if existing == content:
            return destination.resolve()
        raise FileExistsError('A different credential ZIP has this name. Rename your ZIP before importing it.')
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(destination, content, overwrite=False, validate=lambda: check_cancelled(cancelled))
    return destination.resolve()
