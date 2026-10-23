"""Memory-only document readers shared by ordinary and encrypted providers."""
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import ZipFile
from commonUtils.archives.zip_access import validate_members


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
        self.editable = self.kind in SOURCE_EXTENSIONS
        if self.kind in SOURCE_EXTENSIONS:
            if len(data) > 1024 * 1024:
                raise ValueError('Private text reading is limited to 1 MiB.')
            from commonUtils.persistence.text import TextSession
            self.session = TextSession(name, data, max_bytes=1024 * 1024)
            self.text_snapshot = self.session.text_snapshot
            self.text = self.session.text
            self.labels = [name]
        elif self.kind == '.pdf':
            from features.pdf.document import PDFDocument
            self.pdf = PDFDocument.from_source(name, self.source) if self.streaming else PDFDocument(data)
            self.data = self.pdf.data
            self.read_only = True
            self.labels = [f'Page {i + 1}' for i in range(self.pdf.count)]
        elif self.kind in {'.epub', '.cbz', '.zip'}:
            from services.documents.limits import MAX_BOOK, MAX_MEMBER
            with self.source.open_archive(name) if self.streaming else ZipFile(BytesIO(data)) as archive:
                validate_members(archive)
                members = archive.infolist()
                if len(members) > 10000 or (not self.streaming and (sum(m.file_size for m in members) > MAX_BOOK or any(m.file_size > MAX_MEMBER for m in members))):
                    raise ValueError('Archive exceeds mobile reader limits.')
                if any(m.flag_bits & 1 for m in members):
                    raise ValueError('Unlock the inner ZIP through the native reader before parsing its contents.')
                if self.kind != '.epub':
                    from features.comics.collection.pages import page_names
                    self.pages = page_names(archive)
                    self.labels = [f'Page {i + 1}' for i in range(len(self.pages))]
                    try:
                        self.right_to_left = self.comic.info.get_field('Manga') == 'YesAndRightToLeft'
                    except (OSError, ValueError, ParseError):
                        self.right_to_left = False
            if self.kind == '.epub':
                from features.books.epub import EPUBBook
                self.book = EPUBBook(Path(name), source=self.source)
                from features.books.mobile.navigation import chapter_labels
                self.labels = chapter_labels(self.book)
        else:
            raise ValueError('Private reading supports PDF, text/Markdown/INI, EPUB and PNG/JPEG/WebP CBZ/ZIP comics.')

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
            from features.books.mobile.content import chapter_text
            return 'text', chapter_text(self.book, index)
        if self.kind in SOURCE_EXTENSIONS:
            return 'text', self.text
        if self.kind == '.pdf':
            return 'image', self.pdf.page(index)
        from features.images.validation import image_dimensions, MAX_IMAGE
        with self.source.open_archive(self.name) if self.streaming else ZipFile(BytesIO(self.data)) as archive:
            member = archive.getinfo(self.pages[index])
            if member.file_size > MAX_IMAGE:
                raise ValueError('Comic page exceeds 8 MiB.')
            data = archive.read(member)
        image_dimensions(data)
        return 'image', data
