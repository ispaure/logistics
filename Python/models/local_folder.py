"""
Core model for folders managed by Logistics under Server/Local.
"""

from pathlib import Path

from .logistics_folder import LogisticsFolder


class LocalFolder(LogisticsFolder):
    """
    Represents a folder managed by Logistics under Server/Local.
    """

    def __init__(self, path: str | Path):
        super().__init__(Path(path))