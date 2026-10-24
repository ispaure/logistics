"""Safe private-copy import identities; no provider handles or plaintext paths."""
from hashlib import sha256
import json
from pathlib import Path
from commonUtils.persistence import atomic_write_json
from .workspace import uuid
from services.identifiers import digest


class ResourceImports:
    def __init__(self, root, *, collection_root=None):
        if Path(root).is_symlink():
            raise ValueError('Import storage cannot be linked.')
        self.root = Path(root).resolve()
        if collection_root is not None and Path(collection_root).is_symlink():
            raise ValueError('Import storage cannot be linked.')
        self.collection_root = Path(collection_root).resolve() if collection_root is not None else None
        from features.rclone.mobile.storage_location import shared_documents_path
        shared_root = shared_documents_path(Path(root))
        self.shared_root = shared_root.resolve() if shared_root is not None else None
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
        resolved = path.resolve()
        if resolved.is_relative_to(self.root):
            relative = resolved.relative_to(self.root)
            identity = relative.as_posix()
        elif self.collection_root is not None and resolved.is_relative_to(self.collection_root):
            relative = resolved.relative_to(self.collection_root)
            # Preserve the pre-migration LocalFiles identity when iOS exposes
            # Local in Documents, or Android moves the collection to an SD card.
            identity = 'LocalFiles/' + relative.as_posix()
        elif self.shared_root is not None and resolved.is_relative_to(self.shared_root):
            relative = resolved.relative_to(self.shared_root)
            identity = 'SharedFiles/' + relative.as_posix()
        else:
            raise ValueError('Choose a file in Local or private Downloads.')
        components = [path, *list(path.parents)[:max(0, len(relative.parts) - 1)]]
        if any(part.is_symlink() for part in components):
            raise ValueError('Linked private-copy imports are not supported.')
        return sha256(identity.encode()).hexdigest()

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

    def forget(self, provider, resource):
        if self.error or self.path.is_symlink():
            raise ValueError(self.error or 'Import index cannot be linked.')
        updated = {key: value for key, value in self.items.items()
                   if (value['provider'], value['resource']) != (provider, resource)}
        if updated != self.items:
            atomic_write_json(self.path, dict(schema=1, items=updated), max_bytes=65536, durable_directory=True)
            self.items = updated
