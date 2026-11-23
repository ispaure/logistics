"""Shared persistent filename snapshots for ordinary mobile storage."""

import json
import sqlite3
from contextlib import contextmanager

from commonUtils.runtime.operations import check_cancelled
from commonUtils.runtime.resources.local import LocalFiles
from services.documents.locations import (
    CollectionFiles, MobileLocalFiles, local_folder_snapshot, visible_transfer_rows,
)

FILENAME_DATABASE = 'device-filenames.sqlite3'


def supports_device_name_cache(provider):
    from .local_sources import PhoneFiles

    return (type(provider) in (LocalFiles, PhoneFiles, CollectionFiles, MobileLocalFiles)
            and not provider.private and not getattr(provider, 'session_only', False)
            and not getattr(provider, 'remote_storage', False))


def _stamp(folder):
    info = folder.stat(follow_symlinks=False)
    return ':'.join(str(value) for value in
                    (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns))


def _rows_for_folder(data, path):
    rows = json.loads(data)
    for row in rows:
        # Older snapshots hold a provider-relative path. Only its basename
        # belongs to the physical folder shared by different provider roots.
        basename = row.pop('basename', None) or row['path'].rpartition('/')[2]
        row['path'] = '/'.join(filter(None, (path, basename)))
    return rows


def _pack_rows(rows):
    return json.dumps([dict(name=row['name'], basename=row['path'].rpartition('/')[2],
                            directory=row['directory'], size=row['size']) for row in rows])


def _cache_path(provider, path):
    from .local_sources import PhoneFiles

    folder = provider.root / provider.relative(path)
    # The Phone root has reserved names, unlike a generic provider pointing
    # at that physical directory. Descendants can share their basename rows.
    return f'phone:{folder}' if type(provider) is PhoneFiles and not path else str(folder)


def retire_legacy_mobile_index(cache_directory):
    """Remove only the retired mobile index and its own SQLite sidecars."""
    for name in ('directory-index.sqlite3', 'directory-index.jobs.sqlite3', 'directory-index.pre-v3.sqlite3'):
        for suffix in ('', '-wal', '-shm', '-journal'):
            try:
                (cache_directory / (name + suffix)).unlink(missing_ok=True)
            except OSError:
                pass
    for name in ('directory-index.lock', 'directory-index.jobs.lock'):
        try:
            (cache_directory / name).unlink(missing_ok=True)
        except OSError:
            pass


@contextmanager
def device_name_listing(provider, cache_directory, *, status=lambda phase: None):
    """Reuse unchanged directory listings. The provider owns all enumeration."""
    database = None
    try:
        cache_directory.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(cache_directory / FILENAME_DATABASE,
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

    def listing(path, *, cancelled, cached_only=False, cache_status=status):
        path = provider.relative(path)
        key = _cache_path(provider, path)
        if cached_only:
            check_cancelled(cancelled)
            if database is None:
                return ()
            try:
                saved = database.execute('SELECT rows FROM folders WHERE path = ?', (key,)).fetchone()
                return _rows_for_folder(saved[0], path) if saved is not None else ()
            except (sqlite3.Error, json.JSONDecodeError):
                return ()
        folder = provider._locate(path)
        stamp = _stamp(folder)
        if database is not None:
            try:
                saved = database.execute('SELECT rows FROM folders WHERE path = ? AND stamp = ?',
                                         (key, stamp)).fetchone()
                if saved is not None and _stamp(folder) == stamp:
                    provider._guard(folder)
                    check_cancelled(cancelled)
                    cache_status('device_cached')
                    return _rows_for_folder(saved[0], path)
            except (sqlite3.Error, json.JSONDecodeError):
                pass

        cache_status('device_refreshing' if database is not None else '')
        list_names = getattr(provider, 'list_names', None)
        children = (list_names(path, cancelled=cancelled) if list_names is not None
                    else local_folder_snapshot(provider, path, cancelled=cancelled, names_only=True))
        rows = list(visible_transfer_rows(provider, children))
        if database is not None and _stamp(folder) == stamp:
            pending.append((key, stamp, _pack_rows(rows)))
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
