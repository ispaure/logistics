"""Configured immediate-child libraries for the local comics browser."""

from configparser import ConfigParser, Error as ConfigError
from pathlib import Path


def _library_names(root):
    config = ConfigParser(interpolation=None)
    config_path = Path(root) / 'remoteConfig.ini'
    if config_path.exists():
        with config_path.open(encoding='utf-8-sig') as stream:
            config.read_file(stream)
    if not config.has_option('LogisticsComics', 'libraries'):
        return None
    names = list(dict.fromkeys(name.strip() for name in config.get('LogisticsComics', 'libraries').split(',')
                              if name.strip()))
    for name in names:
        if name in ('.', '..') or '/' in name or '\\' in name or Path(name).is_absolute():
            raise ValueError('Library names must name immediate child folders')
    return names


def configured_libraries(root):
    """Return configured names/paths in order, plus an optional configuration error.

    An absent setting retains whole-root browsing. Configured missing folders
    remain in the library tabs and are disabled by the UI.
    """
    root = Path(root)
    try:
        names = _library_names(root)
        if names is None:
            return [(root.name or str(root), root)], ''
        return [(name, root / name) for name in names], ''
    except (OSError, ValueError, ConfigError) as error:
        return [], f'Cannot read library configuration: {error}'


def has_library_configuration(root):
    """A configured collection can open the browser without an external reader."""
    try:
        return _library_names(root) is not None
    except (OSError, ValueError, ConfigError):
        return False
