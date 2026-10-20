"""App-private text documents and durable, conflict-aware recovery records."""
import base64
import asyncio
from dataclasses import dataclass
from functools import wraps
import json
import os
from pathlib import Path
from uuid import uuid4
from threading import RLock

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.text import decode_bytes, write_text_file, FileConflictError

MAX_BYTES = 1024 * 1024
MAX_RECORD = 4 * 1024 * 1024


from features.text_editor.names import document_name


def serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._write_lock:
            return method(self, *args, **kwargs)
    return call


@dataclass
class Document:
    id: str
    name: str
    snapshot: object
    text: str
    conflict: bool = False

    @property
    def modified(self):
        return self.text != self.snapshot.text


@dataclass(frozen=True)
class DocumentSummary:
    id: str
    name: str


class DocumentStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('The mobile host must supply an absolute app-private directory.')
        self.root = root.resolve()
        self._checkpoints = {}
        self._write_lock = RLock()
        self._queue_lock = RLock()
        self._pending = {}
        self._timers = {}
        self._writes = set()
        self._summaries = {}
        self._summary_lock = RLock()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key, suffix):
        if suffix not in ('.data', '.json'):
            raise ValueError('Invalid document storage suffix.')
        if (not isinstance(key, str) or len(key) != 32
                or any(c not in '0123456789abcdef' for c in key)):
            raise ValueError('Invalid document identity.')
        path = self.root / (key + suffix)
        if path.is_symlink():
            raise ValueError('Document storage cannot contain symbolic links.')
        return path

    def create(self, name='Untitled.txt', content=b''):
        name = document_name(name)
        if not isinstance(content, bytes) or len(content) > MAX_BYTES:
            raise ValueError('Mobile text documents are limited to 1 MiB.')
        key = uuid4().hex
        path = self.path(key, '.data')
        snapshot = decode_bytes(content, path=path)
        doc = Document(key, name, snapshot, snapshot.text)
        # Android app sandboxes can reject hard links. Reserve the private UUID
        # exclusively; publish its visible recovery record after durable data.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.checkpoint(doc)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return doc

    @staticmethod
    def _recovery_revision(path):
        info = path.stat()
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                info.st_ctime_ns, info.st_mode, info.st_nlink)

    def queue_checkpoint(self, doc, loop, *, failed=None):
        """Batch edits in RAM; native UI values are captured by the caller."""
        if getattr(doc, 'private', False):
            self.cancel_checkpoint(doc.id)
            return
        snapshot = Document(doc.id, doc.name, doc.snapshot, doc.text, doc.conflict)
        with self._queue_lock:
            previous = self._pending.get(doc.id)
            since = previous[2] if previous is not None else loop.time()
            self._pending[doc.id] = (doc, snapshot, since)
            timer = self._timers.pop(doc.id, None)
            if timer is not None:
                timer.cancel()
            delay = min(.25, max(0, 1 - (loop.time() - since)))
            self._timers[doc.id] = loop.call_later(delay, self._start_checkpoint, doc.id, loop, failed)

    def cancel_checkpoint(self, key):
        with self._queue_lock:
            self._pending.pop(key, None)
            timer = self._timers.pop(key, None)
            if timer is not None:
                timer.cancel()

    def _start_checkpoint(self, key, loop, failed):
        async def publish():
            try:
                await asyncio.to_thread(self._publish_checkpoint, key)
            except (OSError, ValueError) as error:
                if failed is not None:
                    failed(error)
        task = loop.create_task(publish())
        self._writes.add(task)
        task.add_done_callback(self._writes.discard)

    @serialized
    def _publish_checkpoint(self, key):
        with self._queue_lock:
            pending = self._pending.pop(key, None)
            self._timers.pop(key, None)
        if pending is None:
            return
        original, snapshot, _ = pending
        if getattr(original, 'private', False):
            return
        try:
            self._checkpoint(snapshot)
        except (OSError, ValueError):
            # Retain the latest live buffer for an explicit navigation retry.
            with self._queue_lock:
                self._pending.setdefault(key, pending)
            raise

    @serialized
    def flush_checkpoints(self):
        with self._queue_lock:
            documents = [value[0] for value in self._pending.values()]
        for doc in documents:
            self.checkpoint(doc)

    @serialized
    def checkpoint(self, doc):
        self.cancel_checkpoint(doc.id)
        return self._checkpoint(doc)

    def _checkpoint(self, doc):
        if getattr(doc, "private", False):
            return
        path = self.path(doc.id, '.json')
        state = (doc.name, doc.text, doc.snapshot.encoding, doc.snapshot.original)
        cached = self._checkpoints.get(doc.id)
        if cached is not None and cached[0] == state:
            try:
                if self._recovery_revision(path) == cached[1]:
                    return
            except FileNotFoundError:
                pass
        if not isinstance(doc.text, str) or len(doc.snapshot.encode(doc.text)) > MAX_BYTES:
            raise ValueError('Mobile text documents are limited to 1 MiB.')
        record = dict(schema=1, id=doc.id, name=document_name(doc.name), text=doc.text,
                      encoding=doc.snapshot.encoding,
                      original=base64.b64encode(doc.snapshot.original).decode('ascii'))
        atomic_write_json(path, record, max_bytes=MAX_RECORD,
                          durable_directory=True)
        # Only a successful durable publication may suppress a future write.
        self._checkpoints[doc.id] = (state, self._recovery_revision(path))
        with self._summary_lock:
            self._summaries[doc.id] = (self._recovery_revision(path), DocumentSummary(doc.id, doc.name))

    @serialized
    def privatize(self, doc):
        """Keep the draft in memory and replace its recovery record with the baseline."""
        doc.private = True
        baseline = Document(doc.id, doc.name, doc.snapshot, doc.snapshot.text)
        self.checkpoint(baseline)

    @serialized
    def open(self, key):
        with self._queue_lock:
            pending = self._pending.get(key)
        if pending is not None:
            self.checkpoint(pending[0])
        path = self.path(key, '.json')
        with path.open('rb') as stream:
            content = stream.read(MAX_RECORD + 1)
        if len(content) > MAX_RECORD:
            raise ValueError('Recovery record is too large; it was preserved.')
        record = json.loads(content)
        if not isinstance(record, dict) or record.get('schema') != 1 or record.get('id') != key:
            raise ValueError('Unsupported recovery record; it was preserved.')
        original = base64.b64decode(record['original'], validate=True)
        if len(original) > MAX_BYTES or not isinstance(record.get('text'), str):
            raise ValueError('Invalid recovery text; it was preserved.')
        source = self.path(key, '.data')
        snapshot = decode_bytes(original, path=source, encoding=record['encoding'])
        # Explicit encoding preserves BOM information from the stored bytes.
        doc = Document(key, document_name(record['name']), snapshot, record['text'])
        if len(snapshot.encode(doc.text)) > MAX_BYTES:
            raise ValueError('Recovery text is too large; it was preserved.')
        try:
            with source.open('rb') as stream:
                doc.conflict = stream.read(MAX_BYTES + 1) != original
        except FileNotFoundError:
            doc.conflict = True
        return doc

    def documents(self):
        documents, failures = [], []
        for path in sorted(self.root.glob('*.json')):
            try:
                documents.append(self.open(path.stem))
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append((path.name, str(error)))
        return sorted(documents, key=lambda doc: doc.name.casefold()), failures

    def cached_summaries(self):
        with self._summary_lock:
            records = [value[1] for value in self._summaries.values()]
        return sorted(records, key=lambda doc: doc.name.casefold())

    def summaries(self):
        """Read changed metadata only; never decode original bytes for a list."""
        records, failures, retained = [], [], set()
        for path in sorted(self.root.glob('*.json')):
            try:
                with self._write_lock:
                    key = path.stem
                    self.path(key, '.json')  # Reject links and invalid identities.
                    revision = self._recovery_revision(path)
                    with self._summary_lock:
                        cached = self._summaries.get(key)
                    if cached is None or cached[0] != revision:
                        with path.open('rb') as stream:
                            raw = stream.read(MAX_RECORD + 1)
                        if len(raw) > MAX_RECORD:
                            raise ValueError('Recovery record exceeds the inventory limit.')
                        record = json.loads(raw)
                        if not isinstance(record, dict) or record.get('schema') != 1 or record.get('id') != key:
                            raise ValueError('Invalid recovery summary.')
                        summary = DocumentSummary(key, document_name(record['name']))
                        with self._summary_lock:
                            self._summaries[key] = (revision, summary)
                    else:
                        summary = cached[1]
                    retained.add(key)
                    records.append(summary)
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append((path.name, str(error)))
        with self._write_lock, self._summary_lock:
            # A writer may have added another record during the scan. Remove
            # only entries whose recovery file really disappeared.
            for key in set(self._summaries) - retained:
                if not self.path(key, '.json').exists():
                    self._summaries.pop(key, None)
        return sorted(records, key=lambda doc: doc.name.casefold()), failures

    @serialized
    def save(self, doc):
        content = doc.snapshot.encode(doc.text)
        if len(content) > MAX_BYTES:
            raise ValueError('Mobile text documents are limited to 1 MiB.')
        try:
            write_text_file(self.path(doc.id, '.data'), content, expected=doc.snapshot.original)
        except FileConflictError:
            doc.conflict = True
            raise
        doc.snapshot = decode_bytes(content, path=doc.snapshot.path, encoding=doc.snapshot.encoding)
        doc.conflict = False
        doc.private = False
        self.checkpoint(doc)

    def save_copy(self, doc, name=None):
        return self.create(name or doc.name, doc.snapshot.encode(doc.text))

    @serialized
    def delete(self, doc):
        """Remove one app-owned document and its recovery record."""
        self.cancel_checkpoint(doc.id)
        source = self.path(doc.id, '.data')
        recovery = self.path(doc.id, '.json')
        # Leave recovery available if removing the saved bytes fails.
        source.unlink(missing_ok=True)
        recovery.unlink(missing_ok=True)
        self._checkpoints.pop(doc.id, None)
        with self._summary_lock:
            self._summaries.pop(doc.id, None)

    @serialized
    def discard(self, doc):
        """Reset recovery to the current saved bytes without writing the source."""
        source = self.path(doc.id, '.data')
        try:
            with source.open('rb') as stream:
                content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ValueError('Saved file is too large; the draft was preserved.')
            snapshot = decode_bytes(content, path=source)
            conflict = False
        except FileNotFoundError:
            # Discarding a draft must not recreate a concurrently deleted file.
            snapshot, conflict = doc.snapshot, True
        baseline = Document(doc.id, doc.name, snapshot, snapshot.text, conflict)
        self.checkpoint(baseline)
        doc.snapshot, doc.text, doc.conflict = snapshot, snapshot.text, conflict

    def import_document(self, provider, reference):
        # Platform handles are consumed as streams, never treated as file paths.
        with provider.open(reference) as opened:
            name, stream = opened
            from .loading_progress import reading_stream
            with reading_stream(stream) as incoming:
                content = incoming.read(MAX_BYTES + 1)
            return self.create(name, content)
