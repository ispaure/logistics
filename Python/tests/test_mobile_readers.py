"""Portable mobile library/reader scenarios using generated books and pages."""
import base64
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile
import zlib

from books_fixture import make_book
from logisticsmobile.access import LocalDocuments
from logisticsmobile.library import LibraryStore
from logisticsmobile.reading import chapter_html, image_dimensions


def png_page():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00\xff')) + chunk(b'IEND', b''))


class MobileReaderTests(unittest.TestCase):
    def test_mobile_epub_import_navigation_progress_and_bookmarks_preserve_source(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = make_book(root / 'Book.epub')
            original = source.read_bytes()
            store = LibraryStore(root / 'Library')
            with patch('os.link', side_effect=PermissionError('No hard links')):
                record = store.import_book(LocalDocuments(), source)
                record, book = store.open(record['id'])
                self.assertEqual(book.title, 'Sample Book')
                self.assertIn('First chapter', chapter_html(book, 0))
                record = store.progress(record, 1, bookmark=True)
            loaded, reopened = LibraryStore(store.root).open(record['id'])
            self.assertEqual(loaded['position'], 1)
            self.assertEqual(loaded['bookmarks'], [1])
            self.assertIn('Second chapter', chapter_html(reopened, loaded['position']))
            stale = dict(loaded)
            store.progress(loaded, 0)
            with self.assertRaises(OSError):
                store.progress(stale, 1)
            self.assertEqual(source.read_bytes(), original)

    def test_mobile_comic_reads_native_page_bytes_in_natural_order(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'Comic.cbz'
            image = png_page()
            with ZipFile(source, 'w') as archive:
                archive.writestr('page10.png', image)
                archive.writestr('page2.png', image)
                archive.writestr('ComicInfo.xml', '<ComicInfo><Manga>YesAndRightToLeft</Manga></ComicInfo>')
            store = LibraryStore(root / 'Library')
            record = store.import_book(LocalDocuments(), source)
            record, reader = store.open(record['id'])
            self.assertEqual(reader.pages, ['page2.png', 'page10.png'])
            self.assertTrue(reader.right_to_left)
            data, mime = reader.read_page(1)
            self.assertEqual(data, image)
            self.assertEqual(mime, 'image/png')
            self.assertEqual(image_dimensions(data), (1, 1))
            record = store.progress(record, 1, bookmark=True)
            self.assertEqual(store.open(record['id'])[0]['bookmarks'], [1])
            store.path(record['id'], '.cbz').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                store.open(record['id'])

    def test_mobile_reader_rejects_unsafe_archives_and_oversized_image_dimensions(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / 'Unsafe.cbz'
            with ZipFile(source, 'w') as archive:
                archive.writestr('../outside.png', png_page())
            original = source.read_bytes()
            store = LibraryStore(root / 'Library')
            with self.assertRaises(ValueError):
                store.import_book(LocalDocuments(), source)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list(store.root.iterdir()), [])
            large = bytearray(png_page())
            large[16:24] = struct.pack('>II', 8192, 8192)
            with self.assertRaises(ValueError):
                image_dimensions(bytes(large))
            with self.assertRaises(ValueError):
                image_dimensions(b'not an image')

    def test_mobile_epub_sanitizer_removes_active_html_and_external_resources(self):
        from types import SimpleNamespace
        image = png_page()
        source = (b'<html><body onload="steal()"><script>steal()</script><style>body{color:red}</style>'
                  b'<p>Safe <strong>text</strong></p><a href="https://example.invalid">Link</a>'
                  b'<img src="https://example.invalid/track"/><img src="page.png" onerror="steal()"/></body></html>')
        book = SimpleNamespace(spine=['chapter.xhtml'], members={'page.png'}, resource_sizes={'page.png': len(image)},
                               read=lambda path: source if path == 'chapter.xhtml' else image)
        html = chapter_html(book, 0)
        self.assertIn('<strong>text</strong>', html)
        self.assertIn(base64.b64encode(image).decode(), html)
        self.assertNotIn('steal()', html)
        self.assertNotIn('https://example.invalid', html)
        self.assertNotIn('onerror', html)
        self.assertIn("img-src data:", html)

