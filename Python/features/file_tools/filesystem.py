"""
Filesystem maintenance and diagnostic operations for the Logistics File Tools feature.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path

from commonUtils import dirUtils
from commonUtils.debugUtils import Severity, log


# Some entries appear visually identical but use different Unicode representations.
WEIRD_CHARACTERS = [
    'é', 'É', 'è', 'È', 'ê', 'Ê', 'ë', 'Ë',
    'é', 'É', 'è', 'È', 'ê', 'Ê', 'ë', 'Ë',
    'à', 'À', 'â', 'Â', 'ä', 'Ä',
    'à', 'À', 'â', 'Â', 'ä', 'Ä',
    'î', 'Î', 'ï', 'Ï',
    'î', 'Î', 'ï', 'Ï',
    'ù', 'Ù', 'û', 'Û',
    'ù', 'Ù', 'û', 'Û',
    'ç', 'Ç',
    'ç', 'Ç',
    'ô', 'Ô',
    'ô', 'Ô',
]


# ----------------------------------------------------------------------------------------------------------------------
# DIAGNOSTICS

def find_files_with_weird_characters(target_dir: str | Path, recursive: bool = True) -> list[Path]:
    """Return files whose paths contain one or more configured problematic characters."""

    directory = dirUtils.Directory(Path(target_dir))
    file_lst = directory.list_files(recursive=recursive)

    matching_paths = []

    for file in file_lst:
        file_path_str = str(file.path)

        if any(character in file_path_str for character in WEIRD_CHARACTERS):
            matching_paths.append(file.path)

    return matching_paths


def print_files_with_weird_characters(target_dir: str | Path, recursive: bool = True) -> list[Path]:
    """Find and print files whose paths contain configured problematic characters."""

    matching_paths = find_files_with_weird_characters(target_dir, recursive)

    print('Starting the printing of files with weird characters in their name in dir')
    print(f'Target Folder: {Path(target_dir)}')

    for file_path in matching_paths:
        print(f' - {file_path}')

    print(f'\nFound {len(matching_paths)} files with weird characters.')
    print('Done going through files list!')

    return matching_paths


# ----------------------------------------------------------------------------------------------------------------------
# MAINTENANCE

def delete_pyc_files(target_dir: str | Path, recursive: bool = True) -> int:
    """Delete .pyc files from a directory and return the number successfully deleted."""

    tool_name = 'Bulk Delete PYC Files'
    directory = dirUtils.Directory(Path(target_dir))
    file_lst = directory.list_files(recursive=recursive, filter_extension='pyc')

    deleted_count = 0

    for file in file_lst:
        if file.delete_file():
            deleted_count += 1

    log(
        Severity.INFO,
        tool_name,
        f'Deleted {deleted_count} PYC files from "{directory.path}"'
    )

    return deleted_count
