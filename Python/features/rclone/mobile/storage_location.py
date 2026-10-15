"""One mobile collection drive; private control state never leaves app storage."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.local_files import LocalFiles

CONFIG = 'collection-storage.json'
MARKER = '.logistics-storage'


def _unlinked(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('Choose an absolute storage location.')
    for parent in (path, *path.parents):
        # These OS-owned aliases cannot be changed by an application. Android
        # exposes user 0 differently inside the app's mount namespace.
        if parent.is_symlink() and parent not in (Path('/var'), Path('/tmp'), Path('/data/user/0')):
            raise ValueError('Linked storage locations are not supported: ' + str(parent))
    return path


def selection(private_root):
    config = _unlinked(Path(private_root) / CONFIG)
    if not config.exists():
        return None
    if config.stat().st_size > 4096:
        raise ValueError('Invalid collection storage settings.')
    value = json.loads(config.read_text())
    if (not isinstance(value, dict) or set(value) != {'volume', 'token'}
            or not isinstance(value['volume'], str)
            or not isinstance(value['token'], str) or len(value['token']) != 32
            or any(c not in '0123456789abcdef' for c in value['token'])):
        raise ValueError('Invalid collection storage settings.')
    _unlinked(value['volume'])
    return value


def collection_base(private_root):
    """Validate a saved drive before any mkdir/write; never fall back internally."""
    chosen = selection(private_root)
    if chosen is None:
        return Path(private_root)
    base = _unlinked(Path(chosen['volume']) / 'Logistics')
    marker = _unlinked(base / MARKER)
    try:
        if marker.read_text() != chosen['token']:
            raise ValueError('The selected drive does not match this collection.')
    except OSError as error:
        raise OSError('Collection drive unavailable. Reinsert the selected SD card and check storage permission.') from error
    return base


def collection_path(private_root, crypt=False):
    base = collection_base(private_root)
    external = base != Path(private_root)
    return _unlinked(base / (('LocalCrypt' if crypt else 'Local') if external
                             else ('LocalCryptFolders' if crypt else 'LocalFiles')))


class CollectionFiles(LocalFiles):
    def __init__(self, private_root):
        self.private_root = Path(private_root)
        root = collection_path(private_root)
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root)

    def _guard(self, path):
        if collection_path(self.private_root) != self.root:
            raise ValueError('Collection location changed. Restart Logistics.')
        return super()._guard(path)


def _inventory(root):
    """Hash bytes, not mtimes (SD filesystems round timestamp precision)."""
    result = {}
    if not root.exists():
        return result
    _unlinked(root)
    if not root.is_dir():
        raise ValueError('Collection storage must be a folder.')
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in directories + files:
            path = _unlinked(Path(folder) / name)
            info = path.stat()
            key = path.relative_to(root).as_posix()
            if path.is_dir():
                result[key] = None
            elif path.is_file() and info.st_nlink == 1:
                digest = sha256()
                with path.open('rb') as stream:
                    while block := stream.read(1024 * 1024):
                        digest.update(block)
                if (path.stat().st_ino, path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns) != (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                    raise OSError('Collection changed during copying. Close documents and retry.')
                result[key] = info.st_size, digest.hexdigest()
            else:
                raise ValueError('Collection migration requires independent regular files and folders.')
    return result


def _copy_durable(source, destination):
    shutil.copyfile(source, destination)
    with open(destination, 'rb') as stream:
        os.fsync(stream.fileno())
    return destination


def switch_location(private_root, volume):
    """Copy/verify both trees, then commit the private pointer. Keep source backup.

    Existing destination files are never merged or replaced. Uncommitted copied
    trees can be reused on retry only if every byte matches the active source.
    """
    private_root = Path(private_root)
    source_base = collection_base(private_root)
    volume = _unlinked(volume) if volume is not None else None
    if volume is not None and not volume.is_dir():
        raise OSError('The selected drive is not mounted.')
    destination_base = volume / 'Logistics' if volume is not None else private_root
    _unlinked(destination_base)
    if source_base == destination_base:
        return False
    if source_base.is_relative_to(destination_base) or destination_base.is_relative_to(source_base):
        raise ValueError('Collection locations cannot contain each other.')
    sources = [collection_path(private_root, crypt) for crypt in (False, True)]
    destinations = [destination_base / name for name in (
        ('Local', 'LocalCrypt') if volume is not None else ('LocalFiles', 'LocalCryptFolders'))]
    snapshots = [_inventory(source) for source in sources]
    # Check all conflicts before publishing either tree.
    for target, expected in zip(destinations, snapshots):
        existing = _inventory(target)
        if existing and expected and existing != expected:
            raise FileExistsError('Destination already contains different files: ' + str(target))
    needed = sum(size for snapshot in snapshots for value in snapshot.values()
                 if value is not None for size in [value[0]])
    if shutil.disk_usage(volume or private_root).free < needed + 1024 * 1024:
        raise OSError('Not enough free space to copy both collections.')
    destination_base.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    marker = _unlinked(destination_base / MARKER)
    if volume is not None and marker.exists():
        token = marker.read_text()
        if len(token) != 32:
            raise ValueError('Invalid destination collection marker.')
    for source, target, expected in zip(sources, destinations, snapshots):
        _unlinked(target)
        if target.exists() and any(target.iterdir()):
            if expected and _inventory(target) != expected:
                raise OSError('Destination changed during copying; original location retained.')
            continue  # Identical backup, or adoption when the source is empty.
        temporary = destination_base / ('.storage-copy-' + uuid4().hex)
        try:
            if source.exists():
                # Never follow a link that appeared after preflight.
                shutil.copytree(source, temporary, symlinks=True, copy_function=_copy_durable)
            else:
                temporary.mkdir()
            if _inventory(temporary) != expected or _inventory(source) != expected:
                raise OSError('Collection verification failed; original location retained.')
            if target.exists():
                target.rmdir()  # Only an empty folder may be replaced.
            temporary.rename(target)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    for target, expected in zip(destinations, snapshots):
        if expected and _inventory(target) != expected:
            raise OSError('Destination verification failed; original location retained.')
    if [_inventory(source) for source in sources] != snapshots:
        raise OSError('Collection changed during copying; original location retained.')
    if volume is None:
        (private_root / CONFIG).unlink(missing_ok=True)
    else:
        if not marker.exists():
            with marker.open('x') as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
        atomic_write_json(private_root / CONFIG, dict(volume=str(volume), token=token))
    return True
