"""Bounded ordinary folder pins; encrypted locations are never persisted here."""
import json
from pathlib import Path
import re
from uuid import uuid4
from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.resource_provider import resource_path

LIMIT = 32
MAX_BYTES = 16384


class Locations:
    def __init__(self, root):
        if not Path(root).is_absolute():
            raise ValueError('Pinned locations require app-private absolute storage.')
        self.path = Path(root) / 'locations.json'
        self.error, self.original, self.items = '', None, []
        try:
            self.original = self.read()
            if self.original is not None:
                value = json.loads(self.original)
                if not isinstance(value, dict) or value.get('schema') != 1 or set(value) != {'schema', 'items'}:
                    raise ValueError('Invalid location schema.')
                if not isinstance(value['items'], list) or len(value['items']) > LIMIT:
                    raise ValueError('Too many pinned locations.')
                keys, identities = set(), set()
                for item in value['items']:
                    self.validate(item)
                    identity = item['kind'], item['connection'], item['path']
                    if item['id'] in keys or identity in identities:
                        raise ValueError('Duplicate location identity.')
                    keys.add(item['id'])
                    identities.add(identity)
                self.items = value['items']
        except (OSError, ValueError, TypeError):
            self.error = 'Pinned locations could not be read; the original file was preserved.'

    def read(self):
        if self.path.is_symlink():
            raise ValueError('Pinned locations cannot be linked.')
        if not self.path.exists():
            return None
        with self.path.open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Pinned locations exceed the size limit.')
        return data

    @staticmethod
    def validate(item):
        if (not isinstance(item, dict) or set(item) != {'id', 'kind', 'connection', 'path'}
                or not isinstance(item['id'], str) or re.fullmatch('[0-9a-f]{32}', item['id']) is None
                or item['kind'] not in ('local', 'remote') or not isinstance(item['path'], str)
                or len(item['path']) > 2048 or resource_path(item['path']) != item['path']):
            raise ValueError('Invalid pinned location.')
        if item['kind'] == 'local':
            if item['connection'] != '':
                raise ValueError('Invalid local identity.')
        elif not isinstance(item['connection'], str) or re.fullmatch('[0-9a-f]{64}', item['connection']) is None:
            raise ValueError('Invalid remote identity.')

    def publish(self, items):
        if self.error:
            raise ValueError(self.error)
        data = (json.dumps({'schema': 1, 'items': items}, ensure_ascii=False) + '\n').encode()
        if len(data) > MAX_BYTES:
            raise ValueError('Pinned locations exceed the size limit.')
        def check():
            if self.read() != self.original:
                raise OSError('Pinned locations changed; reload before saving.')
        atomic_write_bytes(self.path, data, validate=check)
        self.original, self.items = data, items

    def pin(self, kind, path, connection=''):
        item = dict(id=uuid4().hex, kind=kind, path=path, connection=connection)
        self.validate(item)
        existing = next((value for value in self.items if (value['kind'], value['path'], value['connection']) == (kind, path, connection)), None)
        if existing:
            return existing
        if len(self.items) >= LIMIT:
            raise ValueError('Remove a pinned folder before adding another (limit: 32).')
        self.publish([*self.items, item])
        return item

    def remove(self, key):
        self.publish([value for value in self.items if value['id'] != key])
