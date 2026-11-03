"""Bounded favourites and recent references, with credential-password buckets."""
from hashlib import sha256
import json
from pathlib import Path
from threading import RLock
from time import time_ns
from commonUtils.persistence import atomic_write_bytes

LIMIT = 128 * 1024
_lock = RLock()


class DocumentCatalog:
    def __init__(self, root):
        self.root = Path(root) / 'DocumentCatalog'

    def path(self, cipher=None):
        identity = cipher.identity if cipher is not None else 'local'
        if identity != 'local' and (len(identity) != 64 or any(c not in '0123456789abcdef' for c in identity)):
            raise ValueError('Invalid credential identity.')
        path = self.root / (identity + ('.zip' if cipher is not None else '.json'))
        if self.root.is_symlink() or path.is_symlink():
            raise ValueError('Document lists cannot be linked.')
        return path

    def read(self, cipher=None):
        path = self.path(cipher)
        if not path.exists():
            return dict(favourites=[], recent=[])
        if path.stat().st_size > LIMIT + 1024:
            raise ValueError('Document list exceeds limits; original preserved.')
        data = path.read_bytes()
        if cipher is not None:
            data = cipher.transform(data, decode=True)
        value = json.loads(data)
        if not isinstance(value, dict) or set(value) != {'favourites', 'recent'}:
            raise ValueError('Invalid document list; original preserved.')
        for field, maximum in (('favourites', 100), ('recent', 10)):
            rows = value[field]
            if not isinstance(rows, list) or len(rows) > maximum:
                raise ValueError('Invalid document list size.')
            for row in rows:
                if (not isinstance(row, dict) or set(row) != {'id', 'title', 'source', 'opener', 'updated'}
                        or not isinstance(row['title'], str) or len(row['title']) > 1024
                        or not isinstance(row['source'], dict) or not isinstance(row['opener'], dict)
                        or type(row['updated']) is not int or row['id'] != self.identity(row['source'])):
                    raise ValueError('Invalid document reference.')
        return value

    @staticmethod
    def identity(source):
        return sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()

    def save(self, value, cipher=None):
        data = json.dumps(value, ensure_ascii=False).encode()
        if len(data) > LIMIT:
            raise ValueError('Document list exceeds limits.')
        path = self.path(cipher)
        if cipher is not None:
            data = cipher.transform(data)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write_bytes(path, data)

    def remember(self, source, title, opener, *, favourite=False, cipher=None):
        with _lock:
            value = self.read(cipher)
            row = dict(id=self.identity(source), title=title, source=source, opener=opener, updated=time_ns())
            field, maximum = ('favourites', 100) if favourite else ('recent', 10)
            value[field] = [row, *(old for old in value[field] if old['id'] != row['id'])][:maximum]
            self.save(value, cipher)

    def remove(self, identity, *, cipher=None):
        with _lock:
            value = self.read(cipher)
            value['favourites'] = [row for row in value['favourites'] if row['id'] != identity]
            self.save(value, cipher)

    def entries(self, field='favourites', *, ciphers=()):
        with _lock:
            rows = list(self.read()[field])
            for cipher in ciphers:
                rows.extend(self.read(cipher)[field])
            # A re-favourite through another viewer replaces that opening method.
            unique = {}
            for row in sorted(rows, key=lambda row: row['updated'], reverse=True):
                unique.setdefault(row['id'], row)
            return list(unique.values())
