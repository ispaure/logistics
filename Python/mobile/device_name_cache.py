"""Persistent filename snapshots for the guarded On My Phone/Tablet provider."""

import json
import sqlite3
from contextlib import contextmanager

from commonUtils.runtime.operations import check_cancelled
from services.documents.locations import visible_transfer_rows


def _stamp(folder):
    info = folder.stat(follow_symlinks=False)
    return ':'.join(str(value) for value in
                    (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))


@contextmanager
def device_name_listing(provider, cache_directory, *, status=lambda phase: None):
    """Reuse unchanged directory listings. The provider owns all enumeration."""
    database = None
    try:
        cache_directory.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(cache_directory / 'device-filenames.sqlite3',
                                   timeout=.05, isolation_level=None)
        database.execute('''CREATE TABLE IF NOT EXISTS folders (
            path TEXT PRIMARY KEY, stamp TEXT NOT NULL, rows TEXT NOT NULL)''')
    except (OSError, sqlite3.Error):
        if database is not None:
            database.close()
        database = None

    pending = []

    def save():
        if not pending:
            return
        try:
            database.execute('BEGIN IMMEDIATE')
            database.executemany('INSERT OR REPLACE INTO folders VALUES (?, ?, ?)', pending)
            database.commit()
        except sqlite3.Error:
            database.rollback()
        finally:
            pending.clear()

    def listing(path, *, cancelled):
        folder = provider._locate(path)
        stamp = _stamp(folder)
        if database is not None:
            try:
                saved = database.execute('SELECT rows FROM folders WHERE path = ? AND stamp = ?',
                                         (str(folder), stamp)).fetchone()
                if saved is not None and _stamp(folder) == stamp:
                    provider._guard(folder)
                    check_cancelled(cancelled)
                    status('device_cached')
                    return json.loads(saved[0])
            except (sqlite3.Error, json.JSONDecodeError):
                pass

        status('device_refreshing' if database is not None else '')
        rows = list(visible_transfer_rows(provider, provider.list_names(path, cancelled=cancelled)))
        if database is not None and _stamp(folder) == stamp:
            pending.append((str(folder), stamp, json.dumps(rows)))
            if len(pending) >= 32:
                save()
        return rows

    try:
        yield listing
    finally:
        if database is not None:
            try:
                save()
            finally:
                database.close()
