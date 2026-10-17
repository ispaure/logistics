"""
Merged logical-folder construction for Logistics.
"""

from collections.abc import Iterable

import config
from services.folders.policy import configured_values

from models import folder_discovery
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


FOLDERS_SECTION = 'Folders'
EXCLUDED_REMOTE_NAMES_KEY = 'excluded_remote_names'
EXCLUDED_FOLDER_NAME_SUFFIXES_KEY = 'excluded_folder_name_suffixes'


def _get_configured_name_values(key: str) -> list[str]:
    """Return one comma-separated Folders setting as a cleaned list."""

    return configured_values(config.get_config_file_path(), key)


def _get_excluded_remote_names() -> set[str]:
    """Return exact configured remote names excluded from logical folder discovery."""

    return {
        name.casefold()
        for name in _get_configured_name_values(EXCLUDED_REMOTE_NAMES_KEY)
    }


def _get_excluded_folder_name_suffixes() -> tuple[str, ...]:
    """Return case-insensitive suffixes excluded from the complete logical folder list."""

    return tuple(
        suffix.casefold()
        for suffix in _get_configured_name_values(EXCLUDED_FOLDER_NAME_SUFFIXES_KEY)
    )


def _is_excluded_folder_name(folder_name: str, excluded_suffixes: tuple[str, ...]) -> bool:
    """Return whether a logical folder name matches one of the configured suffix exclusions."""

    if not excluded_suffixes:
        return False

    return folder_name.casefold().endswith(excluded_suffixes)


def get_folder_entries(
    remote_names: Iterable[str] = (),
    remote_source: str | None = None,
    remote_context=None,
    include_local_only: bool = True,
    local_folders: Iterable[LocalFolder] | None = None
) -> list[FolderEntry]:
    """
    Build logical folder entries for Local or one selected remote source.

    Local and remote folder names are matched case-sensitively. A remote only
    merges with a local folder when their names are exactly identical.

    When include_local_only is False, local folders without a matching remote
    are omitted from the result. This is used by source-specific remote views.

    Exact names in excluded_remote_names are ignored only on the remote side.

    Names ending in excluded_folder_name_suffixes are omitted from the complete
    logical folder list, whether they exist locally, remotely, or in both places.
    This is intended for implementation/storage companions such as -PMSDATA.
    """

    if local_folders is None:
        local_folders = folder_discovery.get_local_folders()
    else:
        local_folders = list(local_folders)

    excluded_remote_names = _get_excluded_remote_names()
    excluded_folder_suffixes = _get_excluded_folder_name_suffixes()

    local_folders_by_name = {}
    for folder in local_folders:
        if not _is_excluded_folder_name(folder.name, excluded_folder_suffixes):
            matches = local_folders_by_name.setdefault(folder.name, [])
            if all(existing.path != folder.path for existing in matches):
                matches.append(folder)

    remote_names_by_name = {}

    for remote_name in remote_names:
        if not remote_name:
            continue

        remote_name = str(remote_name).strip()

        if not remote_name:
            continue

        if remote_name.casefold() in excluded_remote_names:
            continue

        if _is_excluded_folder_name(remote_name, excluded_folder_suffixes):
            continue

        remote_names_by_name.setdefault(remote_name, remote_name)

    if include_local_only:
        folder_names = set(local_folders_by_name) | set(remote_names_by_name)
    else:
        folder_names = set(remote_names_by_name)

    entries = []
    for name in sorted(folder_names):
        matches = local_folders_by_name.get(name, [])
        if name in remote_names_by_name and len(matches) > 1:
            raise ValueError(f'Multiple local folders named {name!r}; select a specific local source before matching a remote.')
        for local in matches or [None]:
            entries.append(FolderEntry(
                name=name, local=local,
                remote_name=remote_names_by_name.get(name),
                remote_source=remote_source if name in remote_names_by_name else None,
                remote_context=remote_context if name in remote_names_by_name else None,
            ))
    return entries
