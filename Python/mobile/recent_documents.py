"""Ten recent identities and reopen references; credential secrets stay with their owners."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
from pathlib import Path
from time import time_ns
from commonUtils.persistence import atomic_write_json
from .workspace import Session, uuid, KINDS, PROVIDERS
from hashlib import sha256

MAX_RECENT = 20
MAX_HISTORY_BYTES = 64 * 1024
REFERENCE_KINDS = KINDS | {'video', 'archive'}


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
        from services.documents.progress_identity import normalize_local_reference
        return normalize_local_reference(self.private_root, source)[0]

    def notebook_binding(self, resource):
        """Read the filename and draft state through the ordinary notebook binding."""
        from types import SimpleNamespace
        from services.documents.mobile_storage import notebook_source_binding
        try:
            root, binding = notebook_source_binding(
                SimpleNamespace(root=self.private_root / 'notebooks'), resource)
            if binding is not None:
                path = root / binding['path']
                source = self.normalize_source(dict(type='local', path=str(path.resolve())))
                return source, path.name, bool(binding.get('dirty'))
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def notebook_file_reference(self, item):
        """Upgrade clean, file-backed notebook history from a recovery UUID."""
        if item['provider'] != 'notebook':
            return item
        binding = self.notebook_binding(item['resource'])
        if binding is None or binding[2]:
            return item
        source, title, _ = binding
        return dict(item, provider='file-reference', resource=self.reference_id(source),
                    title=title, source=source)

    def normalize_items(self, items):
        from services.documents.help_history import is_documentation
        result, seen = [], set()
        for item in sorted(items, key=lambda item: item.get('opened', 0), reverse=True):
            if item['provider'] == 'file-reference':
                from services.documents.catalog import relocated_title
                from services.documents.progress_identity import normalize_local_reference
                before = item['source']
                source, opener = normalize_local_reference(self.private_root, before, item.get('opener'))
                if is_documentation(source, private_root=self.private_root):
                    continue
                if opener is not None:
                    item = dict(item, opener=opener)
                title = relocated_title(item['title'], before, source) if source != before else item['title']
                item = dict(item, source=source, resource=self.reference_id(source, item['kind']), title=title)
            identity = item['provider'], item['resource']
            if identity not in seen:
                result.append(item)
                seen.add(identity)
        return result

    def remember(self, session, *, replacing=None):
        if session is None or self.error:
            return
        items = [item for item in self.items
                 if (item['provider'], item['resource']) not in (session.identity, replacing)]
        source = getattr(session, 'history_source', None) if session.provider == 'notebook' else None
        if source is not None and not session.transient:
            from services.documents.help_history import is_documentation
            if is_documentation(source, private_root=self.private_root):
                return
            reference = self.reference_id(source)
            items = [item for item in items if not (
                item['provider'] == 'file-reference' and item['kind'] == 'notebook'
                and item['resource'] == reference and 'opener' not in item)]
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
        history = sorted([*self.private_items, *self.items], key=lambda item: item.get('opened', 0), reverse=True)
        # A legacy file row may be newer than its notebook row. Keep its
        # position, but use the notebook identity so reopening can recover edits.
        bindings = {}
        notebooks = {}
        for item in history:
            if item['provider'] == 'notebook':
                binding = self.notebook_binding(item['resource'])
                if binding is not None:
                    bindings[item['resource']] = binding
                    notebooks.setdefault(self.reference_id(binding[0]), item)

        sessions = []
        seen = set()
        for item in history:
            opened = item.get('opened', 0)
            if item['provider'] == 'file-reference' and item['kind'] == 'notebook' and 'opener' not in item:
                item = notebooks.get(item['resource'], item)
            identity = item['provider'], item['resource']
            if identity in seen or len(sessions) >= MAX_RECENT:
                continue
            seen.add(identity)
            values = {key: value for key, value in item.items() if key not in {'source', 'opened', 'opener'}}
            session = Session(id='', **values)
            session.source = item.get('source')
            session.history_opener = item.get('opener')
            session.opened_at = opened
            if item['provider'] == 'notebook' and item['resource'] in bindings:
                session.source, session.title, session.dirty = bindings[item['resource']]
            sessions.append(session)
        return sessions

    @staticmethod
    def valid_time(item):
        return 'opened' not in item or (type(item['opened']) is int and 0 <= item['opened'] < 2**63)

    @staticmethod
    def validate_reference(item):
        if (not {'provider', 'resource', 'kind', 'title', 'source'} <= set(item) <= {'provider', 'resource', 'kind', 'title', 'source', 'opened', 'opener'}
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
                or item['resource'] != RecentDocuments.reference_id(source, item['kind'])):
            raise ValueError('Invalid recent file source.')
        from pathlib import Path
        if source['type'] == 'local':
            from services.documents.mobile_locations import split_alias
            if not Path(source['path']).is_absolute() and split_alias(source['path']) is None:
                raise ValueError('Recent local files require a storage reference.')
        else:
            for key in ('identity', 'namespace'):
                if key in source and (len(source[key]) != 64 or any(c not in '0123456789abcdef' for c in source[key])):
                    raise ValueError('Invalid recent connection identity.')

        opener = item.get('opener')
        if opener is not None:
            from pathlib import Path, PurePosixPath
            if (not isinstance(opener, dict) or set(opener) != {'kind', 'root'}
                    or opener['kind'] != 'notes' or not isinstance(opener['root'], str)
                    or len(opener['root']) > 4096 or '\0' in opener['root']
                    or source.get('type') not in {'local', 'crypt'}):
                raise ValueError('Invalid Notes Library opening reference.')
            if source['type'] == 'local':
                from services.documents.catalog import _path_suffix
                if _path_suffix(source['path'], dict(type='local', path=opener['root'])) is None:
                    raise ValueError('Recent note is outside its library.')
            elif (PurePosixPath(source['key']).is_absolute() or '..' in PurePosixPath(source['key']).parts
                  or PurePosixPath(opener['root']).is_absolute() or '..' in PurePosixPath(opener['root']).parts
                  or not PurePosixPath(source.get('key', '')).is_relative_to(opener['root'] or '.')):
                raise ValueError('Recent note is outside its library.')

    @staticmethod
    def reference_id(source, kind=None):
        if kind == 'archive':
            source = dict(source, opener='archive')
        return sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()

    def remember_file(self, session, source, *, opener=None):
        if self.error or source is None:
            return
        from services.documents.progress_identity import normalize_local_reference
        source, opener = normalize_local_reference(self.private_root, source, opener)
        from services.documents.help_history import is_documentation
        if is_documentation(source, private_root=self.private_root):
            return
        item = dict(provider='file-reference', resource=self.reference_id(source, session.kind),
                    kind=session.kind, title=session.title, source=source, opened=time_ns())
        if opener is not None:
            item['opener'] = dict(opener)
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
        from services.documents.catalog import relocated_source, relocated_title, relocated_opener
        if self.error:
            raise ValueError('Recent history could not be read; it was preserved.')
        items = []
        for item in self.items:
            candidate = self.notebook_file_reference(item)
            before = candidate.get('source')
            after = relocated_source(before, source, destination) if before is not None else before
            if before is not after:
                if after is None:
                    continue
                item = dict(candidate, source=after, resource=self.reference_id(after, candidate['kind']),
                            title=relocated_title(candidate['title'], before, after, names=names))
                if 'opener' in item:
                    item['opener'] = relocated_opener(item['opener'], source, destination)
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
