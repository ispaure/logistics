"""Shared observation order and storage selection for document readers.

Hosts observe successfully displayed locations, then flush those observations on
their existing debounce/lifecycle workers. Only durable I/O holds the store lock.
"""

from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path
from threading import RLock
from time import time_ns
from weakref import ref, WeakValueDictionary

from .credential_state import (
    CredentialState, PreviousPasswordRequired, _io_lock, checkpoint_write_lock,
    position_generation, sources,
)
from .progress_identity import document_identity, external_file_identity, ordinary_local_provider, progress_source
from .progress_store import (
    EncryptedCheckpoints, IncompatibleCheckpoint, LocalCheckpoints, checkpoint, encode,
    local_checkpoint_files, read_local_checkpoint, revision_binding,
)


class ProgressStatus(str, Enum):
    RESTORED = 'restored'
    ABSENT = 'absent'
    INCOMPATIBLE = 'incompatible'
    SESSION_ONLY = 'session-only'
    LOCKED = 'locked'
    ERROR = 'error'
    FENCED = 'fenced'
    SAVED = 'saved'
    WRITE_FAILED = 'write-failed'
    STALE = 'stale'


class ProgressMode(str, Enum):
    LOCAL = 'local'
    ENCRYPTED = 'encrypted'
    SESSION_MEMORY = 'session-memory'


class _Fenced(OSError):
    pass


class _Stale(OSError):
    pass


_ERRORS = (OSError, ValueError, TypeError, RuntimeError, RecursionError)
_BOOKMARKS = ('bookmarks', 'epub_bookmarks')
_MAX_MEMORY_SECTIONS = 64
_observation_lock = RLock()
_channels = WeakValueDictionary()
_memory = OrderedDict()
_sequence = 0


@dataclass(frozen=True)
class _Observation:
    owner: object
    sequence: int
    sections: tuple


@dataclass(frozen=True)
class _Pending:
    observation: _Observation
    payload: bytes
    revision: str
    locator_version: int
    revoked: object

    def matches(self, state):
        return self.revision == state.revision and self.locator_version == state.locator_version


class _Channel:
    def __init__(self):
        self.pending = None
        self.fenced = False


def _next_sequence(previous=0):
    global _sequence
    with _observation_lock:
        _sequence = max(_sequence + 1, previous + 1, time_ns())
        return _sequence


def fence_positions(root):
    """Evict position memory at Clear; bookmark memory is independent."""
    root = Path(root).resolve()
    with _observation_lock:
        for key, channel in tuple(_channels.items()):
            if key[0] == root and key[-1] == 'positions':
                channel.fenced = True
                channel.pending = None
                _channels.pop(key, None)
        for key in tuple(_memory):
            if key[0] == root and key[-1] == 'positions':
                del _memory[key]


def _fence_local_document(root, identity):
    with _observation_lock:
        for key, channel in tuple(_channels.items()):
            if key[:2] == (root, identity):
                channel.fenced = True
                channel.pending = None
                _channels.pop(key, None)


def prepare_local_progress_move(app, provider, source, destination, target, *, cancelled):
    """Capture a local mutation's source file identities before publication.

    The mutation owner calls this inside its existing mutation lock, then calls
    the returned function only after a successful move with the source removed.
    """
    from commonUtils.filesystem.snapshots import verified_file_snapshot
    from commonUtils.runtime.platform import OS, get_os
    from commonUtils.runtime.resources.mutations import inventory

    provider, destination = ordinary_local_provider(provider), ordinary_local_provider(destination)
    if provider is None or destination is None:
        return lambda: None
    root = Path(app.private_root).resolve()
    if not any((root / section / 'Local').is_dir() for section in ('ReaderPositions', 'ReaderBookmarks')):
        return lambda: None
    generation = position_generation(root)
    candidates = []
    may_stream = provider.storage_id != destination.storage_id or get_os() is OS.ANDROID
    for relative, row in inventory(provider, source, cancelled=cancelled).items():
        if row['directory']:
            continue
        old = document_identity(provider, row['path'], app=app)
        if any(LocalCheckpoints.directory(root, old, bookmarks=marked).is_dir() for marked in (False, True)):
            key = '/'.join(part for part in (target, relative) if part)
            digest = None
            if may_stream:
                snapshot, digest = verified_file_snapshot(provider.transfer_location(row['path']), cancelled=cancelled)
                if snapshot != row['revision']:
                    raise ValueError('Source changed while preparing to transfer reader history.')
            candidates.append((old, row['revision'], key, digest))

    def relocate():
        for old, original_revision, key, digest in candidates:
            current = destination.entry(key)['revision']
            if current[:4] != original_revision[:4]:
                # The mutation owner confirmed a verified copy with source
                # removal. Independently bind this destination to the exact
                # pre-move source revision that owned the checkpoint.
                if digest is None:
                    raise ValueError('Reader history could not be associated with the moved file.')
                observed, current_digest = verified_file_snapshot(destination.transfer_location(key))
                if observed != current or current_digest != digest:
                    raise ValueError('Reader history could not be associated with the moved file.')
            new = document_identity(destination, key, app=app)
            if new != old:
                def validate():
                    if destination.entry(key)['revision'] != current:
                        raise ValueError('The moved file changed before reader history could follow it.')

                _relocate_local_checkpoints(root, old, new, original_revision, current, generation, validate)

    return relocate


def _relocate_local_checkpoints(root, old, new, original_revision, current_revision, generation, validate):
    old_binding, _ = revision_binding(original_revision)
    new_binding, _ = revision_binding(current_revision)
    with _io_lock, checkpoint_write_lock(root):
        _fence_local_document(root, old)
        for marked in (False, True):
            if not marked and generation != position_generation(root):
                continue
            directory = LocalCheckpoints.directory(root, old, bookmarks=marked)
            for path in local_checkpoint_files(directory):
                record = read_local_checkpoint(path)
                kind = record.get('kind') if isinstance(record, dict) else None
                if not isinstance(kind, str) or not kind or len(kind) > 64:
                    raise ValueError('Invalid reader state was preserved.')
                origin = LocalCheckpoints(root, old, kind, bookmarks=marked)
                if path != origin.location():
                    raise ValueError('Invalid reader state binding was preserved.')
                checkpoint(record, origin.identity, kind, '' if marked else generation)
                target = LocalCheckpoints(root, new, kind, bookmarks=marked)
                record['identity'] = target.identity
                if record['revision'] == old_binding:
                    record['revision'] = new_binding
                target.write(record, validate, overwrite=False)
                path.unlink()
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()


def _credential_revocation(chain, app):
    """Capture credential generation independently of any one reader lease."""
    for source in chain:
        client = getattr(source, 'client', None)
        if client is not None:
            generation = getattr(client, 'generation', None)
            owned = app is not None and getattr(app, 'cloud_client', None) is client
            host = None
            if owned:
                try:
                    host = ref(app)
                except TypeError:
                    host = lambda: app

            def revoked():
                current = host() if host is not None else None
                return ((current is not None and current.cloud_client is not client)
                        or getattr(client, 'generation', None) != generation)

            return revoked
        connection = getattr(source, 'connection', None)
        context = getattr(connection, 'context', None) or getattr(source, 'config_path', None)
        context = context or getattr(source, 'context', None)
        if context is not None:
            from features.rclone import desktop_session

            session = desktop_session()
            if session.credentials(context) is not None:
                return session.revocation_check(context)
            grant = getattr(source, '_credential_grant', None)
            if grant is not None:
                return grant.revoked
    return lambda: False


def open_progress(provider, path, root, *, kind, revision=None, app=None, check=None,
                  managed_roots=None, identity=None, legacy_path=None, locator_version=1,
                  follow_local_rename=False):
    """Choose ordinary local, authorized ZIP, or session memory exactly once."""
    if not isinstance(kind, str) or not kind or len(kind) > 64:
        raise ValueError('Invalid reader locator kind.')
    if type(locator_version) is not int or not 1 <= locator_version <= 2**31 - 1:
        raise ValueError('Invalid reader locator version.')
    root = Path(root).resolve()
    canonical, protected, logical = progress_source(
        provider, path, app=app, private_root=getattr(app, 'private_root', root),
        managed_roots=managed_roots,
    )
    if identity is not None and identity != canonical:
        raise ValueError('Reader progress identity does not match its source.')
    if follow_local_rename and canonical[:2] == ('local', 'absolute'):
        canonical = external_file_identity(provider, path, revision) or canonical
    chain = tuple(sources(provider))
    revoked = _credential_revocation(chain, app) if protected is not None else lambda: False
    checks = tuple(
        validate for source in chain
        if (validate := (getattr(source, '_check_active', None) or getattr(source, 'check', None)))
    )

    def validate():
        if revoked():
            raise _Fenced('Reader credentials changed. Reopen the document.')
        try:
            for guard in checks:
                guard()
            if check is not None:
                check()
        except _ERRORS as error:
            raise _Fenced('Reader access ended. Reopen the document.') from error

    mode = ProgressMode.SESSION_MEMORY
    stores = (None, None)
    try:
        generation = position_generation(root)
    except (OSError, ValueError):
        # A damaged generation fence reports a state error without blocking the
        # reader itself. Validation rechecks it before every position write.
        generation = ''
    if canonical[0] == 'local':
        mode = ProgressMode.LOCAL
        stores = tuple(LocalCheckpoints(root, canonical, kind, bookmarks=marked) for marked in (False, True))
    elif protected is not None:
        encrypted = CredentialState(
            protected, logical, root, kind=kind, revision=revision, app=app, check=validate,
            generation=generation,
        )
        try:
            encrypted.cipher.identity
        except PermissionError:
            # Saved mobile connection metadata is not ZIP encryption authority.
            pass
        else:
            mode = ProgressMode.ENCRYPTED
            stores = tuple(EncryptedCheckpoints(store, legacy_path, canonical[-2])
                           for store in (encrypted, encrypted.bookmarks))
    return DocumentProgress(root, canonical, kind, locator_version, revision, mode,
                            stores, validate, revoked, generation)


class DocumentProgress:
    """One open reader's handle to shared positions and independent bookmarks."""

    def __init__(self, root, identity, kind, locator_version, revision, mode, stores, validate, revoked, generation):
        self.root, self.identity, self.kind = root, identity, kind
        self.locator_version = locator_version
        self.revision, self._legacy_revision = revision_binding(revision)
        self.mode, self._stores = mode, stores
        self._validate_access, self._revoked = validate, revoked
        self._owner = object()
        self._closed = False
        self.generation = generation
        self.load_status = self.bookmark_status = self.write_status = ProgressStatus.ABSENT
        self.write_error = None
        self._keys = tuple(
            (root, identity, kind, mode, generation, section)
            for generation, section in ((self.generation, 'positions'), ('', 'bookmarks'))
        )
        with _observation_lock:
            self._channels = tuple(_channels.setdefault(key, _Channel()) for key in self._keys)

    @property
    def locked_state(self):
        return ProgressStatus.LOCKED in (self.load_status, self.bookmark_status)

    @property
    def can_import_legacy(self):
        if self.load_status is not ProgressStatus.ABSENT or self._closed or self.generation:
            return False
        try:
            return not position_generation(self.root)
        except (OSError, ValueError):
            return False

    def _validate(self, section):
        if self._closed:
            raise _Fenced('This reader has retired.')
        if self._channels[section].fenced or (section == 0 and self.generation != position_generation(self.root)):
            raise _Fenced('Reader positions were cleared. Reopen the document.')
        self._validate_access()

    def _record(self, section, identity, record):
        if self.mode is ProgressMode.ENCRYPTED and record.get('version') == 1:
            if type(record['version']) is not int or not isinstance(record.get('state'), dict):
                raise ValueError('Invalid legacy reader state.')
            encode(record['state'])
            return dict(record, revision=self.revision if record.get('revision') == self._legacy_revision else '',
                        locator_version=1, sequence=0)
        return checkpoint(record, identity, self.kind, self.generation if section == 0 else '')

    def _read_durable(self, section):
        store = self._stores[section]
        if self.mode is ProgressMode.ENCRYPTED:
            record = store.read(store.identity())
            identity = record['identity']
        else:
            identity, record = store.identity, store.read()
        record = self._record(section, identity, record)
        if record['sequence']:
            _next_sequence(record['sequence'])
        return record

    def _load(self, section):
        try:
            self._validate(section)
            if self.mode is ProgressMode.SESSION_MEMORY:
                pending = self._latest_pending(section)
                state = json.loads(pending.payload) if pending is not None and pending.matches(self) else {}
                return ProgressStatus.SESSION_ONLY, state
            # Authenticate and validate the durable original even when a newer
            # unsaved observation exists. A locked record stays distinguishable.
            try:
                record = self._read_durable(section)
            except FileNotFoundError:
                record = None
            self._validate(section)
            pending = self._latest_pending(section)
            if (pending is not None and pending.matches(self)
                    and (record is None or pending.observation.sequence > record['sequence'])):
                return ProgressStatus.RESTORED, json.loads(pending.payload)
            if record is None:
                return ProgressStatus.ABSENT, {}
            if record['revision'] != self.revision or record['locator_version'] != self.locator_version:
                raise IncompatibleCheckpoint
            return ProgressStatus.RESTORED, record['state']
        except FileNotFoundError:
            return ProgressStatus.ABSENT, {}
        except IncompatibleCheckpoint:
            return ProgressStatus.INCOMPATIBLE, {}
        except PreviousPasswordRequired:
            return ProgressStatus.LOCKED, {}
        except _Fenced:
            return ProgressStatus.FENCED, {}
        except _ERRORS:
            return ProgressStatus.ERROR, {}

    def _latest_pending(self, section):
        with _observation_lock:
            key, channel = self._keys[section], self._channels[section]
            pending = channel.pending or _memory.get(key)
            if pending is not None and pending.revoked():
                if channel.pending is pending:
                    channel.pending = None
                if _memory.get(key) is pending:
                    del _memory[key]
                return None
            return pending

    def load(self):
        with _io_lock:
            self.load_status, position = self._load(0)
            self.bookmark_status, bookmarks = self._load(1)
        return {**{key: val for key, val in position.items() if key not in _BOOKMARKS},
                **{key: bookmarks[key] for key in _BOOKMARKS if key in bookmarks}}

    def _observe(self, position, bookmarks):
        # Freeze a bounded copy before accepting observation order. Ignore
        # generation changes under the observation lock without touching disk.
        payloads = tuple(encode(state) if state is not None else None for state in (position, bookmarks))
        sections = tuple(section for section, payload in enumerate(payloads) if payload is not None)
        with _observation_lock:
            if self._closed or self._revoked() or any(self._channels[section].fenced for section in sections):
                return None
            token = _Observation(self._owner, _next_sequence(), sections)
            updates = []
            for section, (channel, payload) in enumerate(zip(self._channels, payloads)):
                if payload is not None:
                    previous = channel.pending
                    if section == 1 and previous is not None and previous.matches(self) and not previous.revoked():
                        payload = encode({**json.loads(previous.payload), **bookmarks})
                    updates.append((channel, _Pending(token, payload, self.revision, self.locator_version, self._revoked)))
            for channel, pending in updates:
                channel.pending = pending
            return token

    def observe(self, state):
        if not isinstance(state, dict):
            raise TypeError('Reader progress requires a dictionary.')
        bookmarks = {key: state[key] for key in _BOOKMARKS if key in state}
        position = {key: val for key, val in state.items() if key not in _BOOKMARKS}
        return self._observe(position if position or not bookmarks else None, bookmarks or None)

    def observe_bookmarks(self, state):
        if not state or set(state) - set(_BOOKMARKS):
            raise ValueError('Reader bookmark changes require a bookmark field.')
        return self._observe(None, state)

    def _verify_pending(self, section, pending):
        self._validate(section)
        with _observation_lock:
            if self._channels[section].pending is not pending:
                raise _Stale('Newer reader progress is already available.')

    def _write(self, section, pending):
        self._verify_pending(section, pending)
        if self.mode is ProgressMode.SESSION_MEMORY:
            with _observation_lock:
                key = self._keys[section]
                if self._channels[section].pending is not pending:
                    raise _Stale('Newer reader progress is already available.')
                previous = _memory.get(key)
                if section == 1 and previous is not None and previous.matches(self) and not previous.revoked():
                    pending = replace(pending, payload=encode(
                        {**json.loads(previous.payload), **json.loads(pending.payload)}
                    ))
                _memory[key] = pending
                _memory.move_to_end(key)
                if len(_memory) > _MAX_MEMORY_SECTIONS:
                    _memory.popitem(last=False)
            return ProgressStatus.SESSION_ONLY
        with checkpoint_write_lock(self.root):
            self._verify_pending(section, pending)
            return self._write_durable(section, pending)

    def _write_durable(self, section, pending):
        store = self._stores[section]
        if self.mode is ProgressMode.ENCRYPTED:
            identity = store.identity(create=True)
            read = lambda: store.read(identity)
        else:
            identity, read = store.identity, store.read
        try:
            record = read()
            original = self._record(section, record['identity'] if self.mode is ProgressMode.ENCRYPTED else identity,
                                    record)
        except FileNotFoundError:
            original = None
        if original is not None and original['sequence'] >= pending.observation.sequence:
            _next_sequence(original['sequence'])
            raise _Stale('Newer reader progress is already saved.')
        if original is not None and original['locator_version'] > self.locator_version:
            raise ValueError('Reader state uses a newer locator version.')
        state = json.loads(pending.payload)
        if section == 1 and original is not None and original['revision'] == self.revision:
            state = {**original['state'], **state}
        record = dict(
            version=2, identity=identity, kind=self.kind, locator_version=self.locator_version,
            revision=self.revision, sequence=pending.observation.sequence,
            generation=self.generation if section == 0 else '', state=state,
        )
        store.write(record, lambda: self._verify_pending(section, pending))
        return ProgressStatus.SAVED

    def flush(self, observation=None):
        if observation is not None and observation.owner is not self._owner:
            raise ValueError('Reader progress observation belongs to another handle.')
        statuses, error = [], None
        with _io_lock:
            if self._closed:
                self.write_status, self.write_error = ProgressStatus.FENCED, None
                return self.write_status
            for section, channel in enumerate(self._channels):
                with _observation_lock:
                    pending = channel.pending
                if channel.fenced and (observation is None or section in observation.sections):
                    statuses.append(ProgressStatus.FENCED)
                    continue
                if (pending is None or pending.observation.owner is not self._owner
                        or (observation is not None and pending.observation.sequence > observation.sequence)):
                    continue
                try:
                    status = self._write(section, pending)
                except _Fenced:
                    status = ProgressStatus.FENCED
                except _Stale:
                    status = ProgressStatus.STALE
                except PreviousPasswordRequired as failure:
                    status, error = ProgressStatus.LOCKED, failure
                except _ERRORS as failure:
                    status, error = ProgressStatus.WRITE_FAILED, failure
                statuses.append(status)
                if status not in (ProgressStatus.WRITE_FAILED, ProgressStatus.LOCKED):
                    with _observation_lock:
                        if channel.pending is pending:
                            channel.pending = None
        self.write_status = next(
            (status for status in (ProgressStatus.WRITE_FAILED, ProgressStatus.LOCKED, ProgressStatus.FENCED,
                                   ProgressStatus.SAVED, ProgressStatus.SESSION_ONLY, ProgressStatus.STALE)
             if status in statuses),
            ProgressStatus.STALE if observation is not None else ProgressStatus.ABSENT,
        )
        self.write_error = error
        return self.write_status

    def save(self, state):
        token = self.observe(state)
        if token is not None:
            return self.flush(token)
        self.write_status, self.write_error = ProgressStatus.FENCED, None
        return self.write_status

    def retire(self):
        with _observation_lock:
            self._closed = True
            for channel in self._channels:
                pending = channel.pending
                if pending is not None and pending.observation.owner is self._owner:
                    channel.pending = None
