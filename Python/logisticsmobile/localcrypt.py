"""Ciphertext-only offline copies and bounded session-only reader content."""
import base64
from contextlib import contextmanager
from io import BytesIO
import json
import threading
import os
from pathlib import Path
from xml.etree.ElementTree import ParseError
from uuid import uuid4
from zipfile import ZipFile

from commonUtils.archives.zip_access import validate_members
from commonUtils.filesystem.snapshots import verified_file_snapshot
from .cloud import DOWNLOAD_LIMIT, download_name
from commonUtils.persistence.text import decode_bytes
from commonUtils.runtime.operations import check_cancelled
from commonUtils.persistence.publication import mutation_lock


class LocalCryptCopies:
    def __init__(self, root, client):
        self.root, self.client = Path(root), client
        self._write_lock = mutation_lock
        if not self.root.is_absolute() or self.root.is_symlink():
            raise ValueError('Encrypted copies require an app-private directory.')
        self.root.mkdir(parents=True, exist_ok=True)

    def fetch(self, remote, path):
        key = uuid4().hex
        folder = self.root / key
        folder.mkdir(mode=0o700)
        try:
            with (folder / 'data').open('xb') as output:
                record = self.client.request('crypt_fetch', remote=remote, path=path, fd=output.fileno())
            # Store encrypted relative names and a settings fingerprint, never plaintext names or keys.
            self._validate(record)
            with (folder / 'record.json').open('x', encoding='utf-8') as stream:
                json.dump(record, stream)
                stream.flush()
                os.fsync(stream.fileno())
            return key
        except Exception:
            (folder / 'data').unlink(missing_ok=True)
            (folder / 'record.json').unlink(missing_ok=True)
            folder.rmdir()
            raise

    @staticmethod
    def _validate(record):
        if (not isinstance(record, dict) or set(record) != {'remote', 'encrypted_path', 'identity'}
                or any(not isinstance(v, str) or not v for v in record.values())
                or len(record['identity']) != 64
                or any(c not in '0123456789abcdef' for c in record['identity'])):
            raise ValueError('Invalid encrypted-copy mapping.')
        download_name(record['encrypted_path'])

    def _folder(self, key):
        if not isinstance(key, str) or len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid encrypted copy.')
        folder = self.root / key
        if folder.is_symlink():
            raise ValueError('Linked encrypted copies are not supported.')
        return folder

    def _data(self, key):
        return self._folder(key) / 'data'

    def _temporary(self, key):
        return self._data(key).with_name('.save-' + uuid4().hex)

    def record(self, key):
        folder = self._folder(key)
        for name, limit in (('record.json', 8192), ('data', None)):
            path = folder / name
            if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1 or (limit is not None and path.stat().st_size > limit):
                raise ValueError('Invalid encrypted copy.')
        record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
        self._validate(record)
        return record

    def items(self):
        result = []
        for folder in sorted(self.root.iterdir()):
            try:
                record = self.record(folder.name)
            except (OSError, ValueError, TypeError):
                continue
            try:
                name = self.client.request('crypt_describe', remote=record['remote'],
                                           path=record['encrypted_path'], identity=record['identity'])
            except ValueError:
                name = 'Locked copy ' + folder.name[:8]
            result.append((folder.name, name))
        return result

    def _snapshot(self, key):
        record = self.record(key)
        path = self._data(key)
        return self._snapshot_path(record, path)

    def _snapshot_path(self, record, path):
        try:
            revision, digest = verified_file_snapshot(path)
        except ValueError as error:
            raise ValueError('Encrypted copy changed while checking its revision.') from error
        return record, revision, digest

    def _request(self, action, record, path, *, mode='rb', **values):
        with path.open(mode) as stream:
            return self.client.request(action, remote=record['remote'], path=record['encrypted_path'],
                                       identity=record['identity'], fd=stream.fileno(), **values)

    @staticmethod
    def _decoded(result):
        data = base64.b64decode(result['data'], validate=True)
        if len(data) > DOWNLOAD_LIMIT:
            raise ValueError('Decrypted copy exceeds 32 MiB.')
        return download_name(result['name']), data

    def open(self, key, *, password='', cancelled=lambda: False):
        check_cancelled(cancelled)
        revision = self._snapshot(key)
        if getattr(self.client, 'supports_streaming', False):
            reader = self._stream_reader(revision[0], self._data(key), password, cancelled)
            if self._snapshot(key) != revision:
                raise ValueError('The encrypted copy changed while opening; reopen it.')
            reader.key, reader.revision, reader.password = key, revision, password
            return reader
        result = self._request('crypt_decode', revision[0], self._data(key), password=password)
        check_cancelled(cancelled)
        if self._snapshot(key) != revision:
            raise ValueError('The encrypted copy changed while opening; reopen it.')
        reader = PrivateReader(*self._decoded(result))
        reader.key, reader.revision, reader.password = key, revision, password
        return reader

    def _stream_reader(self, record, path, password='', cancelled=lambda: False):
        from .crypt_stream import NativeSource
        source = NativeSource(self.client, record, path, password=password, cancelled=cancelled)
        if Path(source.name).suffix.lower() in {'.txt', '.md', '.markdown', '.ini'}:
            if source.size > 1024 * 1024:
                raise ValueError('Text editing is limited to 1 MiB; the file can still be moved or exported.')
            with source.open(source.name) as stream:
                return PrivateReader(source.name, stream.read())
        return PrivateReader(source.name, source=source)

    def save(self, reader, text, *, cancelled=lambda: False):
        """Verify staged ciphertext before replacing an unchanged local original."""
        if not reader.editable:
            raise ValueError('Only text, Markdown and INI copies can be edited.')
        data = reader.text_snapshot.encode(text)
        if len(data) > 1024 * 1024:
            raise ValueError('Private text editing is limited to 1 MiB.')
        # Validate the resulting document before any ciphertext can be published.
        updated = PrivateReader(reader.name, data)
        def stage(record, temporary):
            self._request('crypt_encode', record, temporary, mode='r+b', data=base64.b64encode(data).decode('ascii'))
        def verify(name, content):
            if name != reader.name or content != data:
                raise ValueError('Encrypted save verification failed; original preserved.')
            return updated
        return self._save_staged(reader, stage, verify, cancelled)

    def save_metadata(self, reader, changes, *, cancelled=lambda: False):
        from services.document_metadata import comic_metadata, epub_metadata
        from commonUtils.archives.rebuilding import patched_manifest, content_manifest
        if reader.kind == '.epub':
            member, data = epub_metadata(reader.book, changes)
        elif reader.kind in {'.cbz', '.zip'}:
            member, data = comic_metadata(reader.comic, changes)
        else:
            raise ValueError('Metadata requires a comic or EPUB.')
        if len(data) > 1024 * 1024:
            raise ValueError('Metadata exceeds 1 MiB.')
        with reader.source.open_archive(reader.name) if reader.streaming else ZipFile(BytesIO(reader.data)) as archive:
            expected = patched_manifest(archive, {member: data}, cancelled=cancelled)
        def stage(record, temporary):
            with temporary.open('r+b') as output:
                self._request('crypt_metadata', record, self._data(reader.key),
                    output_fd=output.fileno(), member=member, password=reader.password,
                    data=base64.b64encode(data).decode('ascii'))
        def verify(name, content):
            if isinstance(content, PrivateReader):
                with content.source.open_archive(content.name) as archive:
                    if name != reader.name or content_manifest(archive, cancelled=cancelled) != expected:
                        raise ValueError('Archive verification failed; original preserved.')
                return content
            with ZipFile(BytesIO(content)) as archive:
                if name != reader.name or content_manifest(archive, cancelled=cancelled) != expected:
                    raise ValueError('Archive resource verification failed; original preserved.')
            return PrivateReader(name, content)
        return self._save_staged(reader, stage, verify, cancelled)

    def _save_staged(self, reader, stage, verify, cancelled):
        """One transaction for text and archive edits; disk staging is ciphertext."""
        from commonUtils.persistence.publication import save_transaction
        record = reader.revision[0]
        target = self._data(reader.key)
        temporary = self._temporary(reader.key)
        password = getattr(reader, 'password', '')
        def validate():
            if self._snapshot(reader.key) != reader.revision:
                raise ValueError('The encrypted copy changed; original preserved. Reopen it before saving.')
        staged_revision = None
        def verified():
            nonlocal staged_revision
            before = self._snapshot_path(record, temporary)
            if getattr(reader, 'streaming', False):
                content = self._stream_reader(record, temporary, password, cancelled)
                name = content.name
            else:
                name, content = self._decoded(self._request('crypt_decode', record, temporary, password=password))
            result = verify(name, content)
            staged_revision = self._snapshot_path(record, temporary)
            if staged_revision != before:
                raise ValueError('Staged ciphertext changed during verification.')
            return result
        owned = False
        def create():
            nonlocal owned
            with temporary.open('xb'):
                owned = True
            stage(record, temporary)
        def cleanup():
            if owned:
                temporary.unlink(missing_ok=True)
        with self._write_lock:
            updated = save_transaction(stage=create, verify=verified,
                validate=validate, publish=lambda: os.replace(temporary, target),
                cleanup=cleanup, cancelled=cancelled)
            from commonUtils.runtime.operations import MutationIncomplete, MutationResult
            try:
                revision = self._snapshot(reader.key)
                if revision[0] != record or revision[2] != staged_revision[2]:
                    raise ValueError('Encrypted file changed after publication.')
                if getattr(updated, 'streaming', False):
                    updated = self._stream_reader(record, target, password, cancelled)
            except Exception as error:
                raise MutationIncomplete('The encrypted file was saved, but its new revision could not be read. Reopen it before editing.',
                                         MutationResult(destination_published=True)) from error
            updated.key, updated.revision, updated.password = reader.key, revision, password
            return updated


class MemorySource:
    """Read-only virtual archive source; contains no filesystem fallback."""
    private = True

    def __init__(self, name, data):
        self.name, self.data = name, data

    def version(self, path):
        return id(self.data), len(self.data)

    @contextmanager
    def open(self, path):
        with BytesIO(self.data) as stream:
            yield stream


class PrivateReader:
    """Bounded text, EPUB or CBZ reader. Never import into persistent libraries."""
    def __init__(self, name, data=None, *, source=None):
        self.name, self.data = name, data
        self.streaming = source is not None
        self.source = source or MemorySource(name, data)
        self.kind = Path(name).suffix.lower()
        self.book = None
        self.editable = self.kind in {'.md', '.markdown', '.txt', '.ini'}
        if self.kind in {'.md', '.markdown', '.txt', '.ini'}:
            if len(data) > 1024 * 1024:
                raise ValueError('Private text reading is limited to 1 MiB.')
            from commonUtils.persistence.text import TextSession
            self.session = TextSession(name, data, max_bytes=1024 * 1024)
            self.text_snapshot = self.session.text_snapshot
            self.text = self.session.text
            self.labels = [name]
        elif self.kind in {'.epub', '.cbz', '.zip'}:
            from .library import MAX_BOOK, MAX_MEMBER
            with self.source.open_archive(name) if self.streaming else ZipFile(BytesIO(data)) as archive:
                validate_members(archive)
                members = archive.infolist()
                if len(members) > 10000 or (not self.streaming and (sum(m.file_size for m in members) > MAX_BOOK or any(m.file_size > MAX_MEMBER for m in members))):
                    raise ValueError('Archive exceeds mobile reader limits.')
                if any(m.flag_bits & 1 for m in members):
                    raise ValueError('Unlock the inner ZIP through the native reader before parsing its contents.')
                if self.kind != '.epub':
                    from features.comics.pages import natural_key
                    self.pages = sorted((m.filename for m in members if not m.is_dir()
                                         and Path(m.filename).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}), key=natural_key)
                    if not self.pages:
                        raise ValueError('The comic contains no PNG/JPEG/WebP pages.')
                    self.labels = [f'Page {i + 1}' for i in range(len(self.pages))]
                    try:
                        self.right_to_left = self.comic.info.get_field('Manga') == 'YesAndRightToLeft'
                    except (OSError, ValueError, ParseError):
                        self.right_to_left = False
            if self.kind == '.epub':
                from features.books.epub import EPUBBook
                self.book = EPUBBook(Path(name), source=self.source)
                self.labels = [f'Chapter {i + 1}' for i in range(len(self.book.spine))]
        else:
            raise ValueError('Private reading supports text/Markdown/INI, EPUB and PNG/JPEG/WebP CBZ/ZIP comics.')

    @property
    def comic(self):
        # Malformed metadata must not prevent reading otherwise valid comic pages.
        if not hasattr(self, '_comic'):
            from features.comics.library import ComicDocument
            self._comic = ComicDocument(Path(self.name), source=self.source)
        return self._comic

    def page(self, index):
        if not 0 <= index < len(self.labels):
            raise ValueError('Page does not exist.')
        if self.book is not None:
            from html.parser import HTMLParser
            from features.books.mobile.content import chapter_html
            class Text(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts, self.hidden = [], 0
                def handle_starttag(self, tag, attrs):
                    if tag in {'head', 'style', 'script'}:
                        self.hidden += 1
                    if tag in {'p', 'div', 'br', 'h1', 'h2', 'h3', 'li', 'tr'} and not self.hidden:
                        self.parts.append('\n')
                def handle_endtag(self, tag):
                    if tag in {'head', 'style', 'script'}:
                        self.hidden = max(0, self.hidden - 1)
                def handle_data(self, value):
                    if not self.hidden:
                        self.parts.append(value)
            parser = Text()
            parser.feed(chapter_html(self.book, index))
            return 'text', ''.join(parser.parts)
        if self.kind in {'.md', '.markdown', '.txt', '.ini'}:
            return 'text', self.text
        from features.comics.mobile.validation import image_dimensions, MAX_IMAGE
        with self.source.open_archive(self.name) if self.streaming else ZipFile(BytesIO(self.data)) as archive:
            member = archive.getinfo(self.pages[index])
            if member.file_size > MAX_IMAGE:
                raise ValueError('Comic page exceeds 8 MiB.')
            data = archive.read(member)
        image_dimensions(data)
        return 'image', data
