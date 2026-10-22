"""Desktop remote I/O through explicit rclone credentials; never a local mount."""
from configparser import ConfigParser
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import threading
import weakref
from uuid import uuid4

from commonUtils.integrations.wrappers.cmdShellWrapper.binary import BinaryCommandError, run_bytes
from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.range_reader import RangeReader
from commonUtils.runtime.resources.paths import resource_path
from commonUtils.runtime.resources.provider import ResourceCapabilities
from . import session

_providers = weakref.WeakSet()
_providers_lock = threading.RLock()


def remote_failure(error):
    """Translate provider diagnostics to fixed text; never echo secrets or paths."""
    detail = error.stderr.decode('utf-8', errors='replace').casefold()
    if any(value in detail for value in ('invalid_grant', 'invalid_client', 'unauthorized_client',
                                         'token has been expired or revoked',
                                         'empty token found', 'invalid authentication credentials')):
        return ('The storage service rejected the account authorization. For Google Drive, '
                'renew the underlying Drive remote authorization, update the credential ZIP, '
                'then lock and unlock the account with the updated ZIP.')
    if "didn't find section in config file" in detail or 'could not find config section' in detail:
        return ('A backing remote is missing from this credential package. Include the crypt '
                'remote and every remote it references, including the underlying Google Drive '
                'account, in the same ZIP, then unlock it again.')
    if 'failed to decrypt password' in detail:
        return ('The crypt password setting could not be decoded. Restore the original rclone '
                'crypt settings in the credential ZIP, then unlock it again.')
    if any(value in detail for value in ('ratelimitexceeded', 'rate limit exceeded', 'quota exceeded',
                                         'userratelimitexceeded', 'too many requests')):
        return 'The storage service rate limit was reached. Wait a moment and retry.'
    if any(value in detail for value in ('directory not found', 'folder not found', 'filenotfound')):
        return ('The remote folder was not found or is inaccessible to this account. '
                'Check the crypt remote path, Drive root folder and shared-folder access.')
    if any(value in detail for value in ('permission denied', 'insufficientpermissions',
                                         'insufficient authentication scopes', 'access denied')):
        return ('The storage service denied access. Check the account permissions and '
                'the underlying remote authorization scope.')
    if any(value in detail for value in ('no such host', 'dial tcp', 'i/o timeout',
                                         'tls handshake timeout', 'x509:', 'network is unreachable')):
        return 'Could not connect securely to the storage service. Check the network connection and retry.'
    return (f'rclone could not read this remote (exit status {error.returncode}). '
            'Check the credential package, underlying account authorization and remote folder access.')


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
        self.encrypted = values[remote].get('type') == 'crypt'
        self.storage_label = ('Home Server' if self.config_path.stem.casefold()
                              in {'network shares', 'session network shares'} else 'Cloud')
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
        try:
            result = run_bytes([str(self.binary), '--config', session.NULL_CONFIG,
                '--log-level', 'ERROR', '--retries', '1', '--low-level-retries', '1',
                '--contimeout', '15s', '--timeout', '30s', operation, *flags, '--', source],
                environment=environment, max_output=limit, max_stderr=64 * 1024,
                cancelled=lambda: cancelled() or self.closed or session.credentials(self.context) is None
                or getattr(self._scope, 'cancelled', lambda: False)())
        except BinaryCommandError as error:
            self._check_active()
            raise OSError(remote_failure(error)) from None
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
        from commonUtils.runtime.resources.archives import BoundedArchive
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

