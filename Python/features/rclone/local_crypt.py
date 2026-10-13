"""Local ciphertext copies, explicit transfer routing and session-only read access."""
from contextlib import contextmanager
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import threading
from uuid import uuid4

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.range_reader import RangeReader
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.persistence.publication import mutation_lock, rename_exclusive, serialize_mutation
from . import configuration, executable, session


def storage_root():
    from .storage import crypt_root
    return crypt_root()


def _component(value):
    readable = re.sub(r'[^\w.-]', '_', value, flags=re.UNICODE).strip('.')[:48] or 'remote'
    return readable + '-' + sha256(value.encode()).hexdigest()[:12]


def _linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def _guard_path(path, root):
    """Permit the chosen root's location; reject links below that boundary."""
    path, root = Path(path).absolute(), Path(root).absolute()
    path.relative_to(root)
    for candidate in (path, *path.parents):
        if candidate == root:
            break
        if _linked(candidate):
            raise ValueError(f'Encrypted storage cannot contain links or junctions: {candidate}')


def validate_ciphertext_tree(item):
    if not item.data.exists():
        return
    for folder, directories, files in os.walk(item.data, followlinks=False):
        for name in (*directories, *files):
            path = Path(folder) / name
            if _linked(path):
                raise ValueError(f'Encrypted copies cannot transfer symbolic links or junctions: {path}')
            info = path.lstat()
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError(f'Encrypted copies require independent regular files: {path}')


@dataclass(frozen=True)
class Connection:
    package: Path
    remote: str
    root: Path
    legacy: bool = False

    @property
    def context(self):
        return configuration.get_credential_config_path(self.package).with_suffix('.session')

    @property
    def data(self):
        if self.legacy:
            return self.root / _component(str(self.package)) / _component(self.remote)
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
        from services.local_storage import install_local_storage_policy
        install_local_storage_policy(self.root)
        if _linked(self.record.parent):
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
            atomic_write_json(self.record, {'schema': 1 if self.legacy else 2, 'package': str(self.package), 'remote': self.remote})


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
            if not isinstance(data, dict) or data.get('schema') not in (1, 2) or set(data) != {'schema', 'package', 'remote'}:
                continue
            package = Path(data['package'])
            remote = data['remote']
            if not package.is_absolute() or not isinstance(remote, str) or not remote or any(c in remote for c in '\0\r\n/\\:'):
                continue
            item = Connection(package, remote, root, legacy=data['schema'] == 1)
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
        values = session.read_package(item.package, password)
        backing_target(values, item.remote)
        session.remember(item.context, values, package_path=item.package)
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
        return (remote_name or Path(path).name) + ':' + (Path(path).name if specific else '')
    validate_ciphertext_tree(item)
    if Path(config_path) != item.context:
        raise ValueError('This encrypted copy belongs to a different credential package.')
    target = backing_target(unlock(item), item.remote)
    suffix = Path(path).absolute().relative_to(item.data).as_posix()
    return target.rstrip('/') + ('/' + suffix if suffix != '.' else '')


class LocalCryptFolder:
    """A backend-owned folder source: raw ciphertext never uses external open."""
    storage_label = 'LocalCrypt'
    private = True
    def __init__(self, item):
        self.connection = item
        self.path = item.data
        self.name = item.remote

    def open(self):
        from .ui.local_crypt import open_browser
        return open_browser(self.connection)


class CryptResources(LocalFiles):
    """Generic reader storage backed by a RAM-only crypt-to-local configuration."""
    private = True
    max_text = 8 * 1024 * 1024
    max_resource = 32 * 1024 * 1024

    def __init__(self, item, *, binary=None, password=None):
        self.connection = item
        values = unlock(item, password)
        self.binary = binary or executable.get_rclone_path()
        if not Path(self.binary).is_file():
            raise ValueError('Install the configured rclone executable first.')
        validate_ciphertext_tree(item)
        self.root = item.data
        from services.local_storage import install_local_storage_policy
        install_local_storage_policy(item.root)
        self.storage_id = str(self.root.resolve())
        self.context = configuration.get_rclone_config_dir() / ('private-' + uuid4().hex + '.session')
        settings = dict(values[item.remote])
        settings['remote'] = str(item.data.resolve(strict=True))
        self.storage_namespace = sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
        session.remember(self.context, {'view': settings}, private=True, parent=item.context)
        self.closed = False
        self._encoded_paths = {}
        self._directories = {'': self.root}
        self._sizes = OrderedDict()
        self._blocks = OrderedDict()
        self._cache_bytes = 0
        self._cache_lock = threading.RLock()
        self._operation = threading.local()
        self._owners = 0
        self._owner_lock = threading.RLock()

    def acquire(self):
        """Return an idempotent release callback for a browser/document owner."""
        with self._owner_lock:
            self._check_active()
            self._owners += 1
        released = False
        def release(*_):
            nonlocal released
            with self._owner_lock:
                if not released:
                    released = True
                    self._owners -= 1
                    if self._owners == 0:
                        self.close()
        return release

    @contextmanager
    def operation(self, cancelled):
        """Scope cancellation to this worker; concurrent readers remain independent."""
        previous = getattr(self._operation, 'cancelled', lambda: False)
        self._operation.cancelled = lambda: previous() or cancelled()
        try:
            self._check_active()
            yield
        finally:
            self._operation.cancelled = previous

    def _check_active(self):
        check_cancelled(getattr(self._operation, 'cancelled', lambda: False))
        if self.closed or session.credentials(self.context) is None:
            raise ValueError('The credential session is locked. Reopen the document after unlocking its ZIP.')


    def relative(self, path):
        if isinstance(path, Path) and path.is_absolute():
            path = path.relative_to(self.root).as_posix()
        text = str(path).replace(os.sep, '/') if isinstance(path, Path) else str(path)
        from commonUtils.runtime.resource_provider import resource_path
        return resource_path(text)

    def command(self, operation, path='', *extra, input_data=None, input_writer=None, limit=1024 * 1024, cancelled=lambda: False):
        self._check_active()
        scoped = getattr(self._operation, 'cancelled', lambda: False)
        requested = cancelled
        cancelled = lambda: scoped() or requested()
        relative = self.relative(path)
        environment, remote, _ = session.launch(self.context, 'view:' + relative, '')
        arguments = [str(self.binary), '--config', os.devnull, '--log-level', 'ERROR', '--retries', '1',
                     '--low-level-retries', '1', '--contimeout', '15s', '--timeout', '30s', operation, remote, *extra]
        return run_bytes(arguments, environment=environment, input_data=input_data, input_writer=input_writer, max_output=limit, cancelled=cancelled)

    def list(self, path='', *, cancelled=lambda: False):
        # Transfers and initial unlock validate the whole tree. Navigation only
        # needs to inspect the requested directory and its immediate children.
        physical = self._physical(path, directory=True)
        _guard_path(physical, self.root)
        versions = {}
        for child in physical.iterdir():
            check_cancelled(cancelled)
            if _linked(child):
                raise ValueError(f'Encrypted copies cannot contain links or junctions: {child}')
            info = child.lstat()
            versions[child] = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                raise ValueError(f'Encrypted copies require independent regular files: {child}')
        rows = json.loads(self.command('lsjson', path, '--encrypted', '--max-depth', '1', limit=8 * 1024 * 1024, cancelled=cancelled))
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError('Folder listing exceeds 10,000 entries.')
        prefix = self.relative(path)
        result = []
        for row in rows:
            name = row['Name']
            if not name or '/' in name or '\\' in name or name in {'.', '..'} or any(ord(c) < 32 for c in name):
                raise ValueError('Invalid decrypted filename.')
            relative = '/'.join(part for part in (prefix, name) if part)
            encrypted = self.relative(row['EncryptedPath'])
            target = physical / encrypted
            _guard_path(target, self.root)
            self._encoded_paths[relative] = target
            if row['IsDir']:
                self._directories[relative] = target
                revision = None
            else:
                revision = self.version(relative)
                if versions.get(target) == revision:
                    self._remember_size(relative, revision, int(row['Size']))
            result.append(dict(name=name, path=relative, revision=revision,
                               directory=bool(row['IsDir']), size=int(row['Size']), modified=row.get('ModTime', '')))
        return sorted(result, key=lambda row: (not row['directory'], row['name'].casefold()))

    def encrypted_path(self, path):
        self._check_active()
        relative = self.relative(path)
        target = self._encoded_paths.get(relative)
        if target is None:
            environment, remote, _ = session.launch(self.context, 'view:', '')
            arguments = [str(self.binary), '--config', os.devnull, 'backend', 'encode', remote, relative, '--json']
            result = json.loads(run_bytes(arguments, environment=environment, max_output=16384, cancelled=getattr(self._operation, 'cancelled', lambda: False)))
            if not isinstance(result, list) or len(result) != 1:
                raise ValueError('Encrypted path could not be resolved.')
            target = self.root / self.relative(result[0])
        _guard_path(target, self.root)
        self._encoded_paths[relative] = target
        return target

    def _physical(self, path, directory=False):
        relative = self.relative(path)
        if not relative:
            self._check_active()
            return self.root
        # Encoding a child maps every parent with the directory-name settings,
        # including remotes whose filename encryption is disabled.
        if directory:
            if relative in self._directories:
                self._check_active()
                target = self._directories[relative]
                _guard_path(target, self.root)
                return target
            return self.encrypted_path(relative + '/.directory-probe').parent
        return self.encrypted_path(relative)

    def create_file(self, path, stream, *, cancelled=lambda: False):
        with mutation_lock, self.operation(cancelled):
            path = self.relative(path)
            if not path or self._locate(path).exists():
                raise FileExistsError('Destination already exists.')
            temporary = '/'.join(p for p in (path.rpartition('/')[0], '.create-' + uuid4().hex) if p)
            encrypted = self.encrypted_path(temporary)
            def write(output):
                while chunk := stream.read(256 * 1024):
                    check_cancelled(cancelled)
                    output.write(chunk)
            owned = False
            try:
                with encrypted.open('xb'):
                    owned = True
                self.command('rcat', temporary, '--streaming-upload-cutoff', '0', input_writer=write, limit=0)
                self._check_active()
                rename_exclusive(encrypted, self._guard(self._physical(path)))
            finally:
                if owned:
                    encrypted.unlink(missing_ok=True)
                self._encoded_paths.pop(temporary, None)

    def version(self, path):
        info = self.encrypted_path(path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f'Encrypted documents require independent regular files: {self.encrypted_path(path)}')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def size(self, path):
        path = self.relative(path)
        revision = self.version(path)
        with self._cache_lock:
            cached = self._sizes.get(path)
            if cached and cached[0] == revision:
                self._sizes.move_to_end(path)
                return cached[1]
        row = json.loads(self.command('lsjson', path, '--stat', limit=65536))
        if row.get('IsDir') or not isinstance(row.get('Size'), int) or row['Size'] < 0:
            raise ValueError('Choose a regular file.')
        if self.version(path) != revision:
            raise ValueError('The encrypted document changed; reopen it.')
        self._remember_size(path, revision, row['Size'])
        return row['Size']

    def _remember_size(self, path, revision, size):
        with self._cache_lock:
            self._sizes[path] = revision, size
            self._sizes.move_to_end(path)
            while len(self._sizes) > 10000:
                self._sizes.popitem(last=False)

    def read_bytes(self, path, *, limit=None):
        limit = self.max_text if limit is None else limit
        self.version(path)
        if self.size(path) > limit:
            raise ValueError('The document exceeds its memory limit.')
        with self.open(path) as stream:
            return stream.read(limit + 1)

    @contextmanager
    def open(self, path):
        path = self.relative(path)
        expected = self.version(path)
        def read(offset, count):
            if self.version(path) != expected:
                raise ValueError('The encrypted document changed; reopen it.')
            key = path, expected, offset, count
            with self._cache_lock:
                if key in self._blocks:
                    self._blocks.move_to_end(key)
                    return self._blocks[key]
            data = self.command('cat', path, '--offset', str(offset), '--count', str(count), limit=count)
            if self.version(path) != expected:
                raise ValueError('The encrypted document changed; reopen it.')
            with self._cache_lock:
                self._check_active()
                if key not in self._blocks:
                    self._blocks[key] = data
                    self._cache_bytes += len(data)
                while self._cache_bytes > 32 * 1024 * 1024 or len(self._blocks) > 512:
                    _, evicted = self._blocks.popitem(last=False)
                    self._cache_bytes -= len(evicted)
            return data
        with RangeReader(self.size(path), read, block_size=4 * 1024 * 1024, cache_blocks=2) as stream:
            stream.name = Path(self.relative(path)).name
            yield stream

    def write_bytes(self, path, data, *, expected=None):
        path = self.relative(path)
        if PurePosixPath(path).suffix.lower() not in {'.md', '.markdown'} or len(data) > self.max_text:
            raise ValueError('Only bounded Markdown documents can be saved here.')
        revision = self.version(path)
        if expected is not None and self.read_bytes(path) != expected:
            raise ValueError('The document changed. Reopen it before saving.')
        def verify(staged):
            if self.read_bytes(staged) != data:
                raise ValueError('Saved content verification failed; original preserved.')
        self.replace_stream(path, lambda output: output.write(data), expected_revision=revision, verify=verify)

    @serialize_mutation
    def replace_stream(self, path, writer, *, expected_revision, verify=None):
        from commonUtils.runtime.resource_provider import require_capability
        require_capability(self, 'replace')
        path = self.relative(path)
        target = self.encrypted_path(path)
        temporary = str(PurePosixPath(path).parent / ('.save-' + uuid4().hex + PurePosixPath(path).suffix))
        if temporary.startswith('./'):
            temporary = temporary[2:]
        encrypted_temporary = self.encrypted_path(temporary)
        from commonUtils.persistence.publication import save_transaction
        cancelled = getattr(self._operation, 'cancelled', lambda: False)
        owned = False
        def stage():
            nonlocal owned
            with encrypted_temporary.open('xb'):
                owned = True
            def write(output):
                with self.operation(cancelled):
                    writer(output)
            self.command('rcat', temporary, '--streaming-upload-cutoff', '0', input_writer=write, limit=0)
        def verified():
            if verify is not None:
                verify(self.root / temporary)
            else:
                # Authenticate every block even when the caller has no domain validator.
                with self.open(temporary) as stream:
                    while stream.read(256 * 1024):
                        check_cancelled(cancelled)
            with encrypted_temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
        def validate():
            if self.version(path) != expected_revision:
                raise ValueError('The document changed while saving; the original was preserved.')
            self._check_active()
        def cleanup():
            if owned:
                encrypted_temporary.unlink(missing_ok=True)
            self._encoded_paths.pop(temporary, None)
        save_transaction(stage=stage, verify=verified, validate=validate,
                         publish=lambda: os.replace(encrypted_temporary, target),
                         cleanup=cleanup, cancelled=cancelled)

    def archive_password(self, path):
        from services.zip_passwords import password_from_ini
        relative = PurePosixPath(self.relative(path))
        for folder in (relative.parent, *relative.parent.parents):
            candidate = str(folder / 'remoteConfig.ini')
            if candidate.startswith('./'):
                candidate = candidate[2:]
            try:
                data = self.read_bytes(candidate, limit=65536)
            except OSError:
                continue
            password, found = password_from_ini(data)
            if found:
                return password
        return None

    def close(self):
        self.closed = True
        session.forget(self.context)
        with self._cache_lock:
            self._blocks.clear()
            self._sizes.clear()
            self._encoded_paths.clear()
            self._directories.clear()
            self._cache_bytes = 0
