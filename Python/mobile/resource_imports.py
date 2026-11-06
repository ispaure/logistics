"""Safe private-copy import identities; no provider handles or plaintext paths."""
from hashlib import sha256
import json
from pathlib import Path
from stat import S_ISREG
from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.publication import mutation_lock
from services.identifiers import digest, uuid

MAX_ITEMS = 256
MAX_BYTES = 65536
PROVIDERS = ('managed-text', 'library', 'notebook')


class ResourceImports:
    def __init__(self, root, *, collection_root=None):
        if Path(root).is_symlink():
            raise ValueError('Import storage cannot be linked.')
        self.root = Path(root).resolve()
        if collection_root is not None and Path(collection_root).is_symlink():
            raise ValueError('Import storage cannot be linked.')
        self.collection_root = Path(collection_root).resolve() if collection_root is not None else None
        from services.documents.locations import shared_documents_path
        shared_root = shared_documents_path(Path(root))
        self.shared_root = shared_root.resolve() if shared_root is not None else None
        # Android relocates both ordinary folders to the selected drive. Only
        # admit Received Files beside Local, never the rest of that drive.
        self.received_root = (self.collection_root.parent / 'Received Files'
                              if self.collection_root is not None and self.shared_root is None else None)
        self.path = self.root / 'resource-imports.json'
        try:
            self._refresh()
        except ValueError:
            pass  # Defer reporting unreadable history until it is used.

    def _read_items(self):
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return {}
        if not S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('Invalid import index.')
        with self.path.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('Invalid import index.')
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict) or data.get('schema') != 1:
            raise ValueError('Invalid import index.')
        items = data.get('items')
        if not isinstance(items, dict) or len(items) > MAX_ITEMS:
            raise ValueError('Invalid import index.')
        for key, value in items.items():
            if (not digest(key) or not isinstance(value, dict)
                    or set(value) != {'provider', 'resource'}
                    or value['provider'] not in PROVIDERS or not uuid(value['resource'])):
                raise ValueError('Invalid import identity.')
        return items

    def _refresh(self):
        try:
            self.items = self._read_items()
        except (OSError, ValueError, RecursionError):
            self.items = {}
            self.error = 'The import index could not be restored; its original file was preserved.'
            raise ValueError(self.error) from None
        self.error = ''

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
        elif self.received_root is not None and resolved.is_relative_to(self.received_root):
            relative = resolved.relative_to(self.received_root)
            identity = 'Received Files/' + relative.as_posix()
        else:
            raise ValueError('Choose a file in Local or private Downloads.')
        components = [path, *list(path.parents)[:max(0, len(relative.parts) - 1)]]
        if any(part.is_symlink() for part in components):
            raise ValueError('Linked private-copy imports are not supported.')
        return sha256(identity.encode()).hexdigest()

    def find(self, path):
        with mutation_lock:
            self._refresh()
            return self.items.get(self.identity(path))

    def remember(self, path, provider, resource):
        key = self.identity(path)
        if provider not in PROVIDERS or not uuid(resource):
            raise ValueError('Invalid import identity.')
        with mutation_lock:
            self._refresh()
            if key not in self.items and len(self.items) >= MAX_ITEMS:
                raise ValueError(f'Private-copy import history is full (limit: {MAX_ITEMS}).')
            # The last published remember for this path replaces its mapping.
            updated = dict(self.items)
            updated[key] = dict(provider=provider, resource=resource)
            self._publish(updated)

    def forget(self, provider, resource):
        with mutation_lock:
            self._refresh()
            updated = {key: value for key, value in self.items.items()
                       if (value['provider'], value['resource']) != (provider, resource)}
            if updated != self.items:
                self._publish(updated)

    def _publish(self, items):
        atomic_write_json(self.path, dict(schema=1, items=items),
                          max_bytes=MAX_BYTES, durable_directory=True)
        self.items = items
