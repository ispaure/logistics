"""Bounded LocalCrypt directory metadata, sealed with the credential ZIP key."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections import OrderedDict
from contextlib import contextmanager
from hashlib import sha256
import json
import os
import re
import stat
from threading import RLock, local

from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.operations import check_cancelled
from services.documents.credential_state import LIMIT, credential_authority


_CACHE_FILE = re.compile(r'(?:root-)?[0-9a-f]{64}\.zip\Z')
_BUCKET_ENTRIES = 32
_BUCKET_BYTES = 256 * 1024


def _directory_revision(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns


class DirectoryNameMemory:
    """Bounded filename snapshots shared by views in one credential generation."""
    def __init__(self):
        self.generation = 0
        self.rows = OrderedDict()
        self.size = 0
        self.lock = RLock()

    def reset(self, generation):
        with self.lock:
            self.generation = generation
            self.rows.clear()
            self.size = 0

    def get(self, generation, key):
        with self.lock:
            if generation != self.generation or key not in self.rows:
                return None
            self.rows.move_to_end(key)
            return self.rows[key]

    def put(self, generation, key, value):
        limit = 8 * 1024 * 1024
        size = len(value[1])
        with self.lock:
            if generation != self.generation or size > limit:
                return
            previous = self.rows.pop(key, None)
            if previous is not None:
                self.size -= len(previous[1])
            self.rows[key] = value
            self.size += size
            while self.size > limit or len(self.rows) > 4096:
                # A cached tree starts at its root. Keep that entry when
                # scanning a share too large to fit its entire tree in RAM.
                oldest = next((row for row in self.rows if row[-1]), next(iter(self.rows)))
                self.size -= len(self.rows.pop(oldest)[1])


class DirectoryIndex:
    def __init__(self, provider, folder, cipher, *, memory=None, scope=None):
        self.provider, self.folder, self.cipher = provider, folder, cipher
        self.memory, self.scope = memory, scope
        self.rows, self.lock = OrderedDict(), RLock()
        self._batch_work = local()
        self.closed = False

    def close(self):
        with self.lock:
            self.closed = True
            self.rows.clear()

    def credentials_changed(self):
        self.close()

    def _check(self, cancelled):
        check_cancelled(cancelled)
        self.provider._note_check()
        if self.closed:
            raise ValueError('Encrypted directory index closed.')

    @contextmanager
    def cache_operation(self, cancelled):
        """Use one batch session for a mobile traversal and its nested listings."""
        if self.memory is None or self.folder is None or hasattr(self._batch_work, 'current'):
            yield
            return
        work = self._batch_work.current = {'cancelled': cancelled}
        try:
            yield
            if (store := work.get('store')) is not None:
                store.flush()
        finally:
            if (store := work.get('store')) is not None:
                store.close()
            del self._batch_work.current

    def _batch_store(self):
        work = getattr(self._batch_work, 'current', None)
        if work is None:
            return None
        if 'store' not in work:
            work['store'] = None
            try:
                self._check(work['cancelled'])
                root = self.provider.root.stat(follow_symlinks=False)
                identity = [credential_authority(self.provider), self.provider.storage_namespace,
                            self.cipher.identity, root.st_dev, root.st_ino]
                key = sha256(json.dumps(identity).encode()).hexdigest()
                copies = self.folder / 'copies'
                if any(path.is_symlink() for path in (copies, self.folder, self.folder.parent)):
                    return None
                from .cache_batches import EncryptedNameBatches
                work['store'] = EncryptedNameBatches(copies / f'{key}.sqlite3', self.cipher,
                                                    lambda: self._check(work['cancelled']))
            except (OSError, ValueError, RuntimeError):
                pass
        return work['store']

    def _fingerprint(self, folder, cancelled, inventory=None):
        self.provider._note_guard(folder)
        before = folder.stat(follow_symlinks=False)
        entries = []
        windows = os.name == 'nt'
        with os.scandir(folder) as children:
            for child in children:
                check_cancelled(cancelled)
                path = folder / child.name if windows else None
                if child.is_symlink() or (windows and hasattr(path, 'is_junction') and path.is_junction()):
                    raise ValueError('Linked encrypted storage is not supported.')
                # Windows DirEntry.stat omits the hard-link count and file ID.
                info = (path.stat(follow_symlinks=False) if windows else child.stat(follow_symlinks=False))
                directory = stat.S_ISDIR(info.st_mode)
                if not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1):
                    raise ValueError('Choose an independent regular file or folder.')
                if inventory is not None:
                    inventory.append((child.name, info, directory))
                entries.append((child.name, info.st_mode, info.st_ino, info.st_size,
                                info.st_mtime_ns, info.st_ctime_ns))
                if len(entries) > 10000:
                    raise ValueError('Folder listing exceeds 10,000 entries.')
        self._check(cancelled)
        self.provider._note_guard(folder)
        after = folder.stat(follow_symlinks=False)
        parent_revision = _directory_revision(after)
        if _directory_revision(before) != parent_revision:
            return None
        inode = before.st_dev, before.st_ino
        revision = sha256(json.dumps([inode, sorted(entries)], ensure_ascii=True).encode()).hexdigest()
        return inode, revision, parent_revision

    def _record_path(self, inode, *, root=False):
        if self.folder is None:
            return None, None
        self.cipher.identity
        authority = credential_authority(self.provider)
        # The full opaque key prevents unrelated folders from replacing each
        # other. Each of the 256 buckets has its own retention budget.
        scope = sha256(json.dumps([authority, self.provider.storage_namespace, inode]).encode()).hexdigest()
        filename = f'root-{scope}.zip' if root else f'{scope}.zip'
        records = self.folder / 'records'
        bucket = records / scope[:2]
        file = bucket / filename
        if any(item.is_symlink() for item in (file, bucket, records, self.folder, self.folder.parent)):
            raise ValueError('Linked encrypted directory index is not supported.')
        return file, scope

    def _load_record(self, file, scope, path, revision=None):
        if file is None:
            return None
        with file.open('rb') as stream:
            encrypted = stream.read(LIMIT + 2049)
        if len(encrypted) > LIMIT + 2048:
            return None
        record = json.loads(self.cipher.transform(encrypted, decode=True))
        return self._validated_record(record, scope, path, revision)

    def _validated_record(self, record, scope, path, revision):
        binding = record.get('binding') if isinstance(record, dict) else None
        if (not isinstance(binding, list) or len(binding) != 4 or binding[:3] != [1, scope, path]
                or (revision is not None and binding[3] != revision)):
            return None
        rows = record['rows']
        if isinstance(rows, list) and all(
                isinstance(row, dict) and type(row.get('directory')) is bool
                and self.provider.relative(row['path']) == row['path']
                and row['path'] == '/'.join(filter(None, (path, row['name'])))
                and row['path'].rpartition('/')[0] == path for row in rows):
            stamp = record.get('folder_revision')
            if not isinstance(stamp, list) or len(stamp) != 5 or any(type(value) is not int for value in stamp):
                stamp = ()
            return binding[3], rows, tuple(stamp)
        return None

    def _legacy_candidates(self, file, scope, path):
        slot = f'root-{scope[0]}.zip' if not path else f'{int(scope[:3], 16) % 1024:03x}.zip'
        return file, self.folder / slot, self.folder / f'{scope[:2]}.zip'

    def _retire_legacy_records(self, file, scope, path, cancelled):
        for candidate in self._legacy_candidates(file, scope, path):
            try:
                before = candidate.stat(follow_symlinks=False)
                if not stat.S_ISREG(before.st_mode) or self._load_record(candidate, scope, path) is None:
                    continue
                self._check(cancelled)
                after = candidate.stat(follow_symlinks=False)
                if (_directory_revision(before), before.st_size) == (_directory_revision(after), after.st_size):
                    candidate.unlink()
            except (OSError, TypeError, ValueError, KeyError, RuntimeError):
                pass

    def _read_record(self, file, scope, path, revision=None):
        if file is None:
            return None
        if (store := self._batch_store()) is not None:
            try:
                record = self._validated_record(store.read(scope), scope, path, revision)
                if record is not None:
                    self._retire_legacy_records(file, scope, path, self._batch_work.current['cancelled'])
                    return (*record, True)
            except (ValueError, KeyError, TypeError):
                pass
        # Read old slots after checking the exact key, and migrate a verified
        # old record when the provider next validates its folder.
        for candidate in self._legacy_candidates(file, scope, path):
            if candidate.is_symlink():
                continue
            try:
                record = self._load_record(candidate, scope, path, revision)
                if record is not None:
                    return (*record, self.memory is None and candidate == file)
            except (OSError, TypeError, ValueError, KeyError, RuntimeError):
                continue
        return None

    def _trim_bucket(self, file):
        entries = []
        for candidate in file.parent.iterdir():
            if not _CACHE_FILE.fullmatch(candidate.name):
                continue
            try:
                info = candidate.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode):
                entries.append((candidate.name.startswith('root-'), info.st_mtime_ns, candidate, info.st_size))
        count, size = len(entries), sum(entry[3] for entry in entries)
        for _, _, candidate, length in sorted(entries):
            if count <= _BUCKET_ENTRIES and size <= _BUCKET_BYTES:
                break
            if candidate != file:
                candidate.unlink(missing_ok=True)
                count -= 1
                size -= length

    def _store_record(self, path, revision, rows, folder_revision, cancelled, *, file, scope):
        if file is None:
            return
        record = dict(binding=[1, scope, path, revision], rows=rows, folder_revision=folder_revision)
        if self.memory is not None:
            if (store := self._batch_store()) is not None:
                retire = None
                if any(candidate.is_file() for candidate in self._legacy_candidates(file, scope, path)):
                    retire = lambda: self._retire_legacy_records(file, scope, path, cancelled)
                store.add(scope, record, root=not path, retire=retire)
            return
        raw = json.dumps(record).encode()
        if len(raw) > LIMIT:
            return
        try:
            sealed = self.cipher.transform(raw)
            self._check(cancelled)
            file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            atomic_write_bytes(file, sealed, validate=lambda: self._check(cancelled))
            self._trim_bucket(file)
        except (OSError, ValueError, RuntimeError):
            pass  # A disposable cache can always be rebuilt from the provider.

    def cached_listing(self, path, *, cancelled, locate):
        """Read search hints without enumerating or fingerprinting the folder."""
        with self.provider.operation(cancelled):
            self._check(cancelled)
            with self.lock:
                saved = self._cached_rows(path)
            if saved is not None:
                self._check(cancelled)
                return json.loads(saved[1])
            if self.folder is None:
                return ()
            try:
                info = locate(path).stat(follow_symlinks=False)
                file, scope = self._record_path((info.st_dev, info.st_ino), root=not path)
                record = self._read_record(file, scope, path)
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                record = None
            self._check(cancelled)
            if record is None:
                return ()
            revision, rows, stamp, exact = record
            if not exact:
                stamp = ()  # Validate the old slot before migrating its contents.
            self._remember(path, revision, rows, cancelled, stamp)
            return rows

    def listing(self, path, *, cancelled, from_inventory=None, locate=None, cache_status=lambda phase: None,
                names_only=False):
        provider = self.provider
        with provider.operation(cancelled):
            self._check(cancelled)
            folder = (locate or provider._locate)(path)
            cache_status('checking')
            if names_only:
                with self.lock:
                    cached = self._cached_rows(path)
                if cached is not None and cached[2]:
                    try:
                        stamp = _directory_revision(folder.stat(follow_symlinks=False))
                    except FileNotFoundError:
                        stamp = ()
                    if cached[2] == stamp:
                        self._check(cancelled)
                        cache_status('cached')
                        return json.loads(cached[1])
            inventory = [] if from_inventory is not None else None
            try:
                signature = (self._fingerprint(folder, cancelled, inventory)
                             if inventory is not None else self._fingerprint(folder, cancelled))
            except FileNotFoundError:
                signature = None
            if signature is None:
                cache_status('refreshing')
                return provider.list(path, cancelled=cancelled)
            inode, revision, parent_revision = signature
            with self.lock:
                cached = self._cached_rows(path)
            if cached is not None and cached[0] == revision:
                self._check(cancelled)
                rows = json.loads(cached[1])
                if not cached[2]:
                    self._remember(path, revision, rows, cancelled, parent_revision)
                    try:
                        file, scope = self._record_path(inode, root=not path)
                        self._store_record(path, revision, rows, parent_revision, cancelled, file=file, scope=scope)
                    except (OSError, ValueError, RuntimeError):
                        pass
                cache_status('cached')
                return rows
            file = scope = None
            try:
                file, scope = self._record_path(inode, root=not path)
                record = self._read_record(file, scope, path, revision)
                if record is not None:
                    _, rows, stamp, exact = record
                    self._remember(path, revision, rows, cancelled, parent_revision)
                    if not (stamp and exact):
                        self._store_record(path, revision, rows, parent_revision, cancelled, file=file, scope=scope)
                    cache_status('cached')
                    return rows
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                pass  # A disposable cache can always be rebuilt from the provider.
            cache_status('refreshing')
            if from_inventory is None:
                rows = provider.list(path, cancelled=cancelled)
                try:
                    unchanged = self._fingerprint(folder, cancelled) == signature
                except FileNotFoundError:
                    unchanged = False
            else:
                rows, unchanged = from_inventory(folder, path, inventory, cancelled)
                # The loader rechecks each decoded entry against the same
                # metadata used for the fingerprint. Check the parent too so
                # additions, moves and removals prevent a saved publication.
                try:
                    unchanged = unchanged and _directory_revision(
                        folder.stat(follow_symlinks=False)) == parent_revision
                except FileNotFoundError:
                    unchanged = False
            # Keep only search metadata. Live opens still validate the resource.
            rows = [{key: row[key] for key in ('name', 'path', 'directory', 'size', 'modified') if key in row}
                    for row in rows]
            self._check(cancelled)
            if unchanged:
                self._remember(path, revision, rows, cancelled, parent_revision)
                self._store_record(path, revision, rows, parent_revision, cancelled, file=file, scope=scope)
            self._check(cancelled)
            return rows

    def _cached_rows(self, path):
        if self.memory is not None:
            generation, *key = self.scope
            shared = self.memory.get(generation, (*key, path))
            if shared is not None:
                return shared
        if path in self.rows:
            self.rows.move_to_end(path)
            return self.rows[path]
        return None

    def _remember(self, path, revision, rows, cancelled, folder_revision):
        data = json.dumps(rows).encode()
        value = (revision, data, folder_revision)
        with self.lock:
            self._check(cancelled)
            if self.memory is not None:
                generation, *key = self.scope
                self.memory.put(generation, (*key, path), value)
            if len(data) <= LIMIT:
                self.rows.pop(path, None)
                self.rows[path] = value
                while len(self.rows) > 64:
                    self.rows.popitem(last=False)
