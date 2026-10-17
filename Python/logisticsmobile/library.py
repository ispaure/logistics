"""Private, bounded EPUB/CBZ imports and conflict-aware reading progress."""
from hashlib import sha256
from collections import OrderedDict
from commonUtils.runtime.archive_source import LocalArchiveSource
from commonUtils.runtime.streams import iter_chunks, file_sha256
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.archives.zip_access import validate_members
from commonUtils.persistence import atomic_write_bytes, atomic_write_json
from .documents import document_name
from .library_edits import LibraryEdits

from services.documents.limits import MAX_BOOK, MAX_MEMBER
MAX_RECORD = 128 * 1024


class LibraryStore(LibraryEdits):
    def __init__(self, root, *, archive_client=None):
        root = Path(root)
        if not root.is_absolute():
            raise ValueError('The library requires an absolute private root.')
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.verified = OrderedDict()
        self.archive_client = archive_client

    def path(self, key, suffix):
        if (not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key)
                or suffix not in {'.json', '.epub', '.cbz'}):
            raise ValueError('Invalid library identity.')
        path = self.root / (key + suffix)
        if path.is_symlink():
            raise ValueError('Library files cannot be symbolic links.')
        return path

    def read_record(self, key):
        self.recover_edit(key)
        return self._read_record(key)

    def _read_record(self, key):
        with self.path(key, '.json').open('rb') as stream:
            data = stream.read(MAX_RECORD + 1)
        if len(data) > MAX_RECORD:
            raise ValueError('Library record is too large; it was preserved.')
        return self.decode_record(key, data), data

    @staticmethod
    def decode_record(key, data):
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
        from features.books.locations import valid_location
        if 'location' in record and not valid_location(record['location']):
            raise ValueError('Invalid EPUB reading location; record was preserved.')
        locations = record.get('epub_bookmarks', [])
        if (not isinstance(locations, list) or len(locations) > 200
                or any(not valid_location(value) for value in locations)
                or len(locations) + len(bookmarks) > 200):
            raise ValueError('Invalid EPUB bookmarks; record was preserved.')
        return record

    def items(self):
        records, failures = [], []
        for path in sorted(self.root.glob('*.json')):
            try:
                records.append(self.read_record(path.stem)[0])
            except (OSError, ValueError, KeyError, TypeError) as error:
                failures.append((path.name, str(error)))
        return sorted(records, key=lambda r: r['name'].casefold()), failures

    def stored_files(self):
        """Inventory retained imports, including incomplete/corrupt records."""
        keys = {path.stem for suffix in ('.cbz', '.epub', '.json')
                for path in self.root.glob('*' + suffix)}
        items, failures = [], []
        for key in sorted(keys):
            try:
                paths = [self.path(key, suffix) for suffix in ('.cbz', '.epub', '.json')]
                size = sum(path.stat().st_size for path in paths if path.exists())
                try:
                    record = self._read_record(key)[0]
                    name, kind = record['name'], record['kind']
                except (OSError, ValueError, KeyError, TypeError):
                    name, kind = key, 'Unrecognized import'
                items.append(dict(id=key, name=name, kind=kind, size=size))
            except (OSError, ValueError) as error:
                failures.append((key, str(error)))
        return sorted(items, key=lambda item: (item['name'].casefold(), item['id'])), failures

    def delete_local_copy(self, key):
        """Delete only this UUID's import and records, never its original source."""
        from commonUtils.persistence.publication import mutation_lock
        with mutation_lock:
            paths = [self.path(key, suffix) for suffix in ('.cbz', '.epub', '.json')]
            journal = self.edit_journal(key)
            for path in (*paths, journal):
                if path.exists() and not path.is_file():
                    raise ValueError('Import storage contains a non-file; it was preserved.')
            for path in (*paths, journal):
                path.unlink(missing_ok=True)
            self.verified.clear()

    @staticmethod
    def validate_archive(path, kind='epub'):
        with ZipFile(path) as archive:
            validate_members(archive)
            infos = archive.infolist()
            if (len(infos) > 5000 or (kind == 'epub' and (sum(i.file_size for i in infos) > MAX_BOOK
                    or any(i.file_size > MAX_MEMBER for i in infos)))):
                raise ValueError('Book exceeds the mobile archive limits.')
            protected = any(i.flag_bits & 1 for i in infos)
            if kind == 'epub' and protected:
                raise ValueError('Standalone password-protected EPUB imports are not supported.')
            if kind == 'comic':
                from features.comics.mobile.pages import page_names
                page_names(archive)
            return protected

    def import_book(self, provider, reference):
        temporary, destination = None, None
        key = uuid4().hex
        try:
            with provider.open(reference) as opened:
                name, incoming = opened
                name = document_name(name)
                suffix = Path(name).suffix.lower()
                if suffix not in {'.epub', '.cbz', '.zip'}:
                    raise ValueError('Import an EPUB or CBZ/ZIP comic.')
                kind = 'epub' if suffix == '.epub' else 'comic'
                digest, length = sha256(), 0
                with NamedTemporaryFile(dir=self.root, delete=False) as stream:
                    temporary = Path(stream.name)
                    for chunk in iter_chunks(incoming):
                        length += len(chunk)
                        if kind == 'epub' and length > MAX_BOOK:
                            raise ValueError('Mobile book imports are limited to 256 MiB.')
                        digest.update(chunk)
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
            prepared = LocalArchiveSource(temporary, max_read=MAX_MEMBER, max_members=5000)
            protected = self.validate_archive(temporary, kind)
            if kind == 'epub':
                from features.books.epub import EPUBBook
                if len(EPUBBook(temporary).spine) > 5000:
                    raise ValueError('Mobile EPUB reading order is limited to 5,000 chapters.')
            elif not protected:
                pages = self.comic_reader(temporary)
                from features.comics.mobile.pages import validate_page_names
                validate_page_names(pages.pages)
            destination = self.path(key, '.epub' if kind == 'epub' else '.cbz')
            if destination.exists():
                raise FileExistsError(destination)
            prepared.check()
            os.replace(temporary, destination)
            published = LocalArchiveSource(destination, max_read=MAX_MEMBER, max_members=5000)
            if published.expected[:-1] != prepared.expected[:-1]:
                raise ValueError('Imported archive changed during publication.')
            temporary = None
            record = dict(schema=1, id=key, kind=kind, name=name, digest=digest.hexdigest(),
                          position=0, bookmarks=[], revision=0)
            atomic_write_json(self.path(key, '.json'), record, max_bytes=MAX_RECORD, durable_directory=True)
            self.remember_verified(destination, record['digest'], expected=published.expected)
            return record
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if destination is not None and not self.path(key, '.json').exists():
                destination.unlink(missing_ok=True)

    def open(self, key, *, password=None):
        record, _ = self.read_record(key)
        path = self.path(key, '.epub' if record['kind'] == 'epub' else '.cbz')
        if record['kind'] == 'epub' and path.stat().st_size > MAX_BOOK:
            raise ValueError('Stored EPUB exceeds the mobile size limit.')
        source = LocalArchiveSource(path, max_read=MAX_MEMBER, max_members=5000)
        cache_key = path, source.expected, record['digest']
        if cache_key not in self.verified:
            if file_sha256(path) != record['digest']:
                raise ValueError('Stored book changed; import it again to create a new library entry.')
            source.check()
            self.remember_verified(path, record['digest'], expected=source.expected)
        protected = self.validate_archive(path, record['kind'])
        if record['kind'] == 'epub':
            from features.books.epub import EPUBBook
            reader = EPUBBook(path)
            if len(reader.spine) > 5000:
                raise ValueError('Mobile EPUB reading order is limited to 5,000 chapters.')
        else:
            reader = self.comic_reader(path, password=password, protected=protected)
            from features.comics.mobile.pages import validate_page_names
            validate_page_names(reader.pages)
        return record, reader

    def comic_reader(self, path, *, password=None, protected=False):
        from features.comics.library import ComicDocument
        from features.comics.pages import ComicPages
        if protected:
            from commonUtils.archives.zip_access import ArchivePasswordError
            if not password:
                raise ArchivePasswordError('Enter the comic ZIP password.')
            if not isinstance(password, str) or len(password) > 4096:
                raise ValueError('Comic password exceeds its length limit.')
            from .comic_source import LocalComicSource
            if self.archive_client is None:
                from features.rclone.mobile.cloud import CloudClient
                self.archive_client = CloudClient()
            source = LocalComicSource(path, self.archive_client, password)
        else:
            source = LocalArchiveSource(path, max_read=MAX_MEMBER, max_members=5000)
        return ComicPages(path, document=ComicDocument(path, source=source, password=password))

    def remember_verified(self, path, digest, *, expected):
        source = LocalArchiveSource(path, max_read=MAX_MEMBER, max_members=5000)
        if source.expected != expected:
            raise ValueError('Archive changed while verifying its checksum.')
        self.verified[path, expected, digest] = True
        while len(self.verified) > 32:
            self.verified.popitem(last=False)

    def progress(self, record, position, *, bookmark=False, location=None):
        current, original = self.read_record(record['id'])
        if current != record:
            raise OSError('Reading progress changed; reopen the book before saving.')
        if type(position) is not int or not 0 <= position < 5000:
            raise ValueError('Invalid reading position.')
        updated = dict(record, position=position, revision=record['revision'] + 1,
                       bookmarks=list(record['bookmarks']))
        if location is not None:
            from features.books.locations import valid_location
            if record['kind'] != 'epub' or not valid_location(location):
                raise ValueError('Invalid EPUB reading location.')
            updated['location'] = dict(location)
            if bookmark:
                locations = [dict(value) for value in record.get('epub_bookmarks', [])]
                if position in updated['bookmarks'] and location['offset'] == 0:
                    updated['bookmarks'].remove(position)
                elif location in locations:
                    locations.remove(location)
                elif len(locations) + len(updated['bookmarks']) < 200:
                    locations.append(dict(location))
                else:
                    raise ValueError('This book already has 200 bookmarks.')
                updated['epub_bookmarks'] = locations
        elif bookmark:
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
