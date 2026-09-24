"""
Core model for folders managed by Logistics through a remote source.
"""

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