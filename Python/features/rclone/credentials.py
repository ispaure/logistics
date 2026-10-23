"""
Credential management for the Logistics rclone feature.
"""

from pathlib import Path

import config

from commonUtils.filesystem import files as fileUtils
from commonUtils import ui
from commonUtils.runtime.diagnostics import print_debug_msg

from . import configuration


def get_credential_package_directories() -> tuple[Path, ...]:
    """Combine checkout credentials with Marc's existing Dropbox credential folder.

    The optional Dropbox location is read-only discovery: never create it, copy
    packages, or use it as a software source.
    """
    from services.personal_paths import get_marc_dropbox_root
    local = config.LogisticsConfig().path_logistics_remote_cred
    dropbox = get_marc_dropbox_root() / 'Software/GIT/logistics/Credentials/rclone'
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
    from . import session
    return configuration.get_all_conf_paths() + session.paths()


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
    except Exception:
        ui.display_msg_box_ok('Load Remote Credential',
            'Could not load the credential ZIP. Check the password and local file access. Every credential TXT must be password-protected.')
        return False
    print_debug_msg(f'Successfully loaded remote credentials to "{config_path.name}"!', True)
    return True
