"""Credential-password encrypted open/recent references; plaintext lives only in RAM."""
import base64
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import weakref
from threading import RLock
from time import time_ns

from commonUtils.persistence import atomic_write_bytes

LIMIT = 128 * 1024
_managers = weakref.WeakSet()
_cache_io_lock = RLock()


def cache_path(root, key):
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid credential document cache identity.')
    root = Path(root)
    path = root / key
    if root.is_symlink() or path.is_symlink():
        raise ValueError('Credential document caches cannot be linked.')
    return path


def forget_cache(root, key=None):
    """Serialize removal against writes, including every window's copy."""
    with _cache_io_lock:
        _forget_cache(root, key)


def _forget_cache(root, key=None):
    root = Path(root)
    if root.is_symlink():
        raise ValueError('Credential document caches cannot be linked.')
    directories = [cache_path(root, key)] if key else ([cache_path(root, p.name) for p in root.iterdir()] if root.exists() else [])
    for directory in directories:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_symlink() or not path.is_file() or path.suffix != '.zip' or len(path.stem) != 64 or any(c not in '0123456789abcdef' for c in path.stem):
                raise ValueError('Unexpected credential document cache file.')
            path.unlink()
        directory.rmdir()
    for manager in tuple(_managers):
        if manager.root == root:
            manager.retire_writes(key)
            if manager.app.loop.is_running():
                manager.app.loop.call_soon_threadsafe(manager.forget_memory, key)
            else:
                manager.forget_memory(key)


class CredentialDocumentLists:
    def __init__(self, app, *, references, max_recent, reopen):
        self.app = app
        self.references, self.max_recent, self.reopen = references, max_recent, reopen
        self.root = app.private_root / 'CredentialDocumentLists'
        self.scene = sha256(getattr(app, 'window_id', 'primary').encode()).hexdigest()
        self.states = {}
        self.failed = set()
        self.refreshing = False
        self.views_pending = False
        self._queued_writes = {}
        self._write_timers = {}
        self._write_tasks = set()
        _managers.add(self)
        from .cloud import CloudClient
        CloudClient._document_list_observers.add(self)

    def credentials_changed(self):
        if self.app.active_host and not self.app.loop.is_closed():
            self.app.loop.call_soon_threadsafe(self.refresh)

    def queue_views(self):
        if not self.views_pending and self.app.active_host and not self.app.loop.is_closed():
            self.views_pending = True
            self.app.loop.call_soon(self.refresh_views)

    def refresh_views(self):
        self.views_pending = False
        if self.app.active_host and hasattr(self.app, 'routes'):
            for destination in ('home', 'documents'):
                self.app.refresh_hub(destination)

    def records(self):
        client = getattr(self.app, 'cloud_client', None)
        return {record['document_cache_id']: record for record in getattr(client, 'package_records', ())
                if not record.get('saved') and record.get('document_cache_id')}

    def path(self, key):
        directory = cache_path(self.root, key)
        path = directory / (self.scene + '.zip')
        if path.is_symlink():
            raise ValueError('Credential document caches cannot be linked.')
        return path

    def validate(self, state, credential=None):
        if not isinstance(state, dict) or set(state) != {'version', 'credential', 'open', 'recent'} or state['version'] != 1:
            raise ValueError('Invalid encrypted document lists.')
        key = state['credential']
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key) or (credential is not None and key != credential):
            raise ValueError('Encrypted document lists belong to a different credential.')
        for field, limit in (('open', 32), ('recent', self.max_recent)):
            if not isinstance(state[field], list) or len(state[field]) > limit:
                raise ValueError('Encrypted document list exceeds limits.')
            for item in state[field]:
                self.references.validate_reference(item)
                if item['source']['type'] == 'local':
                    raise ValueError('Credential cache contains an unrelated local file.')
        return state

    def notice(self):
        label = getattr(self.app, 'recovery_notice', None)
        if label is not None:
            label.text = 'Could not restore or save encrypted document lists. The existing cache was preserved.'

    def refresh(self):
        if self.refreshing or not self.app.active_host:
            return
        self.refreshing = True
        try:
            records = self.records()
            for key in set(self.states) - records.keys():
                self.forget_memory(key)
            for key in records.keys() - self.states.keys() - self.failed:
                try:
                    path = self.path(key)
                    state = dict(version=1, credential=key, open=[], recent=[])
                    if path.exists():
                        if path.stat().st_size > LIMIT + 1024:
                            raise ValueError('Encrypted document list exceeds limits.')
                        value = self.app.cloud_client.request('document_lists_open', id=key,
                            data=base64.b64encode(path.read_bytes()).decode())
                        raw = base64.b64decode(value, validate=True)
                        if len(raw) > LIMIT:
                            raise ValueError('Encrypted document list exceeds limits.')
                        state = self.validate(json.loads(raw), key)
                        if any(not self.belongs(item['source'], records[key]) for field in ('open', 'recent') for item in state[field]):
                            raise ValueError('Encrypted document lists belong to a different connection.')
                    self.states[key] = state
                    self.queue_views()
                    self.restore_open(key, state['open'])
                    self.migrate_plaintext(key, records[key])
                except (OSError, ValueError, TypeError, KeyError):
                    self.failed.add(key)
                    self.notice()
            for key, state in self.states.items():
                if key in records and key not in self.failed:
                    self.restore_open(key, state['open'])
            self.publish_recent()
        finally:
            self.refreshing = False

    def belongs(self, source, record):
        if source is None or source.get('type') == 'local':
            return False
        identity = source['identity']
        return (identity in record.get('identities', {}).values()
                or identity in record.get('crypt_identities', {}).values())

    def migrate_plaintext(self, key, record):
        history = self.app.recent_documents
        matches = [item for item in history.items if item.get('source') and self.belongs(item['source'], record)]
        if not matches:
            return
        state = self.states[key]
        state['recent'] = [*state['recent'], *(item for item in matches if item not in state['recent'])][:self.max_recent]
        # Publish ciphertext before removing old references from the ordinary file.
        self.write(key)
        for item in matches:
            history.forget(item['provider'], item['resource'])

    def restore_open(self, key, items):
        workspace = self.app.workspace
        selected = workspace.active
        for item in items:
            if any(getattr(session, 'cache_source', None) == item['source'] and (
                    session.provider == 'credential-reference' or self.app.private_sessions.available(session.id))
                    for session in workspace.sessions.values()):
                continue
            if len(workspace.sessions) >= 32:
                break
            resource = sha256((self.scene + ':' + item['resource']).encode()).hexdigest()
            session = workspace.open('credential-reference', resource, item['kind'], item['title'], transient=True)
            session.cache_id, session.cache_source = key, item['source']
        workspace.active = selected

    def publish_recent(self):
        self.app.recent_documents.private_items = sorted((item for state in self.states.values() for item in state['recent']),
            key=lambda item: item.get('opened', 0), reverse=True)[:self.max_recent]

    def write(self, key):
        with _cache_io_lock:
            self.retire_writes(key)
            if key not in self.records():
                raise ValueError('Credential document cache is locked.')
            self._write(key)

    def retire_writes(self, key=None):
        keys = set(self._queued_writes) | set(self._write_timers) if key is None else {key}
        for value in keys:
            self._queued_writes.pop(value, None)
            timer = self._write_timers.pop(value, None)
            if timer is not None:
                timer.cancel()

    def queue_write(self, key):
        if not self.app.loop.is_running():
            return self.write(key)
        client = self.app.cloud_client
        token = object(), client, getattr(client, 'generation', None)
        self._queued_writes[key] = token
        timer = self._write_timers.pop(key, None)
        if timer is not None:
            timer.cancel()
        def start():
            self._write_timers.pop(key, None)
            if self._queued_writes.get(key) is not token or key not in self.states:
                return
            state = deepcopy(self.states[key])
            async def publish():
                try:
                    await asyncio.to_thread(self._publish_snapshot, key, state, token)
                except (OSError, ValueError):
                    if self.app.active_host:
                        self.notice()
            task = self.app.loop.create_task(publish())
            self._write_tasks.add(task)
            task.add_done_callback(self._write_tasks.discard)
        self._write_timers[key] = self.app.loop.call_later(.05, start)

    def _write_valid(self, key, token):
        return (self._queued_writes.get(key) is token and self.app.active_host
                and token[1] is self.app.cloud_client
                and token[2] == getattr(token[1], 'generation', None)
                and key in self.records())

    def _publish_snapshot(self, key, state, token):
        with _cache_io_lock:
            if self._write_valid(key, token):
                self._write(key, state=state, valid=lambda: self._write_valid(key, token))
                if self._queued_writes.get(key) is token:
                    self._queued_writes.pop(key, None)

    def flush_writes(self):
        with _cache_io_lock:
            for key, token in tuple(self._queued_writes.items()):
                if self._write_valid(key, token):
                    self.write(key)
                else:
                    self.retire_writes(key)

    def _write(self, key, *, state=None, valid=lambda: True):
        state = self.states[key] if state is None else state
        self.validate(state, key)
        raw = json.dumps(state, ensure_ascii=False).encode()
        if len(raw) > LIMIT:
            raise ValueError('Encrypted document list exceeds limits.')
        value = self.app.cloud_client.request('document_lists_seal', id=key, data=base64.b64encode(raw).decode())
        encrypted = base64.b64decode(value, validate=True)
        if len(encrypted) > LIMIT + 1024:
            raise ValueError('Encrypted document list exceeds limits.')
        if not valid():
            return
        path = self.path(key)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_bytes(path, encrypted)

    def remember(self, session, source=None):
        self.refresh()
        source = source or getattr(session, 'cache_source', None)
        key = next((key for key, record in self.records().items() if self.belongs(source, record)), None)
        if key is None or key not in self.states or key in self.failed:
            return
        session.cache_id, session.cache_source = key, source
        if session.id in self.app.workspace.sessions:
            for pending in list(self.app.workspace.sessions.values()):
                if pending.provider == 'credential-reference' and getattr(pending, 'cache_source', None) == source:
                    self.app.workspace.close(pending.id, guard=lambda session: True)
        item = dict(provider='file-reference', resource=self.references.reference_id(source),
                    kind=session.kind, title=session.title, source=source, opened=time_ns())
        self.references.validate_reference(item)
        state = self.states[key]
        for field, limit in (('recent', self.max_recent), ('open', 32)):
            state[field] = [item, *(old for old in state[field] if old['resource'] != item['resource'])][:limit]
        try:
            self.queue_write(key)
        except (OSError, ValueError):
            self.notice()
        self.publish_recent()
        self.queue_views()

    def closed(self, session):
        key = getattr(session, 'cache_id', None)
        if key not in self.states:
            return
        resource = self.references.reference_id(session.cache_source)
        self.states[key]['open'] = [item for item in self.states[key]['open'] if item['resource'] != resource]
        try:
            self.queue_write(key)
        except (OSError, ValueError):
            self.notice()

    def forget_memory(self, key=None):
        with _cache_io_lock:
            self._forget_memory(key)

    def _forget_memory(self, key=None):
        self.retire_writes(key)
        keys = (set(self.states) | self.failed) if key is None else {key}
        for value in keys:
            self.states.pop(value, None)
            self.failed.discard(value)
        for session in list(self.app.workspace.sessions.values()):
            if session.provider == 'credential-reference' and getattr(session, 'cache_id', None) in keys:
                self.app.workspace.close(session.id, guard=lambda session: True)
        self.publish_recent()
        self.queue_views()

    async def open(self, session):
        try:
            opened = await self.reopen(session.cache_source)
        except (OSError, ValueError, KeyError) as error:
            import toga
            await self.app.main_window.dialog(toga.InfoDialog('Could not reopen file', str(error)))
            return False
        if opened and session.id in self.app.workspace.sessions:
            self.app.workspace.close(session.id, guard=lambda session: True)
            self.app.save_workspace()
        return opened
