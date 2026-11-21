"""
Core model for folders managed by Logistics through a remote source.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from .logistics_folder import LogisticsFolder


class RemoteFolder(LogisticsFolder):
    """
    Represents a folder managed by Logistics through a remote source.

    The remote source may currently be an rclone/network mount, but the model
    intentionally does not depend on rclone so other remote backends can be
    supported later.
    """

    def __init__(self, path: str | Path):
        super().__init__(Path(path))