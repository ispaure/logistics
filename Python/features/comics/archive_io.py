"""Build and verify comic archives before committing changes to user files."""

import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
import zipfile

from commonUtils import zipUtils
from commonUtils.archives.zip_access import validate_members, open_archive
from commonUtils.streams import stream_signature


def _file_signature(snapshot):
    if snapshot is None:
        return None
    return (snapshot.st_dev, snapshot.st_ino, snapshot.st_size, snapshot.st_mode,
            snapshot.st_mtime_ns, snapshot.st_ctime_ns)


def archive_unchanged(path: Path, snapshot) -> bool:
    current = path.stat() if path.exists() else None
    return _file_signature(current) == _file_signature(snapshot)


def validate_archive_members(path: Path):
    """Reject member paths that extraction would merge or place outside its workspace."""
    with zipfile.ZipFile(path) as archive:
        validate_members(archive)


def replace_archive(source_dir: Path, destination: Path, *, overwrite: bool = True,
                    expected_stat=None, password=None):
    """Keep the original intact until a complete, verified ZIP is ready beside it."""
    source_dir, destination = Path(source_dir), Path(destination)
    if destination.is_symlink():
        raise ValueError(f'Refusing to replace an archive symlink: {destination}')
    original_stat = destination.stat() if destination.exists() else None
    if expected_stat is not None and _file_signature(original_stat) != _file_signature(expected_stat):
        raise RuntimeError(f'Archive changed while processing: {destination}')
    if original_stat is not None and not overwrite:
        raise FileExistsError(destination)

    # Use the destination filesystem so the final replacement is atomic.
    with TemporaryDirectory(prefix='.logistics-comic-', dir=destination.parent, ignore_cleanup_errors=True) as staging:
        staged_archive = Path(staging) / 'result.zip'
        if any(path.is_symlink() for path in source_dir.rglob('*')):
            raise ValueError('Cannot build a comic archive from symbolic links')
        if password is None:
            zipUtils.zip_file(source_dir, staged_archive, keep_root=False)
        else:
            zipUtils.zip_file(source_dir, staged_archive, keep_root=False, password=password)
        expected = {
            path.relative_to(source_dir).as_posix(): path
            for path in source_dir.rglob('*') if path.is_file()
        }
        if not expected:
            raise ValueError('Cannot build an empty comic archive')
        with open_archive(staged_archive, password=password) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) != len(expected) or {info.filename for info in members} != set(expected):
                raise ValueError('Archive contents do not match the result directory')
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValueError(f'Archive CRC verification failed: {bad_member}')
            for info in members:
                with expected[info.filename].open('rb') as source, archive.open(info) as result:
                    if stream_signature(source) != stream_signature(result):
                        raise ValueError(f'Archive member differs from result: {info.filename}')

        # Do not overwrite changes made by another operation during the build.
        if not archive_unchanged(destination, original_stat):
            raise RuntimeError(f'Archive changed while processing: {destination}')
        with staged_archive.open('r+b') as archive_file:
            os.fsync(archive_file.fileno())
        if original_stat is not None:
            staged_archive.chmod(stat.S_IMODE(original_stat.st_mode))
        if overwrite:
            os.replace(staged_archive, destination)
        else:
            # An exclusive link also closes the race with another conversion.
            os.link(staged_archive, destination)
