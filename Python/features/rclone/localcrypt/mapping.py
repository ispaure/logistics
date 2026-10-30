"""Desktop ciphertext-copy identities, persisted mappings and transfer routing.

Records contain only credential ZIP identity and remote spelling. Provider I/O,
private read caches and widgets belong to other owners.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from commonUtils.persistence import atomic_write_json
from commonUtils.filesystem.native_paths import native_path
from commonUtils.persistence.publication import serialize_mutation
from features.rclone import configuration, session


def storage_root():
    from features.rclone.storage import crypt_root
    return crypt_root()


def is_linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def guard_ciphertext_path(path, root):
    """Permit the chosen root's location; reject links below that boundary."""
    path, root = native_path(path), native_path(root)
    path.relative_to(root)
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if is_linked(candidate):
            raise ValueError(f'Encrypted storage cannot contain links or junctions: {candidate}')


def validate_ciphertext_tree(item):
    data = native_path(item.data)
    if not data.exists():
        return
    for folder, directories, files in os.walk(data, followlinks=False):
        for name in (*directories, *files):
            path = Path(folder) / name
            if is_linked(path):
                raise ValueError(f'Encrypted copies cannot transfer symbolic links or junctions: {path}')
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError(f'Encrypted copies require independent regular files: {path}')


@dataclass(frozen=True)
class Connection:
    """Bind one credential ZIP and exact remote spelling to a ciphertext root."""
    package: Path
    remote: str
    root: Path

    @property
    def context(self):
        return configuration.get_credential_config_path(self.package).with_suffix('.session')

    @property
    def data(self):
        # Keep the actual remote spelling; never silently map two names together.
        name = self.remote
        if (not name or name.startswith('.') or name.endswith((' ', '.'))
                or any(ord(c) < 32 or c in '<>:"/\\|?*' for c in name)
                or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                    *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}):
            raise ValueError('The crypt remote name must be a valid folder name. Rename the remote before pulling.')
        return self.root / name

    @property
    def record(self):
        identity = sha256((str(self.package) + '\0' + self.remote).encode()).hexdigest()
        return self.root / '.connections' / (identity + '.json')

    @serialize_mutation
    def publish(self):
        from features.rclone.storage import install_local_storage_policy
        install_local_storage_policy(self.root)
        if is_linked(self.record.parent):
            raise ValueError('LocalCrypt credential mappings cannot be stored through a link.')
        mapped = connections(self.root, _include_missing=True)
        own = next((item for item in mapped if item.record == self.record), None)
        if own is not None and own != self:
            raise ValueError('This credential package already has a different LocalCrypt mapping.')
        if self.record.exists() and own is None:
            raise ValueError('The existing LocalCrypt credential mapping is invalid.')
        for item in mapped:
            if item != self and item.data.relative_to(self.root).as_posix().casefold() == self.data.relative_to(self.root).as_posix().casefold():
                raise ValueError(f'LocalCrypt folder {self.remote!r} belongs to another credential package. Rename the remote before pulling.')
        validate_ciphertext_tree(self)
        if own is None:
            # Exclusive creation also refuses an untracked directory or symlink.
            self.data.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if any(child.name.casefold() == self.data.name.casefold() for child in self.data.parent.iterdir()):
                raise ValueError(f'LocalCrypt destination already exists without this credential mapping: {self.data}')
            self.data.mkdir(mode=0o700)
        else:
            self.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        from commonUtils.filesystem.local_access import provider_record_access
        with provider_record_access(self.record):
            atomic_write_json(self.record, {'schema': 2, 'package': str(self.package), 'remote': self.remote})


def connection(config_path, remote, *, root=None):
    package = session.package_path(config_path)
    if package is None:
        raise ValueError('Unlock this credential ZIP for the current session first.')
    values = session.credentials(config_path)
    if values is None or values.get(remote, {}).get('type') != 'crypt':
        raise ValueError('Pull encrypted copy requires a session-loaded crypt remote.')
    backing_target(values, remote)
    root = Path(root or storage_root()).absolute()
    return next((item for item in connections(root, _include_missing=True)
                 if item.package == package.absolute() and item.remote == remote),
                Connection(package.absolute(), remote, root))


def connections(root=None, *, _include_missing=False):
    root = Path(root or storage_root()).absolute()
    directory = root / '.connections'
    if not directory.is_dir() or directory.is_symlink():
        return []
    result = []
    for record in directory.glob('*.json'):
        try:
            if record.is_symlink() or record.stat().st_size > 8192:
                continue
            data = json.loads(record.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema') != 2 or set(data) != {'schema', 'package', 'remote'}:
                continue
            package = Path(data['package'])
            remote = data['remote']
            if not package.is_absolute() or not isinstance(remote, str) or not remote or any(c in remote for c in '\0\r\n/\\:'):
                continue
            item = Connection(package, remote, root)
            item.data  # Validate the folder name even for a missing copy.
            if item.record != record or (not _include_missing and not item.data.is_dir()):
                continue
            result.append(item)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(result, key=lambda item: (item.package.name.casefold(), item.remote.casefold()))


def for_path(path, root=None):
    path = Path(path).absolute()
    return next((item for item in connections(root) if path == item.data or item.data in path.parents), None)


def backing_target(values, remote):
    settings = values.get(remote, {})
    if settings.get('type') != 'crypt':
        raise ValueError('The selected remote is not a crypt remote.')
    target = settings.get('remote', '')
    name, colon, _path = target.partition(':')
    if not colon or not name or name not in values or values[name].get('type') in {'crypt', 'alias', 'union', 'combine'}:
        raise ValueError('Crypt must point directly to a cloud remote and subpath in the same ZIP.')
    if not target or any(c in target for c in '\0\r\n'):
        raise ValueError('Invalid backing remote.')
    return target


def unlock(item, password=None):
    values = session.credentials(item.context)
    if values is None or session.package_path(item.context) != item.package:
        if password is None:
            raise ValueError('Unlock the matching credential ZIP for this session.')
        from features.rclone.desktop_service import service
        from features.rclone.desktop_credentials import DesktopCredentialLoad
        service.credentials.load(DesktopCredentialLoad(item.package, item.context, crypt_remote=item.remote), password)
        values = session.credentials(item.context)
    backing_target(values, item.remote)
    if 'password' not in values[item.remote]:
        raise ValueError('The credential ZIP is missing its crypt password setting.')
    return values


def push_target(path, config_path, remote_name=None, *, root=None, specific=False):
    """Resolve ciphertext copies before ordinary remote:path construction."""
    item = for_path(path, root)
    if item is None:
        boundary = Path(root or storage_root()).absolute()
        candidate = Path(path).absolute()
        if candidate == boundary or boundary in candidate.parents:
            raise ValueError(f'Encrypted copy has no valid credential mapping: {candidate}')
        from features.rclone.transfers.scope import push_scope
        remote, prefix = push_scope(Path(path).name, remote_name, specific=specific)
        return remote + ':' + prefix
    validate_ciphertext_tree(item)
    if Path(config_path) != item.context:
        raise ValueError('This encrypted copy belongs to a different credential package.')
    target = backing_target(unlock(item), item.remote)
    suffix = Path(path).absolute().relative_to(item.data).as_posix()
    return target.rstrip('/') + ('/' + suffix if suffix != '.' else '')
