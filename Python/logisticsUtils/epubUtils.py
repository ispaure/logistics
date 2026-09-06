"""
Hosts functions related to .EPUBs (Digital Books) Files.
"""

# ----------------------------------------------------------------------------------------------------------------------
# AUTHORSHIP INFORMATION - THIS FILE BELONGS TO MARC-ANDRE VOYER HELPER FUNCTIONS CODEBASE

__author__ = 'Marc-André Voyer'
__copyright__ = 'Copyright (C) 2020-2026, Marc-André Voyer'
__license__ = "MIT License"
__maintainer__ = 'Marc-André Voyer'
__email__ = 'marcandre.voyer@gmail.com'
__status__ = 'Production'

# ----------------------------------------------------------------------------------------------------------------------


from commonUtils import fileUtils
from pathlib import Path


class EPUBFile(fileUtils.File):
    def __init__(self, path: Path):
        super().__init__(path)

