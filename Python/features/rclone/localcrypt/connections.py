"""Nonsecret credential associations for decrypted local copies.

Records live in application support, outside the local sync destination.
"""
from hashlib import sha256
import json
from pathlib import Path

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import serialize_mutation
from features.rclone.localcrypt.mapping import Connection, is_linked
from features.rclone.storage import local_records


def storage_root():
    import config
    return Path(config.LogisticsConfig(create_resources=False).path_remote_local).absolute()


class LocalConnection(Connection):
    @property
    def record(self):
        identity = sha256((str(self.package) + '\0' + self.remote).encode()).hexdigest()
        return local_records(self.root) / (identity + '.json')

    def check(self):
        self.data  # Validate the remote's folder spelling before any transfer.
        if is_linked(self.record.parent) or is_linked(self.record):
            raise ValueError('Local credential associations cannot be stored through a link.')
        mapped = connections(self.root, include_missing=True)
        own = next((item for item in mapped if item.record == self.record), None)
        if self.record.exists() and own != self:
            raise ValueError('The existing local credential association is invalid.')
        for item in mapped:
            if item != self and item.data.name.casefold() == self.data.name.casefold():
                raise ValueError(f'Local folder {self.remote!r} belongs to another credential package.')

    @serialize_mutation
    def publish(self):
        self.check()
        self.record.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_json(self.record, {'schema': 1, 'package': str(self.package), 'remote': self.remote})


def connections(root=None, *, include_missing=False):
    root = Path(root or storage_root()).absolute()
    directory = local_records(root)
    if not directory.is_dir() or is_linked(directory):
        return []
    result = []
    for record in directory.glob('*.json'):
        try:
            if is_linked(record) or record.stat().st_size > 8192:
                continue
            data = json.loads(record.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or set(data) != {'schema', 'package', 'remote'} or data['schema'] != 1:
                continue
            package = Path(data['package'])
            if not package.is_absolute() or not isinstance(data['remote'], str):
                continue
            item = LocalConnection(package, data['remote'], root)
            if item.record != record or (not include_missing and not item.data.is_dir()):
                continue
            item.data
            result.append(item)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(result, key=lambda item: (str(item.package), item.remote))


def for_path(path):
    path = Path(path).absolute()
    return next((item for item in connections() if path == item.data or item.data in path.parents), None)
