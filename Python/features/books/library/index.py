"""Disposable ordinary-import metadata index with incremental scans and paging.

Private providers never enter this database. Hosts supply revision signatures and
an ordinary-import metadata loader; formats and matching remain feature-owned.
"""

import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
from threading import RLock
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from features.comics.collection import suggestions

PAGE_SIZE = 50


class CollectionIndex:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ValueError("Metadata index cannot use linked storage.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        try:
            self.prepare()
        except sqlite3.DatabaseError:
            # This is derived ordinary-import metadata, never an archive or a
            # recovery journal. A corrupt cache can be recreated from imports.
            self.path.unlink(missing_ok=True)
            self.prepare()

    def prepare(self):
        with self.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS imports (id TEXT PRIMARY KEY, name TEXT NOT NULL, digest TEXT NOT NULL, signature TEXT NOT NULL, fields TEXT NOT NULL, search TEXT NOT NULL, status TEXT NOT NULL)"
            )

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def scan(
        self,
        records,
        *,
        signature,
        load,
        cancelled=lambda: False,
        progress=lambda done, total, failures: None,
    ):
        """Commit bounded chunks; interruption leaves a reusable partial index."""
        with self.lock:
            # A superseded scan may have waited behind a newer worker. It must
            # not even open/prune the cache after its owner has retired it.
            if cancelled():
                return
            self._scan(
                records,
                signature=signature,
                load=load,
                cancelled=cancelled,
                progress=progress,
            )

    def _scan(self, records, *, signature, load, cancelled, progress):
        with self.connect() as db:
            wanted = {record["id"] for record in records}
            for (key,) in db.execute("SELECT id FROM imports").fetchall():
                if key not in wanted:
                    db.execute("DELETE FROM imports WHERE id=?", (key,))
            pending = []
            for record in records:
                if cancelled():
                    return
                try:
                    stamp = json.dumps(signature(record))
                except (OSError, ValueError):
                    stamp = ""
                old = db.execute(
                    "SELECT digest, signature, status, fields FROM imports WHERE id=?",
                    (record["id"],),
                ).fetchone()
                fresh = (
                    old is not None
                    and old[:2] == (record["digest"], stamp)
                    and old[2] in ("ready", "protected")
                )
                if fresh:
                    search = "\n".join(
                        [record["name"], *json.loads(old[3]).values()]
                    ).casefold()
                    db.execute(
                        "UPDATE imports SET name=?, search=? WHERE id=?",
                        (record["name"], search, record["id"]),
                    )
                else:
                    db.execute(
                        "INSERT OR REPLACE INTO imports VALUES (?,?,?,?,?,?,?)",
                        (
                            record["id"],
                            record["name"],
                            record["digest"],
                            stamp,
                            "{}",
                            record["name"].casefold(),
                            "pending",
                        ),
                    )
                    pending.append((record, stamp))
            db.commit()
            failures = 0
            done = len(records) - len(pending)
            progress(done, len(records), failures)
            for record, stamp in pending:
                if cancelled():
                    return
                status, fields = "ready", {}
                try:
                    loaded = load(record)
                    if loaded is None:
                        status = "protected"
                    else:
                        fields = {
                            str(key): str(value)[:4096] for key, value in loaded.items()
                        }
                    if json.dumps(signature(record)) != stamp:
                        raise ValueError("Archive changed while indexing.")
                except (
                    OSError,
                    ValueError,
                    RuntimeError,
                    KeyError,
                    EOFError,
                    BadZipFile,
                    ParseError,
                ):
                    status, fields = "error", {}
                    failures += 1
                if cancelled():
                    return
                db.execute(
                    "UPDATE imports SET fields=?, search=?, status=? WHERE id=? AND digest=? AND signature=?",
                    (
                        json.dumps(fields),
                        "\n".join([record["name"], *fields.values()]).casefold(),
                        status,
                        record["id"],
                        record["digest"],
                        stamp,
                    ),
                )
                done += 1
                if done % 25 == 0:
                    db.commit()
                    progress(done, len(records), failures)
            db.commit()
            progress(done, len(records), failures)

    def page(self, query="", *, offset=0, limit=PAGE_SIZE):
        tokens = query.casefold().split()
        where = " AND ".join("instr(search, ?) > 0" for _ in tokens) or "1"
        with self.connect() as db:
            total = db.execute(
                "SELECT count(*) FROM imports WHERE " + where, tokens
            ).fetchone()[0]
            return [
                row[0]
                for row in db.execute(
                    "SELECT id FROM imports WHERE "
                    + where
                    + " ORDER BY name COLLATE NOCASE,id LIMIT ? OFFSET ?",
                    (*tokens, limit, offset),
                )
            ], total

    def suggestions(self):
        with self.connect() as db:
            return suggestions(
                json.loads(row[0])
                for row in db.execute("SELECT fields FROM imports WHERE status='ready'")
            )
