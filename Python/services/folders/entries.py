"""
Merged logical-folder construction for Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections.abc import Iterable

import config

from models import folder_discovery
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder
from services.folders.policy import read_exclusions, visible_name


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

    exclusions = read_exclusions(config.get_config_file_path())

    locals_by_name = {}
    for folder in local_folders:
        # An unnamed local root still belongs in the listing.
        if not folder.name or visible_name(folder.name, exclusions):
            locals_by_name.setdefault(folder.name, {}).setdefault(folder.path, folder)

    visible_remotes = set()
    for name in remote_names:
        if name:
            normalized_name = str(name).strip()
            if visible_name(normalized_name, exclusions, remote=True):
                visible_remotes.add(normalized_name)

    names = visible_remotes | locals_by_name.keys() if include_local_only else visible_remotes
    entries = []
    for name in sorted(names):
        local_matches = locals_by_name.get(name, {})
        has_remote = name in visible_remotes
        if has_remote and len(local_matches) > 1:
            raise ValueError(f'Multiple local folders named {name!r}; select a specific local source before matching a remote.')
        for folder in local_matches.values() if local_matches else (None,):
            entries.append(FolderEntry(
                name=name,
                local=folder,
                remote_name=name if has_remote else None,
                remote_source=remote_source if has_remote else None,
                remote_context=remote_context if has_remote else None,
            ))
    return entries
