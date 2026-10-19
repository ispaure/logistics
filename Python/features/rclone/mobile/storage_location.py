"""One mobile collection drive; private control state never leaves app storage."""
from hashlib import sha256
import errno
import json
from datetime import datetime
import os
from pathlib import Path
import shutil
import stat
from uuid import uuid4

from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.local_files import LocalFiles

CONFIG = 'collection-storage.json'
MARKER = '.logistics-storage'
# Registered by iOS startup after its legacy private-data migration completes.
# Keep this process-local: absolute iOS container paths change on restore/update.
_shared_local_roots = {}


def use_shared_local(private_root, documents):
    private_root, documents = _unlinked(private_root), _unlinked(documents)
    if private_root == documents or private_root.is_relative_to(documents) or documents.is_relative_to(private_root):
        raise ValueError('Shared Local storage must be separate from private app data.')
    _shared_local_roots[private_root] = _unlinked(documents / 'Local')


def shared_documents_path(private_root):
    """Return iOS public Documents when registered; private roots are never exposed."""
    local = _shared_local_roots.get(Path(private_root))
    return _unlinked(local.parent) if local is not None else None


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
    if not crypt and Path(private_root) in _shared_local_roots:
        return _unlinked(_shared_local_roots[Path(private_root)])
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

    def list(self, path='', *, cancelled=lambda: False):
        path = self.relative(path)
        folder = self._locate(path)
        from commonUtils.filesystem.local_access import check_local_path
        rows = []
        # Resolve collection configuration once at each snapshot boundary, not
        # repeatedly for every entry. Each child still gets the rooted link and
        # regular-file checks, including externally supplied SD-card contents.
        with os.scandir(folder) as children:
            for child in children:
                check_cancelled(cancelled)
                if child.is_symlink() or (hasattr(Path, 'is_junction') and Path(child.path).is_junction()):
                    raise ValueError('Linked storage is not supported.')
                check_local_path(child.path)
                try:
                    info = child.stat(follow_symlinks=False)
                    directory = child.is_dir(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError('Choose an independent regular file or folder.')
                revision = ((info.st_dev, info.st_ino) if directory else
                    (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
                rows.append(dict(name=child.name, path='/'.join(p for p in (path, child.name) if p),
                    directory=directory, size=info.st_size, revision=revision,
                    modified=datetime.fromtimestamp(info.st_mtime).astimezone().isoformat(sep=' ', timespec='seconds')))
        check_cancelled(cancelled)
        self._guard(folder)
        return sorted(rows, key=lambda row: (not row['directory'], row['name'].casefold()))


def _inventory(root):
    """Hash bytes, not mtimes (SD filesystems round timestamp precision)."""
    result = {}
    _unlinked(root)
    if not root.exists():
        return result
    if not root.is_dir():
        raise ValueError('Collection storage must be a folder.')
    def unreadable(error):
        raise error
    for folder, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
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
    with open(destination, 'r+b') as stream:
        _sync(stream)
    return destination


def _sync(stream):
    try:
        os.fsync(stream.fileno())
    except OSError as error:
        # Some Android removable filesystems do not implement fsync. The copy
        # still must pass byte verification; real I/O/full-device errors fail.
        if error.errno not in (errno.EINVAL, errno.ENOTSUP, errno.ENOSYS):
            raise


def _destination(private_root, volume):
    private_root = _unlinked(private_root)
    if private_root in _shared_local_roots:
        raise ValueError('Drive selection is Android-only.')
    volume = _unlinked(volume) if volume is not None else None
    if volume is not None and not volume.is_dir():
        raise OSError('The selected drive is not mounted.')
    base = _unlinked(volume / 'Logistics' if volume is not None else private_root)
    if volume is not None and (base.is_relative_to(private_root) or private_root.is_relative_to(base)):
        raise ValueError('Collection locations cannot contain each other.')
    names = ('Local', 'LocalCrypt') if volume is not None else ('LocalFiles', 'LocalCryptFolders')
    return base, [_unlinked(base / name) for name in names]


def _activate(private_root, volume, base):
    if volume is None:
        _unlinked(Path(private_root) / CONFIG).unlink(missing_ok=True)
        return
    marker = _unlinked(base / MARKER)
    if marker.exists():
        token = marker.read_text()
        if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise ValueError('Invalid destination collection marker.')
    else:
        token = uuid4().hex
        with marker.open('x') as stream:
            stream.write(token)
            stream.flush()
            _sync(stream)
    atomic_write_json(_unlinked(Path(private_root) / CONFIG), dict(volume=str(volume), token=token))


def recover_location(private_root, volume):
    """Explicitly use a retained collection without reading the unavailable source."""
    base, trees = _destination(private_root, volume)
    if not any(tree.is_dir() for tree in trees):
        raise ValueError('No existing collection found at this location. Choose a retained backup or copy collections instead.')
    for tree in trees:
        _inventory(tree)
    for tree in trees:
        tree.mkdir(parents=True, exist_ok=True)
    _activate(private_root, volume, base)
    return True


def start_empty_location(private_root, volume):
    """Select empty collection folders without copying or erasing either side."""
    base, trees = _destination(private_root, volume)
    for tree in trees:
        if _inventory(tree):
            raise FileExistsError('This location contains files. Use existing files here, or erase this location first.')
    base.mkdir(parents=True, exist_ok=True)
    for tree in trees:
        tree.mkdir(exist_ok=True)
    _activate(private_root, volume, base)
    return True


def describe_location(private_root, volume):
    """Cheap local preview; no hashes, copying, activation or directory creation."""
    base, trees = _destination(private_root, volume)
    chosen = selection(private_root)
    active = Path(chosen['volume']) / 'Logistics' if chosen else Path(private_root)
    folders = []
    for tree in trees:
        if tree.exists() and not tree.is_dir():
            raise ValueError('A collection folder is a file: ' + str(tree))
        state = 'contains files or folders' if tree.exists() and any(tree.iterdir()) else 'empty' if tree.exists() else 'not created'
        folders.append((str(tree), state))
    return dict(base=str(base), active=base == active, folders=folders)


def wipe_destination(private_root, volume):
    """Delete only inactive collection trees and interrupted copy staging folders."""
    base, trees = _destination(private_root, volume)
    chosen = selection(private_root)
    active = Path(chosen['volume']) / 'Logistics' if chosen else Path(private_root)
    if base == active:
        raise ValueError('This is the active collection. Recover or switch to another location before wiping this backup.')
    stages = list(base.glob('.storage-copy-*')) if base.exists() else []
    targets = trees + stages
    marker = _unlinked(base / MARKER) if volume is not None else None
    if marker is not None and marker.exists() and not marker.is_file():
        raise ValueError('Collection marker must be a regular file.')
    for target in targets:
        _inventory(target)
    for target in targets:
        if target.exists():
            shutil.rmtree(target)
    if marker is not None:
        marker.unlink(missing_ok=True)
    # Keep unrelated folders; neither credentials nor the card itself are
    # erased. A failed/partial wipe can safely be retried.
    return False


def switch_location(private_root, volume):
    """Copy/verify both trees, then commit the private pointer. Keep source backup.

    Existing destination files are never merged or replaced. Uncommitted copied
    trees can be reused on retry only if every byte matches the active source.
    """
    private_root = Path(private_root)
    if private_root in _shared_local_roots:
        raise ValueError('iOS Local uses the file-sharing root; drive selection is Android-only.')
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
    needed = sum(size for target, snapshot in zip(destinations, snapshots)
                 if not target.exists() or not any(target.iterdir()) for value in snapshot.values()
                 if value is not None for size in [value[0]])
    if shutil.disk_usage(volume or private_root).free < needed + 1024 * 1024:
        raise OSError('Not enough free space to copy both collections.')
    destination_base.mkdir(parents=True, exist_ok=True)
    marker = _unlinked(destination_base / MARKER)
    if volume is not None and marker.exists():
        token = marker.read_text()
        if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
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
    _activate(private_root, volume, destination_base)
    return True
