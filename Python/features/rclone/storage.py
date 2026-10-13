"""Application-owned rclone storage and non-overwriting legacy relocation."""
from hashlib import sha256
import errno
import os
from pathlib import Path
import shutil
import stat
from tempfile import mkdtemp

from commonUtils.persistence.publication import rename_exclusive, serialize_mutation


def application_root():
    from features.preferences import preferences_path
    return preferences_path().parent


def _manifest(root, *, link_root=None):
    """Compare bytes and resolved link targets without following directory links."""
    result = {}
    link_root = Path(link_root or root).resolve(strict=False)
    def visit(directory):
        for path in directory.iterdir():
            info = path.lstat()
            relative = path.relative_to(root)
            if path.is_symlink():
                target = Path(os.readlink(path))
                target = target if target.is_absolute() else path.parent / target
                target = target.resolve(strict=False)
                if target.is_relative_to(link_root):
                    result[relative] = ('internal-link', target.relative_to(link_root).as_posix())
                else:
                    result[relative] = ('link', str(target))
            elif stat.S_ISDIR(info.st_mode):
                result[relative] = ('directory',)
                visit(path)
            elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                digest = sha256()
                with path.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                result[relative] = ('file', info.st_size, digest.digest())
            else:
                raise ValueError(f'Cannot relocate linked or special storage file: {path}')
    visit(root)
    return result


@serialize_mutation
def relocate(source, destination):
    """Move once, preserving the source on conflicts or failed verification."""
    source, destination = Path(source), Path(destination)
    if source == destination or not os.path.lexists(source):
        return
    if os.path.lexists(destination):
        # Never merge unknown storage trees or replace a destination copy.
        raise ValueError(f'Both storage locations exist. Preserve their contents and resolve the conflict: {source} and {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if source.is_symlink():
        target = source.resolve(strict=False)
        destination.symlink_to(target, target_is_directory=True)
        source.unlink()
        return
    if not source.is_dir():
        raise ValueError(f'Expected a storage directory: {source}')
    # Relative links would change meaning after a move. Copying rebases them to
    # their original absolute targets, including relocated crypt-copy roots.
    relative_links = any(path.is_symlink() and (not Path(os.readlink(path)).is_absolute()
                                               or path.resolve(strict=False).is_relative_to(source.resolve()))
                         for folder, directories, files in os.walk(source, followlinks=False)
                         for path in (Path(folder) / name for name in (*directories, *files)))
    if not relative_links:
        try:
            rename_exclusive(source, destination)
            return
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
    expected = _manifest(source)
    stage = Path(mkdtemp(prefix='.rclone-relocate-', dir=destination.parent))
    copied = stage / 'contents'
    try:
        shutil.copytree(source, copied, symlinks=True)
        for relative, description in expected.items():
            if description[0] in {'link', 'internal-link'}:
                link = copied / relative
                link.unlink()
                target = destination.resolve(strict=False) / description[1] if description[0] == 'internal-link' else Path(description[1])
                link.symlink_to(target, target_is_directory=(source / relative).is_dir())
        if _manifest(copied, link_root=destination) != expected or _manifest(source) != expected:
            raise ValueError('Storage changed during relocation; the original was preserved.')
        rename_exclusive(copied, destination)
        # The verified destination is already published before source cleanup.
        shutil.rmtree(source)
    finally:
        shutil.rmtree(stage)


def crypt_root():
    import config
    destination = application_root() / 'LocalCrypt'
    relocate(config.LogisticsConfig().server_path / 'LocalCrypt', destination)
    return destination


def local_records(local_root):
    destination = application_root() / 'Connections' / 'Local'
    relocate(Path(local_root).parent / '.local-connections', destination)
    return destination
