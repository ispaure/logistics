"""Safe private-copy import identities; no provider handles or plaintext paths."""
from hashlib import sha256
import json
from pathlib import Path
from commonUtils.persistence import atomic_write_json
from .workspace import uuid
from .pull_jobs import digest


class ResourceImports:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'resource-imports.json'
        self.items, self.error = {}, ''
        if self.path.exists():
            try:
                if self.path.is_symlink() or self.path.stat().st_size > 65536:
                    raise ValueError('Invalid import index.')
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict) or data.get('schema') != 1:
                    raise ValueError('Invalid import index.')
                items = data['items']
                if not isinstance(items, dict) or len(items) > 256:
                    raise ValueError('Invalid import index.')
                for key, value in items.items():
                    if not digest(key) or not isinstance(value, dict) or set(value) != {'provider', 'resource'} or value['provider'] not in {'managed-text', 'library'} or not uuid(value['resource']):
                        raise ValueError('Invalid import identity.')
                self.items = items
            except (OSError, ValueError, TypeError, KeyError):
                self.error = 'The import index could not be restored; its original file was preserved.'

    def identity(self, path):
        path = Path(path)
        relative = path.relative_to(self.root)
        if path.is_symlink() or any(part.is_symlink() for part in path.parents if part != self.root):
            raise ValueError('Linked private-copy imports are not supported.')
        return sha256(relative.as_posix().encode()).hexdigest()

    def find(self, path):
        if self.error:
            raise ValueError(self.error)
        return self.items.get(self.identity(path))

    def remember(self, path, provider, resource):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or 'Import index cannot be linked.')
        key = self.identity(path)
        if key not in self.items and len(self.items) >= 256:
            raise ValueError('Private-copy import history is full (limit: 256).')
        updated = dict(self.items)
        updated[key] = dict(provider=provider, resource=resource)
        atomic_write_json(self.path, dict(schema=1, items=updated), max_bytes=65536, durable_directory=True)
        self.items = updated
