"""Headless Logistics document smoke suite; no Qt, Pillow or external tools.

Run with PYTHONPATH=Python python Python/tests/portable_documents.py.
These fixtures are suitable for a future embedded testbed too; this host command
alone is not mobile verification. There are no OS mocks in this module.
"""
import importlib.abc
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

# Fail on accidental dependency imports, even if installed on the desktop host.
class RejectDesktopDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'PySide6', 'PIL', 'patoolib', 'pyzipper'}:
            raise ImportError(f'Portable document suite excludes {fullname}')
        return None


class PortableDocuments(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='logistics-document-smoke-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_epub_read_and_metadata_save_preserve_resources(self):
        from books_fixture import make_book
        from features.books.epub import EPUBBook, BookError, resolve_href
        from features.books.metadata import save_metadata
        path = make_book(self.root / 'book.epub')
        book = EPUBBook(path)
        chapter = book.read(book.spine[0])
        updated, backup = save_metadata(book, {'title': ['Portable Book']})
        self.assertTrue(backup.is_file())
        self.assertEqual(updated.read(updated.spine[0]), chapter)
        with ZipFile(path) as archive:
            self.assertEqual(archive.read('OPS/unknown.dat'), b'untouched\x00bytes')
            self.assertIn(b'Portable Book', archive.read('OPS/book.opf'))
        with self.assertRaises(BookError):
            resolve_href(book.spine[0], '../../../outside.txt')
        with self.assertRaises(BookError):
            save_metadata(book, {'title': ['Stale edit']})

    def test_comic_pages_and_metadata_work_without_image_decoder(self):
        from features.comics.pages import ComicPages
        from features.comics.library import ComicDocument
        path = self.root / 'comic.cbz'
        with ZipFile(path, 'w') as archive:
            archive.writestr('page10.png', b'page ten bytes')
            archive.writestr('page2.png', b'page two bytes')
            archive.writestr('ComicInfo.xml', b'<ComicInfo><Title>Before</Title></ComicInfo>')
        document = ComicDocument(path)
        pages = ComicPages(path, document)
        self.assertEqual(pages.pages, ['page2.png', 'page10.png'])
        self.assertEqual(pages.read_page(0), (b'page two bytes', 'image/png'))
        document.save({'Title': 'After'})
        with ZipFile(path) as archive:
            self.assertEqual(archive.read('page2.png'), b'page two bytes')
            self.assertIn(b'After', archive.read('ComicInfo.xml'))
        # Reading compressed image bytes needs no decoder; rendering does.
        with self.assertRaisesRegex(RuntimeError, 'optional Pillow'):
            pages.cover()

    def test_markdown_and_text_save_reject_stale_changes(self):
        from commonUtils.formats.markdown import split_frontmatter
        from commonUtils.persistence.text import read_text_file, write_text_file, FileConflictError
        path = self.root / 'notes.md'
        path.write_bytes(b'---\r\ntitle: Notes\r\n---\r\nHello\r\n')
        snapshot = read_text_file(path)
        self.assertEqual(split_frontmatter(snapshot.text).body, 'Hello\n')
        self.assertEqual(snapshot.encode(snapshot.text), path.read_bytes())
        data = snapshot.encode(snapshot.text + 'Saved\n')
        write_text_file(path, data, expected=snapshot.original)
        self.assertEqual(path.read_bytes(), data)
        with self.assertRaises(FileConflictError):
            write_text_file(path, b'stale', expected=snapshot.original)
        self.assertEqual(path.read_bytes(), data)


def main():
    forbidden = {'PySide6', 'PIL', 'patoolib', 'pyzipper'}
    if any(name.split('.')[0] in forbidden for name in sys.modules):
        raise RuntimeError('Run the portable suite in a fresh interpreter')
    blocker = RejectDesktopDependencies()
    sys.meta_path.insert(0, blocker)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(PortableDocuments)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() and not result.skipped else 1
    finally:
        sys.meta_path.remove(blocker)


if __name__ == '__main__':
    raise SystemExit(main())
