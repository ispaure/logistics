"""
Dropbox conflicting-copy detection and cleanup for Logistics.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import List

from commonUtils import dirUtils, fileUtils
from commonUtils.debugUtils import Severity, log


# ----------------------------------------------------------------------------------------------------------------------
# ANALYSIS

def analyze_conflicting_copies(file_lst: List[fileUtils.File]):
    """
    Analyze Dropbox conflicting copies and classify them.

    Returns:
        (with_original, without_original, unsure)
    """

    conflicting_file_lst: List[fileUtils.File] = []

    # Step 1: detect conflicts
    for file in file_lst:
        name_no_ext = file.name_without_ext

        if ' conflicted copy ' in name_no_ext and ' (' in name_no_ext and ')' in name_no_ext:
            conflicting_file_lst.append(file)

    # Step 2: classify
    conflict_file_no_original_lst: List[fileUtils.File] = []
    conflict_file_with_original_lst: List[fileUtils.File] = []
    conflict_file_unsure_process_lst: List[fileUtils.File] = []

    for file in conflicting_file_lst:
        # Ambiguous naming
        if file.name_without_ext.count(' (') != 1:
            conflict_file_unsure_process_lst.append(file)
            continue

        original_name = file.name_without_ext.split(' (')[0]
        parent = file.path.parent

        if file.ext:
            original_path = parent / f'{original_name}.{file.ext}'
        else:
            original_path = parent / original_name

        if original_path.exists():
            conflict_file_with_original_lst.append(file)
        else:
            conflict_file_no_original_lst.append(file)

    return (
        conflict_file_with_original_lst,
        conflict_file_no_original_lst,
        conflict_file_unsure_process_lst
    )


def analyze_directory(target_dir: str | Path, recursive: bool = True):
    """Analyze Dropbox conflicting copies within a directory."""

    directory = dirUtils.Directory(Path(target_dir))
    file_lst = directory.list_files(recursive=recursive)

    return analyze_conflicting_copies(file_lst)


# ----------------------------------------------------------------------------------------------------------------------
# REPORTING

def print_conflicting_copies(target_dir: str | Path, recursive: bool = True) -> None:
    """Log a report of Dropbox conflicting copies within a directory."""

    tool_name = 'Conflicting Copies Report'

    with_original, no_original, unsure = analyze_directory(target_dir, recursive)

    # With original
    msg = f'Conflict Files with Original ({len(with_original)}):\n'
    for file in with_original:
        msg += f' - {file.path}\n'
    log(Severity.INFO, tool_name, msg)

    # Without original
    msg = f'Conflict Files without Original ({len(no_original)}):\n'
    for file in no_original:
        msg += f' - {file.path}\n'
    severity = Severity.INFO if not no_original else Severity.ERROR
    log(severity, tool_name, msg)

    # Unsure
    msg = f'Conflict Files cannot process ({len(unsure)}):\n'
    for file in unsure:
        msg += f' - {file.path}\n'
    severity = Severity.INFO if not unsure else Severity.CRITICAL
    log(severity, tool_name, msg)


# ----------------------------------------------------------------------------------------------------------------------
# DELETION

def delete_conflicting_copies(target_dir: str | Path, recursive: bool = True) -> bool:
    """
    Delete Dropbox conflicting copies only when every detected conflict has an original.

    If any conflicting copy has no corresponding original, or its naming cannot be processed
    safely, deletion is aborted before any files are removed.
    """

    tool_name = 'Delete Conflicting Copies'

    with_original, no_original, unsure = analyze_directory(target_dir, recursive)

    # Safety check: abort if anything is not clean
    if no_original or unsure:
        msg = 'Deletion aborted. Resolve conflicts before proceeding:\n'

        if no_original:
            msg += f'\nFiles WITHOUT original ({len(no_original)}):\n'
            for file in no_original:
                msg += f' - {file.path}\n'

        if unsure:
            msg += f'\nFiles that could NOT be processed safely ({len(unsure)}):\n'
            for file in unsure:
                msg += f' - {file.path}\n'

        log(Severity.CRITICAL, tool_name, msg)
        return False

    # Safe to proceed: all detected conflicts have originals.
    deleted = []
    failed = []

    for file in with_original:
        try:
            result = file.delete_file()

            if result:
                deleted.append(file)
            else:
                failed.append(file)

        except Exception as exception:
            failed.append(file)
            log(Severity.ERROR, tool_name, f'Error deleting {file.path}: {exception}')

    msg = f'Deleted {len(deleted)} conflicting files (all had originals):\n'
    for file in deleted:
        msg += f' - {file.path}\n'
    log(Severity.INFO, tool_name, msg)

    if failed:
        msg = f'Failed to delete {len(failed)} files:\n'
        for file in failed:
            msg += f' - {file.path}\n'
        log(Severity.ERROR, tool_name, msg)
        return False

    return True
