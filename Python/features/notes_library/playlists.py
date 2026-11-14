"""Notes Library playlist records and metadata-only playback checkpoints."""

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from threading import RLock
from time import time_ns
from uuid import uuid4

from commonUtils.persistence.locking import file_lock
from commonUtils.runtime.resources.paths import resource_path
from services.documents.catalog import CredentialBuckets
from services.documents.credential_state import DesktopCredentialCipher, MobileCredentialCipher, sources
from services.documents.progress import _credential_revocation
from services.documents.progress_identity import progress_source
from services.documents.storage import check_document_access

from .notes import LIBRARY_MARKER, MARKDOWN

MAX_PLAYLISTS = 100
MAX_ENTRIES = 200
MAX_NAME = 120
MAX_PATH = 4096
_lock = RLock()
_memory = {}
_listeners = {}


@dataclass(frozen=True)
class PlaylistEntry:
    id: str
    path: str


@dataclass(frozen=True)
class Playlist:
    id: str
    name: str
    entries: tuple[PlaylistEntry, ...]
    active_id: str | None
    position: int
    revision: str
    observed: int
    scope: str
    bucket: str
    session_only: bool


def _identifier(value):
    return isinstance(value, str) and len(value) == 32 and all(char in '0123456789abcdef' for char in value)


def _name(name):
    name = name.strip()
    if not name or len(name) > MAX_NAME or any(ord(char) < 32 for char in name):
        raise ValueError('Enter a playlist name up to 120 characters.')
    return name


def _markdown_path(path):
    if not isinstance(path, str) or len(path) > MAX_PATH or resource_path(path) != path:
        raise ValueError('Choose a Markdown document in this library.')
    if PurePosixPath(path).suffix.lower() not in MARKDOWN:
        raise ValueError('Choose a Markdown document.')
    return path


def _decode(raw, bucket):
    if not isinstance(raw, dict) or raw.get('version') != 1 or not isinstance(raw.get('playlists'), list):
        raise ValueError('Playlist settings could not be read.')
    rows = raw['playlists']
    if len(rows) > MAX_PLAYLISTS:
        raise ValueError('Playlist settings exceed the limit.')
    result = {}
    try:
        for row in rows:
            record = Playlist(**row, bucket=bucket, session_only=False)
            entries = tuple(PlaylistEntry(**entry) for entry in record.entries)
            ids = {entry.id for entry in entries}
            if (not _identifier(record.id) or record.id in result or _name(record.name) != record.name
                    or not isinstance(record.scope, str) or len(record.scope) != 64
                    or len(entries) > MAX_ENTRIES or len(ids) != len(entries)
                    or any(not _identifier(entry.id) or _markdown_path(entry.path) != entry.path for entry in entries)
                    or (record.active_id is not None and record.active_id not in ids)
                    or type(record.position) is not int or not 0 <= record.position <= 32 * 1024 * 1024
                    or type(record.observed) is not int or record.observed < 0
                    or not isinstance(record.revision, str)
                    or len(record.revision) not in (0, 64)):
                raise ValueError('Invalid playlist record.')
            result[record.id] = replace(record, entries=entries)
    except (AttributeError, TypeError, KeyError) as error:
        raise ValueError('Invalid playlist record.') from error
    return result


class PlaylistStore:
    def __init__(self, root, *, app=None):
        self.root = Path(root).resolve() / 'NotesPlaylists'
        self.app = app
        self.buckets = CredentialBuckets(self.root, 'playlists')

    def for_library(self, library):
        return LibraryPlaylists(self, library)

    @contextmanager
    def transaction(self):
        with _lock:
            lock = self.root / '.write.lock'
            if self.root.is_symlink() or lock.is_symlink():
                raise ValueError('Linked playlist settings are unavailable.')
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            with file_lock(lock, timeout=1) as acquired:
                if not acquired:
                    raise OSError('Playlist settings are busy.')
                yield

    def read(self, cipher=None):
        bucket = cipher.identity if cipher is not None else 'local'
        try:
            raw = self.buckets.read(cipher)
        except FileNotFoundError:
            return {}
        return _decode(raw, bucket)

    def save(self, records, cipher=None, *, validate=lambda: None):
        rows = []
        for record in records.values():
            row = asdict(record)
            del row['bucket'], row['session_only']
            rows.append(row)
        self.buckets.save(dict(version=1, playlists=rows), cipher, validate=validate)

    def all(self, *, ciphers=()):
        with _lock:
            rows = list(self.read().values())
            readable = self._readable(ciphers)
            for _, records in readable.values():
                rows.extend(records.values())
            for key, (revoked, records) in tuple(_memory.items()):
                if key[0] == self.root:
                    if revoked():
                        del _memory[key]
                    else:
                        rows.extend(records.values())
        return tuple(sorted(rows, key=lambda record: (record.name.casefold(), record.id)))

    def _readable(self, ciphers):
        readable = {}
        for cipher in ciphers:
            try:
                key = cipher.identity
                if key not in readable:
                    readable[key] = cipher, self.read(cipher)
            except (OSError, ValueError):
                continue
        return readable

    def _locked(self, ciphers):
        unlocked = self._readable(ciphers)
        return tuple(identity for identity in self.buckets.protected_identities() if identity not in unlocked)

    def locked_count(self, *, ciphers=()):
        with _lock:
            return len(self._locked(ciphers))

    def clear_locked(self, *, ciphers=()):
        with self.transaction():
            locked = self._locked(ciphers)
            for identity in locked:
                self.buckets.delete_protected(identity)
        if locked:
            with _lock:
                callbacks = {callback for (root, _), listeners in _listeners.items()
                             if root == self.root for callback in listeners}
            for callback in callbacks:
                callback()

    def delete_record(self, record, *, ciphers=()):
        with self.transaction():
            key = self.root, record.scope
            if record.session_only:
                state = _memory.get(key)
                if state is not None:
                    state[1].pop(record.id, None)
            else:
                if record.bucket == 'local':
                    cipher, rows = None, self.read()
                else:
                    cipher, rows = self._readable(ciphers).get(record.bucket, (None, None))
                    if rows is None:
                        raise PermissionError('Unlock the playlist before deleting it.')
                if rows.pop(record.id, None) is not None:
                    self.save(rows, cipher)
        self.notify(record.scope)

    def notify(self, scope):
        with _lock:
            callbacks = tuple(_listeners.get((self.root, scope), ()))
        for callback in callbacks:
            callback()


class LibraryPlaylists:
    """Scope each playlist to one admitted provider and library root."""

    def __init__(self, store, library):
        from hashlib import sha256
        import json

        self.store, self.library = store, library
        self.provider = library.provider
        self._grant = getattr(self.provider, 'capture_access', lambda path: lambda: None)('')
        marker = str(PurePosixPath(library.root or '.') / LIBRARY_MARKER)
        identity, protected, _ = progress_source(self.provider, marker, app=store.app)
        self.scope = sha256(json.dumps(identity).encode()).hexdigest()
        self._revoked = _credential_revocation(tuple(sources(self.provider)), store.app)
        self.key = store.root, self.scope
        self._cipher = None
        if protected is not None:
            if store.app is not None:
                self._cipher = MobileCredentialCipher(protected, store.app)
            else:
                self._cipher = DesktopCredentialCipher(protected)
        self.private = identity[0] != 'local'

    def revoked(self):
        if self._revoked():
            return True
        try:
            self._grant()
        except (OSError, ValueError):
            return True
        return False

    def _access(self):
        if self.revoked():
            self.retire_memory()
            raise PermissionError('Playlist access ended. Reopen the library.')
        check_document_access(self.provider)

    def _storage(self):
        self._access()
        if not self.private:
            return 'local', None
        if self._cipher is not None:
            try:
                return self._cipher.identity, self._cipher
            except PermissionError:
                pass
        return 'memory', None

    def retire_memory(self):
        if self.revoked():
            with _lock:
                state = _memory.get(self.key)
                if state is not None and state[0]():
                    _memory.pop(self.key, None)

    def _rows(self, bucket, cipher):
        if bucket != 'memory':
            return self.store.read(cipher)
        state = _memory.get(self.key)
        if state is not None and not state[0]():
            return state[1].copy()
        _memory.pop(self.key, None)
        return {}

    @property
    def session_only(self):
        return self._storage()[0] == 'memory'

    def subscribe(self, callback):
        with _lock:
            _listeners.setdefault(self.key, set()).add(callback)

        def unsubscribe():
            with _lock:
                listeners = _listeners.get(self.key)
                if listeners is not None:
                    listeners.discard(callback)
                    if not listeners:
                        _listeners.pop(self.key, None)

        return unsubscribe

    def list(self):
        with _lock:
            bucket, cipher = self._storage()
            rows = self._rows(bucket, cipher)
            memory = self._rows('memory', None) if bucket != 'memory' and self.private else {}
            return tuple(sorted((row for row in (*rows.values(), *memory.values()) if row.scope == self.scope),
                                key=lambda record: (record.name.casefold(), record.id)))

    def get(self, playlist_id):
        return next((row for row in self.list() if row.id == playlist_id), None)

    def has_protected_bucket(self, record):
        """Check whether an encrypted bucket was cleared without accessing it."""
        return (record.bucket in ('local', 'memory')
                or (self.store.root / (record.bucket + '.zip')).is_file())

    def _change(self, playlist_id, change, *, notify=True, allow_missing=False):
        with _lock:
            bucket, cipher = self._storage()
            if playlist_id in self._rows('memory', None):
                bucket, cipher = 'memory', None
            context = _lock if bucket == 'memory' else self.store.transaction()
            with context:
                rows = self._rows(bucket, cipher)
                old = rows.get(playlist_id)
                if (old is not None and old.scope != self.scope) or (old is None and allow_missing is False):
                    raise ValueError('This playlist is unavailable.')
                result = change(old, bucket)
                if old == result:
                    return result
                if result is None:
                    del rows[playlist_id]
                else:
                    rows[playlist_id] = result
                if len(rows) > MAX_PLAYLISTS:
                    raise ValueError('Too many saved playlists.')
                self._access()
                if bucket == 'memory':
                    _memory[self.key] = self.revoked, rows
                else:
                    self.store.save(rows, cipher, validate=self._access)
        if notify:
            self.store.notify(self.scope)
        return result

    def create(self, name):
        name = _name(name)
        identity = uuid4().hex
        return self._change(identity, lambda old, bucket: Playlist(
            identity, name, (), None, 0, '', 0, self.scope, bucket, bucket == 'memory'), allow_missing=True)

    def rename(self, playlist_id, name):
        name = _name(name)
        return self._change(playlist_id, lambda row, bucket: replace(row, name=name))

    def delete(self, playlist_id):
        self._change(playlist_id, lambda row, bucket: None)

    def _path(self, path):
        return _markdown_path(self.library.contained(path))

    def add(self, playlist_id, path):
        entry = PlaylistEntry(uuid4().hex, self._path(path))

        def append(row, bucket):
            if len(row.entries) >= MAX_ENTRIES:
                raise ValueError('A playlist can contain up to 200 documents.')
            return replace(row, entries=(*row.entries, entry))

        return self._change(playlist_id, append)

    @staticmethod
    def _entry_index(row, entry_id):
        for index, entry in enumerate(row.entries):
            if entry.id == entry_id:
                return index
        raise ValueError('This playlist entry is unavailable.')

    def move(self, playlist_id, entry_id, index):
        def reorder(row, bucket):
            entries = list(row.entries)
            entry = entries.pop(self._entry_index(row, entry_id))
            entries.insert(max(0, index), entry)
            return replace(row, entries=tuple(entries))

        return self._change(playlist_id, reorder)

    def remove(self, playlist_id, entry_id):
        def remove(row, bucket):
            index = self._entry_index(row, entry_id)
            entries = row.entries[:index] + row.entries[index + 1:]
            if row.active_id == entry_id:
                following = entries[min(index, len(entries) - 1)].id if entries else None
                return replace(row, entries=entries, active_id=following, position=0, revision='', observed=time_ns())
            return replace(row, entries=entries)

        return self._change(playlist_id, remove)

    def replace(self, playlist_id, entry_id, path):
        entry = PlaylistEntry(entry_id, self._path(path))

        def repair(row, bucket):
            index = self._entry_index(row, entry_id)
            entries = row.entries[:index] + (entry,) + row.entries[index + 1:]
            if row.active_id == entry_id:
                return replace(row, entries=entries, position=0, revision='', observed=time_ns())
            return replace(row, entries=entries)

        return self._change(playlist_id, repair)

    def checkpoint(self, playlist_id, entry, position, revision, observed):
        """Apply only a live entry's newest observation. Never recreate records."""
        def save(row, bucket):
            if row is None or entry not in row.entries or row.observed >= observed:
                return row
            return replace(row, active_id=entry.id, position=position, revision=revision, observed=observed)

        return self._change(playlist_id, save, notify=False, allow_missing=True)
