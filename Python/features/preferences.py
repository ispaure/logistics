"""Per-user feature defaults, independent of installed feature package folders."""
import configparser
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile


def preferences_path():
    if sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support' / 'Logistics'
    elif sys.platform == 'win32':
        root = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming') / 'Logistics'
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
        if not root.is_absolute():
            root = Path.home() / '.config'
        root /= 'logistics'
    return root / 'preferences.ini'


def load_disabled(path):
    parser = configparser.ConfigParser(interpolation=None)
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            parser.read_file(stream)
    return set(parser.get('Features', 'disabled', fallback='').split())


def save_disabled(path, disabled):
    parser = configparser.ConfigParser(interpolation=None)
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            parser.read_file(stream)
    if not parser.has_section('Features'):
        parser.add_section('Features')
    parser.set('Features', 'disabled', '\n'.join(sorted(disabled)))
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            parser.write(stream)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
