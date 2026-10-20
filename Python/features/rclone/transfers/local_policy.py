"""Local transfer policy shared by the CLI and embedded hosts."""
import os
from pathlib import Path
import stat

from features.rclone.transfers.transfer_options import CLEANUP_NAMES


def check_cancelled(cancelled):
    if cancelled():
        raise ValueError('Transfer cancelled; completed destination changes remain.')


def inventory(root, cancelled=lambda: False):
    records = {}
    def failed(error):
        raise error
    for folder, directories, files in os.walk(root, followlinks=False, onerror=failed):
        for name in (*directories, *files):
            check_cancelled(cancelled)
            path = Path(folder) / name
            info = path.lstat()
            if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
                raise ValueError('LocalCrypt push refused: linked entry ' + str(path.relative_to(root)))
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError('LocalCrypt push refused: unsupported entry ' + str(path.relative_to(root)))
            records[path.relative_to(root).as_posix()] = stamp(info)
    return records


def stamp(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def cleanup_candidates(root, decode, cancelled=lambda: False):
    result = {}
    for name, version in inventory(root, cancelled).items():
        if stat.S_ISREG(version[2]):
            label = name if Path(name).name.casefold() in CLEANUP_NAMES else decode(name, cancelled)
            if Path(label).name.casefold() in CLEANUP_NAMES:
                result[name] = (label, version)
    return result


def remove_generated(root, name, version):
    path = Path(root) / name
    if stamp(path.lstat()) != tuple(version) or not stat.S_ISREG(version[2]):
        raise ValueError('LocalCrypt changed during cleanup. Review the push again.')
    path.unlink()


def transfer_inventory(root, cancelled=lambda: False, *, copy_links=False, allow_missing=False):
    """Validate entries; Pull may omit destination entries removed during a scan.

    Push and revision snapshots remain strict. Missing roots, links and errors
    other than ENOENT must still fail rather than hide unavailable storage.
    """
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Transfer root must be an unlinked directory.')
    result, pending = {}, [root]
    while pending:
        directory = pending.pop()
        check_cancelled(cancelled)
        try:
            children = sorted(directory.iterdir())
        except FileNotFoundError:
            if not allow_missing or directory == root:
                raise
            continue
        for path in children:
            check_cancelled(cancelled)
            linked = path.is_symlink() or getattr(path, 'is_junction', lambda: False)()
            if linked and (not copy_links or not path.is_file()):
                raise ValueError('Linked directories and LocalCrypt links cannot be transferred.')
            key = path.relative_to(root).as_posix()
            try:
                if path.is_dir():
                    result[key] = stamp(path.stat()), stamp(path.lstat())
                    pending.append(path)
                else:
                    before = stamp(path.stat())
                    link_before = stamp(path.lstat())
                    if not stat.S_ISREG(before[2]) or (not copy_links and path.stat().st_nlink != 1):
                        raise ValueError('Choose regular transfer files.')
                    result[key] = before, link_before
            except FileNotFoundError:
                if not allow_missing or linked or path.is_symlink():
                    raise
    return result
