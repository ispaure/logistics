"""
Dropbox installation and folder detection helpers.
"""

import json
import os
from pathlib import Path

from commonUtils.debugUtils import Severity, log
from commonUtils.fileUtils import get_user_home_dir
from commonUtils.osUtils import OS, get_os
from models.local_folder import LocalFolder


def _get_info_json_paths() -> list[Path]:
    """Return platform-appropriate Dropbox info.json candidates."""

    home = get_user_home_dir()

    match get_os():
        case OS.WIN:
            candidates = []

            appdata = os.environ.get('APPDATA')
            local_appdata = os.environ.get('LOCALAPPDATA')

            if appdata:
                candidates.append(Path(appdata) / 'Dropbox' / 'info.json')

            if local_appdata:
                candidates.append(Path(local_appdata) / 'Dropbox' / 'info.json')

            return candidates

        case OS.MAC | OS.LINUX:
            return [home / '.dropbox' / 'info.json']

        case _:
            return []


def get_dropbox_roots() -> list[tuple[str, Path]]:
    """
    Return configured Dropbox account roots as (account_name, path) pairs.

    Dropbox's info.json is used instead of assuming a user-specific folder
    name. Missing/unconfigured Dropbox installations simply return no roots.
    """

    info_path = next((path for path in _get_info_json_paths() if path.is_file()), None)

    if info_path is None:
        return []

    try:
        with info_path.open('r', encoding='utf-8') as file:
            info = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        log(
            Severity.WARNING,
            'Dropbox',
            f'Could not read Dropbox configuration "{info_path}": {exc}'
        )
        return []

    roots = []

    for account_name, account_info in info.items():
        if not isinstance(account_info, dict):
            continue

        path_value = account_info.get('path')

        if not path_value:
            continue

        root_path = Path(path_value).expanduser()

        if root_path.is_dir():
            roots.append((str(account_name), root_path))

    return roots


def get_dropbox_folders(root_path: Path) -> list[LocalFolder]:
    """Return immediate child directories of one Dropbox root as local folders."""

    root = LocalFolder(root_path)
    return [LocalFolder(directory.path) for directory in root.list_directories()]
