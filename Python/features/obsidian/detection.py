"""
Detection helpers for the Logistics Obsidian feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from typing import List
from commonUtils.filesystem.files import File
from commonUtils.filesystem.directories import Directory
from commonUtils.runtime.diagnostics import log, Severity
from models.local_folder import LocalFolder


required_files = {'app', 'appearance', 'core-plugins', 'workspace'}


def get_vault_paths(folder: LocalFolder) -> list[Directory]:
    """
    Return Obsidian vault paths within a LocalFolder, at any level(s)
    """

    vault_paths: List[Directory] = []

    # Search for .obsidian dirs

    dir_lst: List[Directory] = folder.list_directories(depth=2)

    for directory in dir_lst:
        if directory.name != '.obsidian':
            continue

        json_f_lst = directory.list_files(recursive=False, filter_extension='json')

        existing_files = {json_f.name_without_ext for json_f in json_f_lst}

        missing_files = required_files - existing_files

        if missing_files:
            msg = (f'Obsidian Vault "{directory.path}" is missing expected configuration file(s): '
                   f'{", ".join(sorted(missing_files))}')
            log(Severity.WARNING, 'Obsidian', msg)

        vault_paths.append(Directory(directory.path.parent))

    return vault_paths


def has_vault(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder contains at least one Obsidian vault."""

    return bool(get_vault_paths(folder))
