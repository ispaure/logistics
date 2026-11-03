"""Ten recent identities and reopen references; credential secrets stay with their owners."""
import json
from time import time_ns
from commonUtils.persistence import atomic_write_json
from .workspace import Session, uuid, KINDS, PROVIDERS
from hashlib import sha256

MAX_RECENT = 10
MAX_HISTORY_BYTES = 64 * 1024
REFERENCE_KINDS = KINDS | {'video'}


class RecentDocuments:
    def __init__(self, root, *, private_root=None):
        self.private_root = root if private_root is None else private_root
        self.path = root / 'recent-documents.json'
        from services.documents.history_controls import _recent
        _recent.add(self)
        self.items = []
        self.private_items = []
        self.error = ''
        try:
            if self.path.is_symlink():
                raise ValueError('Recent documents cannot be linked.')
            if self.path.exists():
                if self.path.stat().st_size > MAX_HISTORY_BYTES:
                    raise ValueError('Recent document history is too large.')
                items = json.loads(self.path.read_text())
                if not isinstance(items, list) or len(items) > MAX_RECENT:
                    raise ValueError('Invalid recent document history.')
                for item in items:
                    if isinstance(item, dict) and item.get('provider') == 'file-reference':
                        self.validate_reference(item)
                        continue
                    if (not isinstance(item, dict) or not {'provider', 'resource', 'kind'} <= set(item) <= {'provider', 'resource', 'kind', 'opened'}
                            or item['provider'] not in PROVIDERS or not uuid(item['resource'])
                            or item['kind'] not in KINDS or not self.valid_time(item)):
                        raise ValueError('Invalid recent document identity.')
                self.items = self.normalize_items(items)
                if self.items != items:
                    atomic_write_json(self.path, self.items, max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
        except (OSError, ValueError, TypeError) as error:
            self.error = str(error)

    def normalize_source(self, source):
        if source.get('type') != 'local':
            return source
        from types import SimpleNamespace
        from .document_sources import local_document_path
        path = local_document_path(SimpleNamespace(private_root=self.private_root), source['path'])
        return dict(source, path=str(path))

    def normalize_items(self, items):
        result, seen = [], set()
        for item in sorted(items, key=lambda item: item.get('opened', 0), reverse=True):
            if item['provider'] == 'file-reference':
                source = self.normalize_source(item['source'])
                item = dict(item, source=source, resource=self.reference_id(source))
            identity = item['provider'], item['resource']
            if identity not in seen:
                result.append(item)
                seen.add(identity)
        return result

    def remember(self, session):
        if session is None or self.error:
            return
        items = [item for item in self.items
                 if (item['provider'], item['resource']) != session.identity]
        if not session.transient and session.provider in PROVIDERS:
            item = dict(provider=session.provider, resource=session.resource, kind=session.kind, opened=time_ns())
            if self.items and self.items[0]['provider'] == session.provider and self.items[0]['resource'] == session.resource and self.items[0]['kind'] == session.kind:
                item = self.items[0]
            items.insert(0, item)
        items = items[:MAX_RECENT]
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
            self.items = items

    def sessions(self):
        sessions = []
        seen = set()
        for item in sorted([*self.private_items, *self.items], key=lambda item: item.get('opened', 0), reverse=True):
            identity = item['provider'], item['resource']
            if identity in seen or len(sessions) >= MAX_RECENT:
                continue
            seen.add(identity)
            values = {key: value for key, value in item.items() if key not in {'source', 'opened'}}
            session = Session(id='', **values)
            session.source = item.get('source')
            sessions.append(session)
        return sessions

    @staticmethod
    def valid_time(item):
        return 'opened' not in item or (type(item['opened']) is int and 0 <= item['opened'] < 2**63)

    @staticmethod
    def validate_reference(item):
        if (not {'provider', 'resource', 'kind', 'title', 'source'} <= set(item) <= {'provider', 'resource', 'kind', 'title', 'source', 'opened'}
                or item['kind'] not in REFERENCE_KINDS or not isinstance(item['title'], str)
                or len(item['title']) > 1024 or not isinstance(item['source'], dict) or not RecentDocuments.valid_time(item)):
            raise ValueError('Invalid recent file reference.')
        source = item['source']
        expected = {'local': {'type', 'path'},
                    'remote': {'type', 'remote', 'identity', 'key'},
                    'crypt': {'type', 'remote', 'identity', 'key', 'namespace'},
                    'download': {'type', 'remote', 'identity', 'key'}}
        if (source.get('type') not in expected or set(source) != expected[source['type']]
                or any(not isinstance(value, str) or not value or len(value) > 4096 for value in source.values())
                or item['resource'] != RecentDocuments.reference_id(source)):
            raise ValueError('Invalid recent file source.')
        from pathlib import Path
        if source['type'] == 'local':
            if not Path(source['path']).is_absolute():
                raise ValueError('Recent local files require an absolute path.')
        else:
            for key in ('identity', 'namespace'):
                if key in source and (len(source[key]) != 64 or any(c not in '0123456789abcdef' for c in source[key])):
                    raise ValueError('Invalid recent connection identity.')

    @staticmethod
    def reference_id(source):
        return sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()

    def remember_file(self, session, source):
        if self.error or source is None:
            return
        source = self.normalize_source(source)
        item = dict(provider='file-reference', resource=self.reference_id(source),
                    kind=session.kind, title=session.title, source=source, opened=time_ns())
        if self.items and all(self.items[0].get(key) == value for key, value in item.items() if key != 'opened'):
            item = self.items[0]
        self.validate_reference(item)
        items = [item, *(old for old in self.items if old['resource'] != item['resource'])][:MAX_RECENT]
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
            self.items = items

    def forget(self, provider, resource):
        if self.error:
            raise ValueError('Recent history could not be read; it was preserved.')
        items = [item for item in self.items
                 if (item['provider'], item['resource']) != (provider, resource)]
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
            self.items = items

    def relocate(self, source, destination=None, *, names=None):
        """Follow renamed files and descendants even when no reader is open."""
        from services.documents.catalog import relocated_source, relocated_title
        if self.error:
            raise ValueError('Recent history could not be read; it was preserved.')
        items = []
        for item in self.items:
            before = item.get('source')
            after = relocated_source(before, source, destination) if before is not None else before
            if before is not after:
                if after is None:
                    continue
                item = dict(item, source=after, resource=self.reference_id(after),
                            title=relocated_title(item['title'], before, after, names=names))
            items.append(item)
        items = self.normalize_items(items)
        if items != self.items:
            atomic_write_json(self.path, items, max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
            self.items = items

    def clear(self):
        """Clear reopen history while preserving documents and open sessions."""
        atomic_write_json(self.path, [], max_bytes=MAX_HISTORY_BYTES, durable_directory=True)
        self.items = []
        self.private_items = []
        self.error = ''
