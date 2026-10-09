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


def scan_weird_characters(target_dir, recursive=True, *, cancelled=lambda: False,
                          report=lambda done, total, message: None):
    """Inspect paths without following directory links or printing results."""
    from commonUtils.operations import check_cancelled
    paths = _scan_targets(target_dir, recursive=recursive, cancelled=cancelled)
    matches = []
    for index, path in enumerate(paths):
        check_cancelled(cancelled)
        characters = tuple(character for character in WEIRD_CHARACTERS if character in str(path))
        if characters:
            matches.append((path, characters))
        report(index + 1, len(paths), f'Inspecting {path.name}')
    return matches


def scan_pyc_files(target_dir, recursive=True, *, cancelled=lambda: False,
                   report=lambda done, total, message: None):
    """Return a read-only snapshot of regular bytecode files and their identities."""
    from services.folder_safety import require_safe_folder
    from commonUtils.operations import check_cancelled
    targets = (target_dir,) if isinstance(target_dir, (str, Path)) else target_dir
    roots = tuple(require_safe_folder(root, recursive=recursive) for root in targets)
    paths = _scan_targets(roots, mask='*.pyc', recursive=recursive, cancelled=cancelled)
    found = []
    for index, path in enumerate(paths):
        check_cancelled(cancelled)
        if not path.is_symlink() and path.is_file():
            found.append((path, _pyc_identity(path)))
        report(index + 1, len(paths), f'Inspecting {path.name}')
    return tuple(found)


def _pyc_identity(path):
    stats = path.lstat()
    return stats.st_dev, stats.st_ino, stats.st_size, stats.st_mtime_ns, stats.st_mode


def cleanup_pyc_files(target_dir, recursive=True, *, cancelled=lambda: False,
                      report=lambda done, total, message: None, candidates=None):
    """Delete only reviewed bytecode identities, preserving links and changed files."""
    from commonUtils.operations import run_batch
    from services.folder_safety import require_safe_folder
    targets = (target_dir,) if isinstance(target_dir, (str, Path)) else target_dir
    roots = tuple(require_safe_folder(root, recursive=recursive) for root in targets)
    if candidates is None:
        candidates = scan_pyc_files(roots, recursive, cancelled=cancelled)
    identities = dict(candidates)
    def delete(path):
        import stat
        require_safe_folder(path.parent, recursive=False)
        if (path.suffix.lower() != '.pyc' or not any(path.parent == root or
                (recursive and root in path.parents) for root in roots)):
            raise ValueError('Outside reviewed deletion scope')
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError('Directory replaced with a symbolic link; scan again')
        identity = _pyc_identity(path)
        if not stat.S_ISREG(identity[-1]) or identity != identities[path]:
            raise ValueError('File changed since preview; scan again')
        path.unlink()
    return run_batch(list(identities), delete, cancelled=cancelled, progress=report)


def _scan_targets(target_dirs, **options):
    from commonUtils.traversal import scan_directory, natural_path_key
    if isinstance(target_dirs, (str, Path)):
        target_dirs = (target_dirs,)
    paths = set()
    for root in target_dirs:
        paths.update(scan_directory(root, hidden=True, **options))
    return sorted(paths, key=natural_path_key)
