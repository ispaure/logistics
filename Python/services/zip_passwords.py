"""Logistics ZIP configuration and per-archive, memory-only unlocked passwords."""

from collections import OrderedDict
from configparser import ConfigParser, Error as ConfigError
from hashlib import sha256
from pathlib import Path
from threading import RLock

from commonUtils.zip_access import ArchivePasswordError, authenticate, is_encrypted, password_bytes

_cache = OrderedDict()
_lock = RLock()


def _configured_section(path):
    """Nearest LogisticsZIP section wins; an empty/missing key stops inheritance."""
    path = Path(path).absolute()
    start = path if path.is_dir() else path.parent
    for folder in (start, *start.parents):
        config_path = folder / 'remoteConfig.ini'
        if not config_path.exists():
            continue
        parser = ConfigParser(interpolation=None)
        try:
            with config_path.open(encoding='utf-8-sig') as stream:
                parser.read_file(stream)
        except (OSError, ConfigError, UnicodeError) as error:
            # Parser errors may include lines containing a secret; do not echo them.
            raise ValueError(f'Cannot read ZIP password configuration: {config_path} ({type(error).__name__})') from None
        if parser.has_section('LogisticsZIP'):
            # DEFAULT belongs to other INI consumers, not archive inheritance.
            parser.defaults().clear()
            return parser
    return None


def has_password_configuration(path):
    try:
        return _configured_section(path) is not None
    except ValueError:
        return False


def configured_password(path):
    parser = _configured_section(path)
    return (parser.get('LogisticsZIP', 'archive_password', fallback='') or None) if parser is not None else None


def _key(path, configured):
    path = Path(path).absolute()
    stat = path.stat()
    fingerprint = sha256(password_bytes(configured) or b'').digest()
    return (str(path), stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, fingerprint)


def clear_passwords():
    with _lock:
        _cache.clear()


def remember_verified_password(path, password):
    """Keep an already verified replacement unlocked under its new file identity."""
    if password is None:
        return
    try:
        key = _key(path, configured_password(path))
    except (OSError, ValueError):
        # A cache update must never turn a completed archive save into a failure.
        return
    with _lock:
        _cache[key] = password_bytes(password)
        _cache.move_to_end(key)
        while len(_cache) > 128:
            _cache.popitem(last=False)


def resolve_password(path, *, password=None, configured_only=False):
    """No prompts. Return a tested password, or raise a sanitized password error.

    Compression uses configured_only so an invalid/missing INI is a per-file
    error even if an interactive reader previously unlocked that archive.
    """
    if not is_encrypted(path):
        return None
    configured = configured_password(path)
    key = _key(path, configured)
    if password is not None:
        candidates = [password_bytes(password)]
    else:
        candidates = [password_bytes(configured)] if configured else []
        if not configured_only:
            with _lock:
                cached = _cache.get(key)
            if cached and cached not in candidates:
                candidates.append(cached)
    last_error = None
    for candidate in candidates:
        try:
            authenticate(path, candidate)
        except ArchivePasswordError as error:
            last_error = error
            continue
        with _lock:
            _cache[key] = candidate
            _cache.move_to_end(key)
            while len(_cache) > 128:
                _cache.popitem(last=False)
        return candidate
    if last_error:
        raise last_error
    raise ArchivePasswordError(f'Archive password required: {Path(path).name}')


def is_password_error(message):
    return 'Archive password required:' in message or 'Archive password incorrect' in message
