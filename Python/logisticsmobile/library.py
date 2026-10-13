"""Private, bounded EPUB/CBZ imports and conflict-aware reading progress."""
from hashlib import sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.archives.zip_access import validate_members
from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from .documents import document_name

MAX_BOOK = 256 * 1024 * 1024
MAX_MEMBER = 8 * 1024 * 1024
MAX_RECORD = 128 * 1024


class LibraryStore:
    def __init__(self, root):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('The library requires an absolute private root.')
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path(self, key, suffix):
        if (not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key)
                or suffix not in {'.json', '.epub', '.cbz'}):
            raise ValueError('Invalid library identity.')
        path = self.root / (key + suffix)
        if path.is_symlink():
            raise ValueError('Library files cannot be symbolic links.')
        return path

    def read_record(self, key):
        with self.path(key, '.json').open('rb') as stream:
            data = stream.read(MAX_RECORD + 1)
        if len(data) > MAX_RECORD:
            raise ValueError('Library record is too large; it was preserved.')
        record = json.loads(data)
        if (not isinstance(record, dict) or record.get('schema') != 1 or record.get('id') != key
                or record.get('kind') not in {'epub', 'comic'} or type(record.get('revision')) is not int
                or record['revision'] < 0 or type(record.get('position')) is not int
                or not 0 <= record['position'] < 5000):
            raise ValueError('Invalid library record; it was preserved.')
        document_name(record['name'])
        digest = record.get('digest')
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid library checksum.')
        bookmarks = record.get('bookmarks')
        if (not isinstance(bookmarks, list) or len(bookmarks) > 200
                or any(type(i) is not int or not 0 <= i < 5000 for i in bookmarks)
                or len(set(bookmarks)) != len(bookmarks)):
            raise ValueError('Invalid library bookmarks; record was preserved.')
        return record, data

    def items(self):
        records, failures = [], []
        for path in sorted(self.root.glob('*.json')):
            try:
                records.append(self.read_record(path.stem)[0])
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append((path.name, str(error)))
        return sorted(records, key=lambda r: r['name'].casefold()), failures

    @staticmethod
    def validate_archive(path):
        with ZipFile(path) as archive:
            validate_members(archive)
            infos = archive.infolist()
            if (len(infos) > 5000 or sum(i.file_size for i in infos) > MAX_BOOK
                    or any(i.file_size > MAX_MEMBER for i in infos)):
                raise ValueError('Book exceeds the mobile archive limits.')
            if any(i.flag_bits & 1 for i in infos):
                raise ValueError('Encrypted books/comics are not supported on mobile yet.')

    def import_book(self, provider, reference):
        temporary, destination = None, None
        key = uuid4().hex
        try:
            with provider.open(reference) as opened:
                name, incoming = opened
                name = document_name(name)
                suffix = Path(name).suffix.lower()
                if suffix not in {'.epub', '.cbz', '.zip'}:
                    raise ValueError('Import an EPUB or unencrypted CBZ/ZIP comic.')
                kind = 'epub' if suffix == '.epub' else 'comic'
                digest, length = sha256(), 0
                with NamedTemporaryFile(dir=self.root, delete=False) as stream:
                    temporary = Path(stream.name)
                    while chunk := incoming.read(512 * 1024):
                        length += len(chunk)
                        if length > MAX_BOOK:
                            raise ValueError('Mobile book imports are limited to 256 MiB.')
                        digest.update(chunk)
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
            self.validate_archive(temporary)
            if kind == 'epub':
                from features.books.epub import EPUBBook
                if len(EPUBBook(temporary).spine) > 5000:
                    raise ValueError('Mobile EPUB reading order is limited to 5,000 chapters.')
            else:
                from features.comics.pages import ComicPages
                pages = ComicPages(temporary)
                if any(Path(name).suffix.lower() not in {'.png', '.jpg', '.jpeg'} for name in pages.pages):
                    raise ValueError('The mobile comic reader currently supports PNG/JPEG pages only.')
            destination = self.path(key, '.epub' if kind == 'epub' else '.cbz')
            if destination.exists():
                raise FileExistsError(destination)
            os.replace(temporary, destination)
            temporary = None
            record = dict(schema=1, id=key, kind=kind, name=name, digest=digest.hexdigest(),
                          position=0, bookmarks=[], revision=0)
            atomic_write_json(self.path(key, '.json'), record, max_bytes=MAX_RECORD, durable_directory=True)
            return record
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if destination is not None and not self.path(key, '.json').exists():
                destination.unlink(missing_ok=True)

    def open(self, key):
        record, _ = self.read_record(key)
        path = self.path(key, '.epub' if record['kind'] == 'epub' else '.cbz')
        if path.stat().st_size > MAX_BOOK:
            raise ValueError('Stored book exceeds the mobile size limit.')
        digest = sha256()
        with path.open('rb') as stream:
            while chunk := stream.read(512 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != record['digest']:
            raise ValueError('Stored book changed; import it again to create a new library entry.')
        self.validate_archive(path)
        if record['kind'] == 'epub':
            from features.books.epub import EPUBBook
            reader = EPUBBook(path)
            if len(reader.spine) > 5000:
                raise ValueError('Mobile EPUB reading order is limited to 5,000 chapters.')
        else:
            from features.comics.pages import ComicPages
            reader = ComicPages(path)
            if any(Path(p).suffix.lower() not in {'.png', '.jpg', '.jpeg'} for p in reader.pages):
                raise ValueError('The mobile comic reader currently supports PNG/JPEG pages only.')
        return record, reader

    def progress(self, record, position, *, bookmark=False):
        current, original = self.read_record(record['id'])
        if current != record:
            raise OSError('Reading progress changed; reopen the book before saving.')
        if type(position) is not int or not 0 <= position < 5000:
            raise ValueError('Invalid reading position.')
        updated = dict(record, position=position, revision=record['revision'] + 1,
                       bookmarks=list(record['bookmarks']))
        if bookmark:
            if position in updated['bookmarks']:
                updated['bookmarks'].remove(position)
            elif len(updated['bookmarks']) < 200:
                updated['bookmarks'].append(position)
                updated['bookmarks'].sort()
            else:
                raise ValueError('This book already has 200 bookmarks.')
        data = json.dumps(updated, ensure_ascii=False).encode('utf-8')
        def check():
            if self.read_record(record['id'])[1] != original:
                raise OSError('Reading progress changed; reopen the book.')
        atomic_write_bytes(self.path(record['id'], '.json'), data, validate=check)
        return updated
