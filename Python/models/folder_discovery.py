"""
Discovery helpers for folders managed by Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

import config

from commonUtils.filesystem import directories as dirUtils

from .local_folder import LocalFolder


def get_local_folders() -> list[LocalFolder]:
    """Return all folders currently present under Server/Local."""

    local_root = Path(config.LogisticsConfig(create_resources=False).path_remote_local)
    local_root.mkdir(parents=True, exist_ok=True)

    local_directory = dirUtils.Directory(local_root)

    return [LocalFolder(directory.path) for directory in local_directory.list_directories()]
