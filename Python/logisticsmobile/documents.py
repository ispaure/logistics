"""App-private text documents and durable, conflict-aware recovery records."""
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from commonUtils.persistence import atomic_write_json
from commonUtils.persistence.text import decode_bytes, write_text_file, FileConflictError

MAX_BYTES = 1024 * 1024
MAX_RECORD = 4 * 1024 * 1024


def document_name(name):
    if (not isinstance(name, str) or not name.strip() or len(name) > 200
            or any(ord(c) < 32 or c in '/\\' for c in name)):
        raise ValueError('Use a document name without slashes or control characters.')
    return name.strip()


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


class DocumentStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('The mobile host must supply an absolute app-private directory.')
        self.root = root.resolve()
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

    def checkpoint(self, doc):
        if getattr(doc, "private", False):
            return
        if not isinstance(doc.text, str) or len(doc.snapshot.encode(doc.text)) > MAX_BYTES:
            raise ValueError('Mobile text documents are limited to 1 MiB.')
        record = dict(schema=1, id=doc.id, name=document_name(doc.name), text=doc.text,
                      encoding=doc.snapshot.encoding,
                      original=base64.b64encode(doc.snapshot.original).decode('ascii'))
        atomic_write_json(self.path(doc.id, '.json'), record, max_bytes=MAX_RECORD,
                          durable_directory=True)

    def privatize(self, doc):
        """Keep the draft in memory and replace its recovery record with the baseline."""
        doc.private = True
        baseline = Document(doc.id, doc.name, doc.snapshot, doc.snapshot.text)
        self.checkpoint(baseline)

    def open(self, key):
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

    def import_document(self, provider, reference):
        # Platform handles are consumed as streams, never treated as file paths.
        with provider.open(reference) as opened:
            name, stream = opened
            content = stream.read(MAX_BYTES + 1)
            return self.create(name, content)
