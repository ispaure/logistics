"""
Actions for the Logistics Calibre feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

from logisticsUtils.calibreUtils import CalibreLibrary
from models.local_folder import LocalFolder

# ----------------------------------------------------------------------------------------------------------------------
# LIBRARY DISCOVERY

def get_libraries(folder: LocalFolder) -> list[CalibreLibrary]:
    """Return the Calibre libraries contained in a LocalFolder."""

    calibre_libraries = []

    for subdirectory in folder.list_directories():
        db_files = subdirectory.list_files(recursive=False, filter_extension='db')

        if db_files:
            calibre_libraries.append(CalibreLibrary(subdirectory.path))

    return calibre_libraries


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

    destination_path = Path('/Volumes', 'BOOX-SD', 'Calibre [EPUBs]', calibre_library.name)
    calibre_library.echo_book_formats(destination_path, ['epub'])