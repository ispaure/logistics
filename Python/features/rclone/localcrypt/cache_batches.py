"""One disposable SQLite store of credential-sealed filename batches per copy."""

import json
import sqlite3
from collections import OrderedDict

from services.documents.credential_state import LIMIT


_MAX_BATCH_ROWS = 32
_MAX_STORE_BYTES = 16 * 1024 * 1024
_MAX_BATCHES = 256


class EncryptedNameBatches:
    def __init__(self, file, cipher, validate):
        self.file, self.cipher, self.validate = file, cipher, validate
        self.database = None
        self.disabled = False
        self.opened = OrderedDict()
        self.pending = {}
        self.pending_size = 128
        self.pending_root = None

    def _connect(self, *, create=False):
        if self.disabled or self.database is not None:
            return self.database
        if self.file.is_symlink() or self.file.parent.is_symlink():
            self.disabled = True
            return None
        if not create and not self.file.is_file():
            return None
        try:
            self.file.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.database = sqlite3.connect(self.file, timeout=.05)
            self.database.executescript('''
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, sealed BLOB NOT NULL, root_scope TEXT
                );
                CREATE TABLE IF NOT EXISTS folders (
                    scope TEXT PRIMARY KEY,
                    batch INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS folders_batch ON folders(batch);
            ''')
        except (OSError, sqlite3.Error):
            self.close()
            self.disabled = True
        return self.database

    def read(self, scope):
        database = self._connect()
        if database is None:
            return None
        try:
            found = database.execute('SELECT batch FROM folders WHERE scope = ?', (scope,)).fetchone()
            if found is None:
                return None
            batch = found[0]
            if batch not in self.opened:
                sealed = database.execute('SELECT sealed FROM batches WHERE id = ?', (batch,)).fetchone()
                if sealed is None or len(sealed[0]) > LIMIT + 2048:
                    return None
                payload = json.loads(self.cipher.transform(sealed[0], decode=True))
                if not isinstance(payload, dict) or payload.get('copy') != self.file.stem:
                    return None
                rows = payload.get('records')
                if not isinstance(rows, dict):
                    return None
                self.opened[batch] = rows
                if len(self.opened) > 32:
                    self.opened.popitem(last=False)
            self.opened.move_to_end(batch)
            self.validate()
            return self.opened[batch].get(scope)
        except (OSError, sqlite3.Error, ValueError, TypeError, RuntimeError):
            return None

    def add(self, scope, record, *, root=False):
        if self.disabled:
            return
        packed = json.dumps(record, separators=(',', ':')).encode()
        size = len(packed) + len(scope) + 8
        if size + 128 > LIMIT:
            return
        if len(self.pending) >= _MAX_BATCH_ROWS or self.pending_size + size > LIMIT:
            self.flush()
        self.pending[scope] = packed
        self.pending_size += size
        if root:
            self.pending_root = scope

    def flush(self):
        if not self.pending:
            return
        pending, root = self.pending, self.pending_root
        self.pending, self.pending_size, self.pending_root = {}, 128, None
        database = self._connect(create=True)
        if database is None:
            return
        raw = (b'{"copy":"' + self.file.stem.encode('ascii') + b'","records":{' +
               b','.join(b'"' + scope.encode('ascii') + b'":' + row for scope, row in pending.items()) + b'}}')
        try:
            self.validate()
            sealed = self.cipher.transform(raw)
            self.validate()
            with database:
                batch = database.execute('INSERT INTO batches(sealed, root_scope) VALUES (?, ?)',
                                         (sealed, root)).lastrowid
                database.executemany('INSERT OR REPLACE INTO folders VALUES (?, ?)',
                                     ((scope, batch) for scope in pending))
                database.execute('DELETE FROM batches WHERE NOT EXISTS '
                                 '(SELECT 1 FROM folders WHERE folders.batch = batches.id)')
                self._trim(database)
                self.validate()
        except (OSError, sqlite3.Error, ValueError, RuntimeError):
            pass  # A missing batch can be rebuilt from a later search.

    @staticmethod
    def _trim(database):
        size = 0
        expired = []
        for count, (batch, length) in enumerate(database.execute('''
                SELECT id, length(sealed) FROM batches
                ORDER BY EXISTS (
                    SELECT 1 FROM folders WHERE scope = batches.root_scope AND batch = batches.id
                ) DESC, id DESC
        ''')):
            size += length
            if count >= _MAX_BATCHES or size > _MAX_STORE_BYTES:
                expired.append((batch,))
        database.executemany('DELETE FROM batches WHERE id = ?', expired)

    def close(self):
        if self.database is not None:
            self.database.close()
            self.database = None
        self.opened.clear()
        self.pending.clear()
