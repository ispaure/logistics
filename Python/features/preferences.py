"""Per-user feature defaults, independent of installed feature package folders."""
import configparser
import os
from pathlib import Path
import sys
import logging
from datetime import datetime
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


def _read(path, *, saving=False):
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open(encoding='utf-8') as stream:
            parser.read_file(stream)
    except FileNotFoundError:
        pass
    except (configparser.Error, UnicodeError):
        backup = path.with_name(path.name + '.broken-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        try:
            path.replace(backup)
        except OSError:
            if saving:
                raise
            logging.warning('Cannot read feature preferences at %s; using defaults and keeping the original file.', path)
        else:
            logging.warning('Malformed feature preferences preserved at %s; using defaults.', backup)
        return configparser.ConfigParser(interpolation=None)
    except OSError:
        if saving:
            raise
        logging.warning('Cannot read feature preferences at %s; using defaults.', path)
        return configparser.ConfigParser(interpolation=None)
    return parser


def load_disabled(path):
    parser = _read(path)
    return set(parser.get('Features', 'disabled', fallback='').split())


def save_disabled(path, disabled):
    parser = _read(path, saving=True)
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
