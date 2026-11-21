"""
Actions for the Logistics Calibre feature.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

from features.calibre import detection
from features.calibre.library import CalibreLibrary
from models.local_folder import LocalFolder


# ----------------------------------------------------------------------------------------------------------------------
# LIBRARY DISCOVERY

def get_libraries(folder: LocalFolder) -> list[CalibreLibrary]:
    """Return the Calibre libraries contained in a LocalFolder."""

    return [CalibreLibrary(library_path) for library_path in detection.get_library_paths(folder)]


# ----------------------------------------------------------------------------------------------------------------------
# ACTIONS

def open_library(calibre_library: CalibreLibrary) -> None:
    """Open a Calibre library directory."""

    calibre_library.open()


def launch_calibre(calibre_library: CalibreLibrary) -> None:
    """Open a library in Calibre."""

    calibre_library.open_in_calibre()


def echo_epubs_to_boox_sd(calibre_library: CalibreLibrary) -> None:
    """Echo EPUB files from a Calibre library to the BOOX SD card."""

    volume = Path('/Volumes/BOOX-SD')
    if not volume.is_mount():
        raise OSError('BOOX-SD is not mounted')
    destination_path = volume / 'Calibre [EPUBs]' / calibre_library.name
    calibre_library.echo_book_formats(destination_path, ['epub'])
