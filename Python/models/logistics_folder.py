"""
Base model for folders managed by Logistics.
"""

from pathlib import Path

from commonUtils.filesystem import directories as dirUtils


class LogisticsFolder(dirUtils.Directory):
    """
    Base class for folders managed by Logistics.
    """

    def __init__(self, path: str | Path):
        super().__init__(Path(path))