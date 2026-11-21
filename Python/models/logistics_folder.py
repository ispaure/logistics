"""
Base model for folders managed by Logistics.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from commonUtils.filesystem import directories as dirUtils


class LogisticsFolder(dirUtils.Directory):
    """
    Base class for folders managed by Logistics.
    """

    def __init__(self, path: str | Path):
        super().__init__(Path(path))