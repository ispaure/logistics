"""Session-only resource provider for desktop ciphertext copies."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import stat
from uuid import uuid4

from commonUtils.runtime.resources.range_reader import RangeReader
from commonUtils.runtime.resources.lifetime import ResourceLeases, WorkerCancellation
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.streams import copy_stream
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.persistence.publication import mutation_lock, rename_exclusive, serialize_mutation
from features.rclone import configuration, executable, session
from .mapping import guard_ciphertext_path, is_linked, unlock, validate_ciphertext_tree
from .read_cache import PrivateReadCache
from .transport import CryptCommand


class LocalCryptFolder:
    """A backend-owned folder source: raw ciphertext never uses external open."""
    storage_label = 'LocalCrypt'
    private = True
    def __init__(self, item):
        self.connection = item
        self.path = item.data
        self.name = item.remote

    def open(self):
        from features.rclone.localcrypt.ui.views import open_browser
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
        self._cancellation = WorkerCancellation()
        self._cache = PrivateReadCache(self.root, self._check_active)
        self._commands = CryptCommand(self.binary, self.context, self._cancellation,
                                      self._check_active, closed=lambda: self.closed)
        self._leases = ResourceLeases(validate=self._check_active, close=self.close)
        self._unsubscribe = session.on_forget(self.context, self.close)
        from features.rclone.desktop_service import service
        self.credential_grant = service.credentials.capture(self.context)

    @property
    def closed(self):
        return self._cache.closed

    def acquire(self):
        return self._leases.acquire()

    @contextmanager
    def operation(self, cancelled):
        """Scope cancellation to this worker; validate before entering."""
        with self._cancellation.scope(cancelled):
            self._check_active()
            yield

    def _check_active(self):
        check_cancelled(self._cancellation.current)
        if self.closed or session.credentials(self.context) is None:
            raise ValueError('The credential session is locked. Reopen the document after unlocking its ZIP.')
        if hasattr(self, 'credential_grant'):
            self.credential_grant.check()


    def relative(self, path):
        if isinstance(path, Path) and path.is_absolute():
            path = path.relative_to(self.root).as_posix()
        text = str(path).replace(os.sep, '/') if isinstance(path, Path) else str(path)
        from commonUtils.runtime.resources.paths import resource_path
        return resource_path(text)

    def command(self, operation, path='', *extra, input_data=None, input_writer=None, limit=1024 * 1024, cancelled=lambda: False):
        return self._commands.command(operation, self.relative(path), *extra,
                                      input_data=input_data, input_writer=input_writer,
                                      limit=limit, cancelled=cancelled)

    def list(self, path='', *, cancelled=lambda: False):
        # Transfers and initial unlock validate the whole tree. Navigation only
        # needs to inspect the requested directory and its immediate children.
        physical = self._physical(path, directory=True)
        guard_ciphertext_path(physical, self.root)
        versions = {}
        for child in physical.iterdir():
            check_cancelled(cancelled)
            if is_linked(child):
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
            guard_ciphertext_path(target, self.root)
            self._cache.remember_path(relative, target, directory=bool(row['IsDir']))
            if row['IsDir']:
                revision = None
            else:
                revision = self.version(relative)
                if versions.get(target) == revision:
                    self._cache.remember_size(relative, revision, int(row['Size']))
            result.append(dict(name=name, path=relative, revision=revision,
                               directory=bool(row['IsDir']), size=int(row['Size']), modified=row.get('ModTime', '')))
        self._check_active()
        check_cancelled(cancelled)
        return sorted(result, key=lambda row: (not row['directory'], row['name'].casefold()))

    def search_entries(self, path='', *, cancelled=lambda: False):
        """List descendants with one rclone process, retaining names only in RAM."""
        prefix = self.relative(path)
        physical = self._physical(prefix, directory=True)
        # A recursive rclone listing must not traverse a link under our root.
        def unreadable(error):
            raise error
        for folder, directories, files in os.walk(physical, followlinks=False, onerror=unreadable):
            check_cancelled(cancelled)
            for name in (*directories, *files):
                check_cancelled(cancelled)
                target = Path(folder) / name
                guard_ciphertext_path(target, self.root)
                info = target.lstat()
                if not stat.S_ISDIR(info.st_mode) and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError(f'Encrypted copies require independent regular files: {target}')
        rows = json.loads(self.command('lsjson', prefix, '--encrypted', '--recursive',
                                       limit=64 * 1024 * 1024, cancelled=cancelled))
        if not isinstance(rows, list):
            raise ValueError('Invalid recursive encrypted listing.')
        for row in rows:
            check_cancelled(cancelled)
            child = self.relative(row['Path'])
            if not child:
                raise ValueError('Invalid decrypted filename.')
            relative = '/'.join(part for part in (prefix, child) if part)
            target = physical / self.relative(row['EncryptedPath'])
            guard_ciphertext_path(target, self.root)
            self._cache.remember_path(relative, target, directory=bool(row['IsDir']))
            if row['IsDir']:
                revision = None
            else:
                revision = self.version(relative)
            self._check_active()
            check_cancelled(cancelled)
            yield dict(name=PurePosixPath(child).name, path=relative, revision=revision,
                       directory=bool(row['IsDir']), size=int(row['Size']), modified=row.get('ModTime', ''))

    def encrypted_path(self, path):
        self._check_active()
        relative = self.relative(path)
        target = self._cache.path(relative)
        if target is None:
            target = self.root / self.relative(self._commands.encode(relative))
        guard_ciphertext_path(target, self.root)
        self._cache.remember_path(relative, target)
        return target

    def _physical(self, path, directory=False):
        relative = self.relative(path)
        if not relative:
            self._check_active()
            return self.root
        # Encoding a child maps every parent with the directory-name settings,
        # including remotes whose filename encryption is disabled.
        if directory:
            target = self._cache.path(relative, directory=True)
            if target is not None:
                guard_ciphertext_path(target, self.root)
                self._check_active()
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
                copy_stream(stream, output, cancelled=cancelled)
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
                self._cache.forget_path(temporary)

    def version(self, path):
        info = self.encrypted_path(path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError(f'Encrypted documents require independent regular files: {self.encrypted_path(path)}')
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

    def size(self, path):
        path = self.relative(path)
        revision = self.version(path)
        cached = self._cache.size(path, revision)
        if cached is not None:
            return cached
        row = json.loads(self.command('lsjson', path, '--stat', limit=65536))
        if row.get('IsDir') or not isinstance(row.get('Size'), int) or row['Size'] < 0:
            raise ValueError('Choose a regular file.')
        if self.version(path) != revision:
            raise ValueError('The encrypted document changed; reopen it.')
        self._cache.remember_size(path, revision, row['Size'])
        return row['Size']

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
            cached = self._cache.block(key)
            if cached is not None:
                return cached
            data = self.command('cat', path, '--offset', str(offset), '--count', str(count), limit=count)
            if self.version(path) != expected:
                raise ValueError('The encrypted document changed; reopen it.')
            self._cache.remember_block(key, data)
            return data
        def validate():
            # RangeReader can satisfy a read entirely from its own RAM cache.
            # Validate before those hits too, including cancellation/revocation.
            if self.version(path) != expected:
                raise ValueError('The encrypted document changed; reopen it.')
        with RangeReader(self.size(path), read, block_size=4 * 1024 * 1024, cache_blocks=2, validate=validate) as stream:
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
        from commonUtils.runtime.resources.provider import require_capability
        require_capability(self, 'replace')
        path = self.relative(path)
        target = self.encrypted_path(path)
        temporary = str(PurePosixPath(path).parent / ('.save-' + uuid4().hex + PurePosixPath(path).suffix))
        if temporary.startswith('./'):
            temporary = temporary[2:]
        encrypted_temporary = self.encrypted_path(temporary)
        from commonUtils.persistence.publication import save_transaction
        cancelled = self._cancellation.current
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
            self._cache.forget_path(temporary)
        save_transaction(stage=stage, verify=verified, validate=validate,
                         publish=lambda: os.replace(encrypted_temporary, target),
                         cleanup=cleanup, cancelled=cancelled)

    def archive_password(self, path):
        from services.documents.zip_passwords import password_from_ini
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
        if self._cache.retire():
            session.forget(self.context)
