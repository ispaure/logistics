"""Desktop remote I/O through explicit rclone credentials; never a local mount."""
from configparser import ConfigParser
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import threading
import weakref
from uuid import uuid4

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.range_reader import RangeReader
from commonUtils.runtime.resource_provider import ResourceCapabilities, resource_path
from . import session

_providers = weakref.WeakSet()
_providers_lock = threading.RLock()


def invalidate_config(config_path):
    """Credential-manager writes/removal immediately retire disk-config views."""
    with _providers_lock:
        providers = tuple(_providers)
    for provider in providers:
        if provider.config_path == Path(config_path):
            provider.close()


class RemoteResources:
    private = True
    remote_storage = True
    capabilities = ResourceCapabilities()
    max_resource = 16 * 1024 * 1024
    max_read = max_resource

    def __init__(self, config_path, remote, *, binary):
        self.config_path, self.remote, self.binary = Path(config_path), remote, Path(binary)
        values = session.credentials(self.config_path)
        self._disk_revision = None
        if values is None:
            if self.config_path.suffix == '.session':
                raise ValueError('Unlock this credential package first.')
            self._disk_revision = self.config_path.stat().st_mtime_ns
            parser = ConfigParser(interpolation=None)
            parser.read(self.config_path, encoding='utf-8')
            values = {name: dict(parser[name]) for name in parser.sections()}
        if remote not in values:
            raise ValueError('This remote is no longer available in the selected account.')
        from services.local_storage import install_local_storage_policy
        install_local_storage_policy()
        self.context = self.config_path.with_name('remote-' + uuid4().hex + '.session')
        session.remember(self.context, values, private=True,
                         parent=self.config_path if self._disk_revision is None else None)
        self.root = Path(Path.home().anchor) / '.logistics-remote' / sha256(str(self.config_path).encode()).hexdigest()[:16] / remote
        self.closed = False
        self._owners = 0
        self._lock = threading.RLock()
        self._scope = threading.local()
        with _providers_lock:
            _providers.add(self)

    def relative(self, path):
        if isinstance(path, Path):
            path = (path.relative_to(self.root) if path.is_absolute() else path).as_posix()
        return resource_path(str(path))

    def _check_active(self):
        check_cancelled(getattr(self._scope, 'cancelled', lambda: False))
        if self.closed or session.credentials(self.context) is None:
            raise ValueError('Credentials changed or were locked. Reopen this remote.')
        if self._disk_revision is not None:
            try:
                current = self.config_path.stat().st_mtime_ns
            except OSError:
                current = None
            if current != self._disk_revision:
                self.close()
                raise ValueError('Credentials changed. Reopen this remote.')

    @contextmanager
    def operation(self, cancelled):
        previous = getattr(self._scope, 'cancelled', lambda: False)
        self._scope.cancelled = lambda: previous() or cancelled()
        try:
            self._check_active()
            yield
        finally:
            self._scope.cancelled = previous

    def acquire(self):
        with self._lock:
            self._check_active()
            self._owners += 1
        released = False
        def release(*_):
            nonlocal released
            with self._lock:
                if not released:
                    released = True
                    self._owners -= 1
                    if self._owners == 0:
                        self.close()
        return release

    def close(self):
        self.closed = True
        session.forget(self.context)

    def command(self, operation, path='', *flags, limit=8 * 1024 * 1024, cancelled=lambda: False):
        self._check_active()
        launched = session.launch(self.context, self.remote + ':' + self.relative(path), '')
        if launched is None:
            raise ValueError('The remote credential session has ended.')
        environment, source, _ = launched
        result = run_bytes([str(self.binary), '--config', session.NULL_CONFIG,
            '--log-level', 'ERROR', '--retries', '1', '--low-level-retries', '1',
            '--contimeout', '15s', '--timeout', '30s', operation, *flags, '--', source],
            environment=environment, max_output=limit,
            cancelled=lambda: cancelled() or self.closed or session.credentials(self.context) is None
            or getattr(self._scope, 'cancelled', lambda: False)())
        self._check_active()
        return result

    def list(self, path='', *, cancelled=lambda: False):
        prefix = self.relative(path)
        rows = json.loads(self.command('lsjson', prefix, '--max-depth', '1', '--no-mimetype', cancelled=cancelled))
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError('Folder listing exceeds 10,000 entries.')
        result = []
        for row in rows:
            name = resource_path(row['Name'])
            if not name or '/' in name:
                raise ValueError('Remote returned an invalid filename.')
            result.append(dict(name=name, path='/'.join(p for p in (prefix, name) if p),
                directory=row['IsDir'], size=row['Size'], modified=row.get('ModTime', ''),
                revision=self._revision(row)))
        return sorted(result, key=lambda row: (not row['directory'], row['name'].casefold()))

    @staticmethod
    def _revision(row):
        return row.get('ID'), row['Size'], row.get('ModTime'), tuple(sorted((row.get('Hashes') or {}).items()))

    def stat(self, path):
        return json.loads(self.command('lsjson', path, '--stat', '--no-mimetype'))

    def version(self, path):
        return self._revision(self.stat(path))

    @contextmanager
    def open(self, path):
        row = self.stat(path)
        expected = self._revision(row)
        if row['IsDir'] or row['Size'] < 0:
            raise ValueError('This remote file cannot be read directly.')
        def validate():
            self._check_active()
        def read(offset, count):
            if self.version(path) != expected:
                raise ValueError('The remote file changed. Reopen it.')
            data = self.command('cat', path, '--offset', str(offset), '--count', str(count), limit=count)
            if self.version(path) != expected:
                raise ValueError('The remote file changed while reading. Reopen it.')
            return data
        with RangeReader(row['Size'], read, cache_blocks=2, max_read=self.max_resource, validate=validate) as stream:
            yield stream

    def read_bytes(self, path, *, limit=None):
        limit = self.max_resource if limit is None else limit
        if self.stat(path)['Size'] > limit:
            from .remote_policy import LocalCopyRequired
            raise LocalCopyRequired()
        with self.open(path) as stream:
            return stream.read(limit + 1)

    def archive_password(self, path):
        return None

    def check(self):
        self._check_active()

    @contextmanager
    def open_archive(self, path, password=None):
        from commonUtils.archives.zip_access import open_archive, validate_members
        from commonUtils.runtime.archive_source import BoundedArchive
        from .remote_policy import LocalCopyRequired
        provider = self
        class RemoteArchive(BoundedArchive):
            @contextmanager
            def open(self, member):
                info = member if hasattr(member, 'file_size') else self.getinfo(member)
                if info.file_size > provider.max_resource:
                    raise LocalCopyRequired()
                with super().open(info) as stream:
                    yield stream
        expected = self.version(path)
        with self.open(path) as stream, open_archive(stream, password=password) as archive:
            validate_members(archive)
            if len(archive.infolist()) > 10000:
                raise LocalCopyRequired()
            yield RemoteArchive(archive, self)
        if self.version(path) != expected:
            raise ValueError('The remote archive changed. Reopen it.')

