"""
Detection helpers for the Logistics Calibre feature.
"""

from pathlib import Path

from models.local_folder import LocalFolder


CALIBRE_METADATA_FILE_NAME = 'metadata.db'


def get_library_paths(folder: LocalFolder) -> list[Path]:
    """
    Return Calibre library paths contained directly within a LocalFolder.

    A top-level subdirectory is considered a Calibre library when it contains
    Calibre's metadata.db file.
    """

    library_paths = []

    for subdirectory in folder.list_directories():
        metadata_path = Path(subdirectory.path, CALIBRE_METADATA_FILE_NAME)

        if metadata_path.is_file():
            library_paths.append(subdirectory.path)

    return library_paths


def has_library(folder: LocalFolder) -> bool:
    """Return whether the LocalFolder contains at least one Calibre library."""

    return bool(get_library_paths(folder))
