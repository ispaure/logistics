"""Bounded LocalCrypt directory metadata, sealed with the credential ZIP key."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from collections import OrderedDict
from hashlib import sha256
import json
import os
import stat
from threading import RLock

from commonUtils.persistence import atomic_write_bytes
from commonUtils.runtime.operations import check_cancelled
from services.documents.credential_state import LIMIT, credential_authority


def _directory_revision(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_mtime_ns, info.st_ctime_ns


class DirectoryIndex:
    def __init__(self, provider, folder, cipher):
        self.provider, self.folder, self.cipher = provider, folder, cipher
        self.rows, self.lock = OrderedDict(), RLock()
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

    def _record_path(self, inode):
        if self.folder is None:
            return None, None
        self.cipher.identity
        authority = credential_authority(self.provider)
        # Fixed, shared cache slots bound disk use. The filename contains no
        # logical path, and the sealed record verifies the full binding.
        scope = sha256(json.dumps([authority, self.provider.storage_namespace, inode]).encode()).hexdigest()
        file = self.folder / f'{int(scope[:2], 16):02x}.zip'
        if file.is_symlink() or self.folder.is_symlink() or self.folder.parent.is_symlink():
            raise ValueError('Linked encrypted directory index is not supported.')
        return file, scope

    def listing(self, path, *, cancelled, from_inventory=None):
        provider = self.provider
        with provider.operation(cancelled):
            self._check(cancelled)
            folder = provider._locate(path)
            inventory = [] if from_inventory is not None else None
            try:
                signature = (self._fingerprint(folder, cancelled, inventory)
                             if inventory is not None else self._fingerprint(folder, cancelled))
            except FileNotFoundError:
                signature = None
            if signature is None:
                return provider.list(path, cancelled=cancelled)
            inode, revision, parent_revision = signature
            with self.lock:
                cached = self.rows.pop(path, None)
                if cached is not None and cached[0] == revision:
                    self._check(cancelled)
                    self.rows[path] = cached
                    return json.loads(cached[1])
            file = scope = None
            try:
                file, scope = self._record_path(inode)
                if file is not None:
                    with file.open('rb') as stream:
                        encrypted = stream.read(LIMIT + 2049)
                    if len(encrypted) <= LIMIT + 2048:
                        record = json.loads(self.cipher.transform(encrypted, decode=True))
                        if isinstance(record, dict) and record.get('binding') == [1, scope, path, revision]:
                            rows = record['rows']
                            if isinstance(rows, list) and all(
                                    isinstance(row, dict) and type(row.get('directory')) is bool
                                    and provider.relative(row['path']) == row['path']
                                    and row['path'] == '/'.join(filter(None, (path, row['name'])))
                                    and row['path'].rpartition('/')[0] == path for row in rows):
                                self._remember(path, revision, rows, cancelled)
                                return rows
            except (OSError, ValueError, TypeError, KeyError, RuntimeError):
                pass  # A disposable cache can always be rebuilt from the provider.
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
                self._remember(path, revision, rows, cancelled)
                if file is not None:
                    raw = json.dumps(dict(binding=[1, scope, path, revision], rows=rows)).encode()
                    if len(raw) <= LIMIT:
                        try:
                            sealed = self.cipher.transform(raw)
                            self._check(cancelled)
                            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
                            atomic_write_bytes(file, sealed, validate=lambda: self._check(cancelled))
                        except (OSError, ValueError, RuntimeError):
                            pass
            self._check(cancelled)
            return rows

    def _remember(self, path, revision, rows, cancelled):
        data = json.dumps(rows).encode()
        with self.lock:
            self._check(cancelled)
            if len(data) <= LIMIT:
                self.rows[path] = revision, data
                while len(self.rows) > 64:
                    self.rows.popitem(last=False)
