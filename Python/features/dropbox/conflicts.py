"""
Dropbox conflicting-copy detection and cleanup for Logistics.
"""

# ----------------------------------------------------------------------------------------------------------------------
# IMPORTS

from pathlib import Path
from typing import List

from commonUtils.filesystem import directories as dirUtils, files as fileUtils
from commonUtils.runtime.diagnostics import Severity, log


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
    """Remove identical copies only; preserve unique content and changed files."""
    result = delete_reviewed_conflicts(review_conflicts(target_dir, recursive))
    return not result.failed and not result.cancelled


from dataclasses import dataclass
from commonUtils.runtime.streams import file_sha256
from commonUtils.runtime.operations import run_batch, check_cancelled


@dataclass(frozen=True)
class ConflictCandidate:
    path: Path
    original: Path | None
    signature: tuple
    original_signature: tuple | None
    identical: bool


def _signature(path):
    info = path.lstat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def review_conflicts(target, recursive=True, *, cancelled=lambda: False):
    from commonUtils.filesystem.traversal import scan_directory
    paths = [fileUtils.File(path) for path in scan_directory(target, recursive=recursive, cancelled=cancelled)
             if not path.is_symlink()]
    with_original, missing, unsure = analyze_conflicting_copies(paths)
    reviewed = []
    for file in [*with_original, *missing, *unsure]:
        check_cancelled(cancelled)
        original = None
        if file in with_original:
            original = file.path.with_name(file.name_without_ext.split(' (')[0] + file.path.suffix)
        before = _signature(file.path)
        previous = _signature(original) if original and original.is_file() and not original.is_symlink() else None
        identical = bool(previous and file_sha256(file.path, cancelled=cancelled) == file_sha256(original, cancelled=cancelled))
        if _signature(file.path) != before or (previous and _signature(original) != previous):
            raise RuntimeError(f'File changed during review: {file.path}')
        reviewed.append(ConflictCandidate(file.path, original, before, previous, identical))
    return tuple(reviewed)


def delete_reviewed_conflicts(candidates, *, cancelled=lambda: False, report=lambda done, total, message: None):
    def remove(candidate):
        if not candidate.identical:
            raise ValueError('Copies with unique or unknown contents are preserved')
        if (_signature(candidate.path) != candidate.signature
                or _signature(candidate.original) != candidate.original_signature
                or candidate.path.is_symlink() or candidate.original.is_symlink()):
            raise RuntimeError(f'File changed after review: {candidate.path}')
        if file_sha256(candidate.path) != file_sha256(candidate.original):
            raise RuntimeError(f'Contents differ after review: {candidate.path}')
        candidate.path.unlink()
        return candidate.path
    return run_batch([item for item in candidates if item.identical], remove,
                     progress=report, cancelled=cancelled)
