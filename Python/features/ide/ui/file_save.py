"""Preserve a competing disk version while publishing an IDE buffer."""
from pathlib import Path
import stat
from tempfile import mkdtemp

from commonUtils.persistence import atomic_write_bytes
from commonUtils.persistence.publication import mutation_lock
from commonUtils.persistence.text import FileConflictError


def save_existing(path, content, expected):
    """Verify the actual displaced entry and publish only to a vacant path."""
    from commonUtils.persistence.publication import rename_exclusive
    from commonUtils.persistence.text import MAX_BYTES
    from commonUtils.filesystem.local_access import check_local_path

    if len(content) > MAX_BYTES:
        raise ValueError('Encoded content exceeds the 16 MiB editing limit.')
    check_local_path(path)
    with mutation_lock:
        mode = _check_version(path, expected)
        work = Path(mkdtemp(prefix='.logistics-save-', dir=path.parent))
        staged, previous = work / 'draft', work / 'previous'
        displaced = published = False
        try:
            atomic_write_bytes(staged, content, overwrite=False, file_mode=stat.S_IMODE(mode))
            try:
                rename_exclusive(path, previous)
            except FileNotFoundError as error:
                raise FileConflictError('The original file was removed or renamed.') from error
            displaced = True
            _check_version(previous, expected)
            try:
                rename_exclusive(staged, path)
            except FileExistsError as error:
                raise FileConflictError('Another program recreated the file during Save.') from error
            published = True
            try:
                _check_version(previous, expected)
                previous.unlink()
            except OSError as error:
                raise FileConflictError(
                    f'The draft was published. A disk recovery copy is retained at {previous}.'
                ) from error
        finally:
            staged.unlink(missing_ok=True)
            if displaced and not published:
                try:
                    rename_exclusive(previous, path)
                except OSError as error:
                    raise FileConflictError(
                        f'Could not restore the displaced disk version. It is preserved at {previous}.'
                    ) from error
            if not previous.exists():
                work.rmdir()


def _check_version(path, expected):
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise FileConflictError('The original file was replaced by a different type of entry.')
        with path.open('rb') as stream:
            if stream.read(len(expected) + 1) != expected:
                raise FileConflictError('The file changed on disk.')
    except FileNotFoundError as error:
        raise FileConflictError('The original file was removed or renamed.') from error
    if not mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH):
        raise PermissionError('The file is read-only. Choose Save As to keep your changes.')
    return mode
