"""Non-secret desktop session destinations; credentials remain memory-only."""
import json
from pathlib import Path

from commonUtils.persistence import atomic_write_json
from commonUtils.runtime.streams import read_up_to


def record_path(context):
    return Path(context).with_suffix('.session.json')


def read(context):
    path = record_path(context)
    try:
        with path.open('rb') as stream:
            content = read_up_to(stream, 64 * 1024 + 1)
        if len(content) > 64 * 1024:
            return None
        value = json.loads(content)
        package, names = value['package'], value['remotes']
        if (value.get('schema') != 1 or not isinstance(package, str) or not Path(package).is_absolute()
                or not isinstance(names, list) or not 0 < len(names) <= 64
                or any(not isinstance(name, str) or not name or len(name) > 256 for name in names)):
            return None
        return Path(package), tuple(sorted(set(names)))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def remember(context, package, names):
    path = record_path(context)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, {'schema': 1, 'package': str(Path(package).absolute()),
                            'remotes': sorted(set(names))}, max_bytes=64 * 1024)


def contexts():
    from .configuration import get_rclone_config_dir
    return [path.with_suffix('') for path in sorted(get_rclone_config_dir().glob('*.session.json'))
            if read(path.with_suffix('')) is not None]


def forget(context):
    record_path(context).unlink(missing_ok=True)
