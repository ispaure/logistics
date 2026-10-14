"""Application-lifetime credential sets; no configs/extracted TXT files on disk."""
from configparser import ConfigParser
import io
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

# rclone compares Go's Windows null-device spelling case-sensitively.
NULL_CONFIG = 'NUL' if os.name == 'nt' else os.devnull

_lock = threading.RLock()
_sets = {}
_private = set()
_known_packages = {}
_parents = {}


def read_package(path, password):
    from commonUtils.archives.zip_access import open_archive, validate_members
    pending = {}
    total = 0
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Credential ZIPs are limited to 1 MiB.')
    with open_archive(path, password=password) as archive:
        validate_members(archive)
        if not 0 < len(archive.infolist()) <= 64:
            raise ValueError('Credential ZIPs require 1–64 entries.')
        for member in archive.infolist():
            if member.is_dir():
                continue
            if Path(member.filename).suffix.lower() != '.txt' or member.file_size > 256 * 1024:
                raise ValueError('Credential ZIPs must contain small TXT files.')
            with archive.open(member) as stream:
                data = stream.read(256 * 1024 + 1)
            total += len(data)
            if len(data) > 256 * 1024 or total > 1024 * 1024:
                raise ValueError('Credential ZIP exceeds its expanded size limit.')
            parser = ConfigParser(interpolation=None)
            parser.read_file(io.StringIO(data.decode('utf-8-sig')))
            if parser.defaults() or len(parser.sections()) != 1:
                raise ValueError('Each TXT file must define one remote.')
            name = parser.sections()[0]
            values = dict(parser[name])
            if name in pending or not values.get('type') or any(not re.fullmatch(r'[a-zA-Z0-9_]+', key) for key in values):
                raise ValueError('Invalid or duplicate remote settings.')
            if any('\n' in value or '\r' in value or '\x00' in value for value in values.values()):
                raise ValueError('Invalid remote setting.')
            pending[name] = values
    if not pending:
        raise ValueError('No credential TXT files found.')
    return pending


def remember(config_path, values, *, package_path=None, private=False, parent=None):
    with _lock:
        config_path = Path(config_path)
        if parent is not None and Path(parent) not in _sets:
            raise ValueError('The credential session is locked.')
        forget(config_path)
        if parent is not None:
            _parents[config_path] = Path(parent)
        _sets[Path(config_path)] = (uuid4().hex, values, Path(package_path) if package_path else None)
        if package_path:
            _known_packages[Path(config_path)] = Path(package_path)
        if private:
            _private.add(Path(config_path))


def names(config_path):
    with _lock:
        entry = _sets.get(Path(config_path))
        return sorted(entry[1]) if entry else None


def paths():
    with _lock:
        return [path for path in _sets if path not in _private]


def forget(config_path):
    with _lock:
        config_path = Path(config_path)
        for child, parent in tuple(_parents.items()):
            if parent == config_path:
                forget(child)
        _parents.pop(config_path, None)
        _private.discard(config_path)
        return _sets.pop(config_path, None) is not None


def launch(config_path, source, destination):
    """Return process-private env and alias paths. Human names remain in UI."""
    with _lock:
        item = _sets.get(Path(config_path))
        if item is None:
            return None
        identity, values, _package = item
        aliases = {name: f'logistics_{identity}_{index}' for index, name in enumerate(values)}
        environment = {key: value for key, value in os.environ.items()
                       if not key.upper().startswith('RCLONE_CONFIG')}
        for name, options in values.items():
            for key, value in options.items():
                if key == 'remote':
                    remote, colon, suffix = value.partition(':')
                    if colon and remote in aliases:
                        value = aliases[remote] + ':' + suffix
                environment[f'RCLONE_CONFIG_{aliases[name].upper()}_{key.upper()}'] = value
        def translate(value):
            text = str(value)
            name, colon, suffix = text.partition(':')
            return aliases[name] + ':' + suffix if colon and name in aliases else value
        return environment, translate(source), translate(destination)


def credentials(config_path):
    from copy import deepcopy
    with _lock:
        item = _sets.get(Path(config_path))
        return deepcopy(item[1]) if item else None


def package_path(config_path):
    with _lock:
        item = _sets.get(Path(config_path))
        return item[2] if item else _known_packages.get(Path(config_path))
