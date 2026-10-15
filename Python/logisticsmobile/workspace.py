"""Pure Python open-resource identities, view state and bounded restoration.

Document bytes remain owned by DocumentStore/library/provider controllers. Private
resources never enter the ordinary workspace manifest, including their names.
"""
from dataclasses import dataclass, field
import json
from pathlib import Path
from uuid import uuid4
from services.identifiers import uuid
from commonUtils.persistence import atomic_write_json

MAX_SESSIONS = 32
MAX_MANIFEST = 64 * 1024
KINDS = {'text', 'markdown', 'epub', 'comic'}
PROVIDERS = {'managed-text', 'library'}
VIEW_NUMBERS = {'cursor', 'selection_length', 'scroll_x', 'scroll_y', 'position'}



def view_state(value):
    if not isinstance(value, dict) or len(value) > 8:
        raise ValueError('Invalid workspace view state.')
    for key, item in value.items():
        if key in VIEW_NUMBERS:
            if type(item) is not int or not 0 <= item <= 2**31 - 1:
                raise ValueError('Invalid workspace position.')
        elif key == 'markdown_mode':
            if item not in ('edit', 'preview'):
                raise ValueError('Invalid Markdown mode.')
        elif key == 'markdown_split':
            if type(item) is not bool:
                raise ValueError('Invalid Markdown split preference.')
        else:
            raise ValueError('Unsupported workspace view field.')
    return dict(value)


@dataclass
class Session:
    id: str
    provider: str
    resource: str
    kind: str
    title: str = ''
    transient: bool = False
    view: dict = field(default_factory=dict)
    generation: int = 0
    dirty: bool = False

    @property
    def identity(self):
        return self.provider, self.resource


class Workspace:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('Workspace storage must be app-private and absolute.')
        self.path = root / 'workspace.json'
        self.sessions = {}
        self.active = None
        self.error = ''
        self.restore()

    def restore(self):
        if not self.path.exists():
            return
        try:
            if self.path.is_symlink() or self.path.stat().st_size > MAX_MANIFEST:
                raise ValueError('Invalid workspace file.')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('schema') != 1:
                raise ValueError('Unsupported workspace schema.')
            entries = data.get('sessions')
            if not isinstance(entries, list) or len(entries) > MAX_SESSIONS:
                raise ValueError('Invalid workspace session list.')
            sessions, identities = {}, set()
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError('Invalid workspace session.')
                key, provider, resource, kind = (entry.get(field) for field in ('id', 'provider', 'resource', 'kind'))
                if (not uuid(key) or not uuid(resource) or provider not in PROVIDERS
                        or kind not in KINDS or key in sessions or (provider, resource) in identities):
                    raise ValueError('Invalid or duplicate workspace identity.')
                sessions[key] = Session(key, provider, resource, kind, view=view_state(entry.get('view', {})))
                identities.add((provider, resource))
            active = data.get('active')
            if active is not None and (not isinstance(active, str) or active not in sessions):
                raise ValueError('Invalid active workspace session.')
            self.sessions, self.active = sessions, active
        except (OSError, ValueError, TypeError):
            self.error = 'Open-document state could not be restored; the original file was preserved.'

    def open(self, provider, resource, kind, title='', *, transient=False):
        if (not isinstance(provider, str) or not isinstance(resource, str)
                or kind not in KINDS or (not transient and (provider not in PROVIDERS or not uuid(resource)))):
            raise ValueError('Unsupported workspace resource.')
        existing = next((session for session in self.sessions.values() if session.identity == (provider, resource)), None)
        owners = getattr(self, 'window_owners', None)
        if existing is not None:
            if existing.transient != transient:
                raise ValueError('Resource privacy cannot change while it is open.')
            if owners is not None:
                owners.claim(self.window_id, (provider, resource), private=transient)
            self.active = existing.id
            return existing
        if len(self.sessions) >= MAX_SESSIONS:
            raise ValueError('Close an open document before opening another (limit: 32).')
        if owners is not None:
            owners.claim(self.window_id, (provider, resource), private=transient)
        session = Session(uuid4().hex, provider, resource, kind, title, transient)
        self.sessions[session.id] = session
        self.active = session.id
        return session

    def activate(self, key):
        if key not in self.sessions:
            raise ValueError('This document is no longer open.')
        self.active = key
        return self.sessions[key]

    def token(self, key):
        return key, self.sessions[key].generation

    def accepts(self, token):
        key, generation = token
        return key in self.sessions and self.sessions[key].generation == generation

    def invalidate(self, key):
        self.sessions[key].generation += 1

    def close(self, key, *, guard):
        session = self.sessions[key]
        if not guard(session):
            return False
        self.invalidate(key)
        del self.sessions[key]
        owners = getattr(self, 'window_owners', None)
        if owners is not None:
            owners.release(self.window_id, session.identity)
        if self.active == key:
            self.active = next(reversed(self.sessions), None)
        return True

    def forget_private(self, provider=None, *, guard):
        sensitive = [session for session in self.sessions.values()
                     if session.transient and (provider is None or session.provider == provider)]
        # Check all dirty owners before closing any of them.
        if any(not guard(session) for session in sensitive):
            return False
        for session in sensitive:
            self.close(session.id, guard=lambda value: True)
        return True

    def save(self):
        if self.error:
            raise ValueError(self.error)
        if self.path.is_symlink():
            raise ValueError('Workspace storage cannot be a symbolic link.')
        entries = [dict(id=session.id, provider=session.provider, resource=session.resource,
                        kind=session.kind, view=view_state(session.view))
                   for session in self.sessions.values()
                   if not session.transient and session.provider in PROVIDERS and uuid(session.resource)]
        ordinary = {entry['id'] for entry in entries}
        active = self.active if self.active in ordinary else (entries[-1]['id'] if entries else None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.path, dict(schema=1, active=active, sessions=entries),
                          max_bytes=MAX_MANIFEST, durable_directory=True)
