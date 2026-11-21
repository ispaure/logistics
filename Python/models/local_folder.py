"""
Core model for folders managed by Logistics under Server/Local.
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


class LocalFolder(LogisticsFolder):
    """
    Represents a folder managed by Logistics under Server/Local.
    """

    def __init__(self, path: str | Path):
        super().__init__(Path(path))