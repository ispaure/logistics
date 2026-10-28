"""Desktop credential publication; no dialogs, extracted TXT files or network I/O."""
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from . import session
from .service import CredentialGrant
from commonUtils.runtime.operations import check_cancelled
from .credential_loading import CredentialStage, CredentialResult


def _config_revision(path):
    """Missing files have a stable sentinel; other storage errors stay visible."""
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _saved_config(path):
    return path.with_suffix('.conf') if path.suffix == '.session' else path


@dataclass(frozen=True)
class DesktopCredentialLoad:
    package: Path
    config: Path
    remember: bool = False
    crypt_remote: str | None = None

    def __post_init__(self):
        object.__setattr__(self, 'package', Path(self.package))
        object.__setattr__(self, 'config', Path(self.config))
        if type(self.remember) is not bool or self.config.suffix != ('.conf' if self.remember else '.session'):
            raise ValueError('Choose an explicit saved config or credential session.')


class DesktopCredentials:
    lock_scope = 'package'
    # Shared across service instances and windows, like the session registry.
    _saved_lock = RLock()
    _saved_generations: dict[Path, int] = {}

    def capture(self, key):
        key = Path(key)
        if key.suffix == '.session' or session.names(key) is not None:
            return CredentialGrant(key, session.revocation_check(key))
        try:
            original = _config_revision(key)
        except OSError:
            original = None
        if original is None:
            raise ValueError('This saved credential config is unavailable.')
        saved = key.absolute()
        with self._saved_lock:
            generation = self._saved_generations.setdefault(saved, 0)
        def revoked():
            try:
                current = _config_revision(key)
            except OSError:
                return True
            with self._saved_lock:
                return self._saved_generations.get(saved) != generation or current != original
        return CredentialGrant(key, revoked)

    def lock(self, key=None):
        with self._saved_lock:
            paths = [Path(key)] if key is not None else list(set(session.paths()) | set(self._saved_generations))
            for path in paths:
                saved = _saved_config(path).absolute()
                self._saved_generations[saved] = self._saved_generations.get(saved, 0) + 1
        # Attempt every revocation even if a view's cleanup callback fails.
        failure = None
        for path in paths:
            from .remote_resources import invalidate_config
            # Saved config bytes are retained; existing views must still
            # retire. Explicitly reopening a saved config creates new access.
            for revoke in (lambda: session.forget(path),
                           lambda: invalidate_config(_saved_config(path))):
                try:
                    revoke()
                except Exception as error:
                    failure = failure or error
        if failure is not None:
            raise failure

    def retain(self, request):
        raise TypeError('Desktop retention is selected when loading a ZIP into a saved config.')

    def forget(self, key=None):
        from .configuration import get_all_conf_paths
        paths = [Path(key)] if key is not None else get_all_conf_paths()
        removed, failure = [], None
        for path in paths:
            if path.suffix.casefold() not in {'.conf', '.session'}:
                raise ValueError('Choose a saved config or credential session; original ZIPs are kept.')
        for path in paths:
            from . import desktop_catalog
            existed = path.is_file() or session.names(path) is not None or (
                path.suffix == '.session' and desktop_catalog.read(path) is not None)
            try:
                self.lock(path)
            except Exception as error:
                failure = failure or error
            try:
                path.unlink(missing_ok=True)
                if path.suffix == '.session':
                    desktop_catalog.forget(path)
                session.forget_package_path(path)
                if existed:
                    removed.append(path)
            except Exception as error:
                failure = failure or error
        if failure is not None:
            raise failure
        return removed

    def prepare(self, request, password):
        if not isinstance(request, DesktopCredentialLoad):
            raise TypeError('Choose a desktop credential package.')
        existing = session.names(request.config) is not None
        revoked = session.revocation_check(request.config)
        original = _config_revision(request.config) if request.remember else None
        def valid():
            return (_config_revision(request.config) == original if request.remember else
                    not revoked() if existing else session.names(request.config) is None)
        values = session.read_package(request.package, password)
        def close():
            for settings in values.values():
                settings.clear()
            values.clear()
        try:
            if request.crypt_remote is not None:
                from .localcrypt.mapping import backing_target
                backing_target(values, request.crypt_remote)
                if 'password' not in values[request.crypt_remote]:
                    raise ValueError('The credential ZIP is missing its crypt password setting.')
            names = tuple(sorted(values))
            def publish(context):
                if request.remember:
                    from commonUtils.persistence import atomic_write_bytes
                    content = '\n\n'.join('[' + name + ']\n' + '\n'.join(
                        f'{key} = {value}' for key, value in settings.items())
                        for name, settings in values.items()) + '\n'
                    request.config.parent.mkdir(parents=True, exist_ok=True)
                    def validate():
                        check_cancelled(context.cancelled)
                        if not context.valid() or not valid():
                            raise ValueError('Credentials changed while loading. Try again.')
                    atomic_write_bytes(request.config, content.encode('utf-8'), validate=validate)
                    from .remote_resources import invalidate_config
                    invalidate_config(request.config)
                else:
                    from . import desktop_catalog
                    desktop_catalog.remember(request.config, request.package, names)
                    session.remember(request.config, {name: dict(settings) for name, settings in values.items()},
                                     package_path=request.package)
                return CredentialResult(request.config, names, request.remember)
            return CredentialStage(publish, valid, close)
        except BaseException:
            close()
            raise

    def restore(self, *, create=False):
        raise TypeError('Desktop credentials are opened from an explicit config or ZIP.')
