"""Screen pages follow text locations and EPUB covers use bounded browser previews."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from features.books.epub import EPUBBook
from features.books.file_type import EPUBFile
from features.books.reader import BooksPage
from books_fixture import make_book


def replace_members(path, changes):
    with ZipFile(path) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries.update(changes)
    with ZipFile(path, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


class BookPaginationTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = make_book(self.root / 'book.epub')

    def page(self):
        replace_members(self.path, {'OPS/Text/one.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><body>' +
            ''.join(f'<p>Paragraph {number}: A sentence to read on a screen-sized page.</p>' for number in range(100)) + '</body></html>'})
        page = BooksPage(state_folder=self.root / 'state')
        self.addCleanup(page.deleteLater)
        page.resize(1000, 650)
        page.show()
        page._loaded(EPUBBook(self.path))
        QTest.qWait(30)
        return page

    def test_arrows_turn_whole_pages_and_cross_chapters_in_both_directions(self):
        page = self.page()
        self.assertGreater(page.text.page_count, 3)
        self.assertEqual(page.text.page_index, 0)
        QTest.keyClick(page.text, qt.Qt.Key.Key_Right)
        self.assertEqual(page.text.page_index, 1)
        self.assertEqual(page.text.verticalScrollBar().value(), page.text.page_height)
        QTest.keyClick(page.text, qt.Qt.Key.Key_Left)
        self.assertEqual(page.text.page_index, 0)
        page.text.show_page(page.text.page_count - 1)
        QTest.keyClick(page.text, qt.Qt.Key.Key_Right)
        QTest.qWait(20)
        self.assertEqual(page._current, 1)
        self.assertEqual(page.text.page_index, 0)
        QTest.keyClick(page.text, qt.Qt.Key.Key_Left)
        QTest.qWait(20)
        self.assertEqual(page._current, 0)
        self.assertEqual(page.text.page_index, page.text.page_count - 1)

    def test_saved_locations_and_bookmarks_survive_font_and_window_changes(self):
        page = self.page()
        page.text.show_page(2)
        offset = page.text.location()
        self.assertGreater(offset, 0)
        page._save_state()
        self.assertEqual(page._state.load()['location'], offset)
        page.font_size.setValue(26)
        QTest.qWait(30)
        self.assertLessEqual(page.text.location(), offset)
        cursor = qt.QTextCursor(page.text.document())
        cursor.setPosition(offset)
        self.assertGreaterEqual(page.text.cursorRect(cursor).top(), 0)
        self.assertLess(page.text.cursorRect(cursor).top(), page.text.viewport().height())
        page._bookmarks = [dict(label='Here', path=page._path, position=0, location=offset)]
        page.text.show_page(0)
        page.open_bookmark(0)
        QTest.qWait(20)
        self.assertGreater(page.text.page_index, 0)
        page.resize(900, 500)
        QTest.qWait(20)
        self.assertEqual(page.text.document().pageSize().height(), page.text.page_height)
        self.assertEqual(page.text.verticalScrollBar().value() % page.text.page_height, 0)

    def test_browser_panel_and_thumbnail_show_epub3_and_epub2_covers(self):
        image = qt.QImage(100, 200, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('blue'))
        output = qt.QBuffer()
        output.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        image.save(output, 'PNG')
        with ZipFile(self.path) as archive:
            original = archive.read('OPS/book.opf').decode()
        for declaration, metadata in (('properties="cover-image"', ''), ('', '<meta name="cover" content="cover"/>')):
            with self.subTest(declaration=declaration):
                package = original.replace('</manifest>', f'<item id="cover" href="cover.png" media-type="image/png" {declaration}/></manifest>')
                package = package.replace('</metadata>', metadata + '</metadata>')
                replace_members(self.path, {'OPS/book.opf': package, 'OPS/cover.png': bytes(output.data())})
                file = EPUBFile(self.path)
                details = file.browser_panels()[0].load()
                self.assertEqual(dict(details.fields)['Title'], 'Sample Book')
                self.assertEqual(dict(details.fields)['Author'], 'One Author')
                self.assertTrue(details.thumbnail)
                thumbnail = qt.QImage.fromData(file.browser_thumbnail((40, 40)))
                self.assertEqual((thumbnail.width(), thumbnail.height()), (20, 40))

    def test_missing_cover_keeps_metadata_available(self):
        details = EPUBFile(self.path).browser_panels()[0].load()
        self.assertFalse(details.thumbnail)
        self.assertIn('No cover', details.message)
        self.assertIn(('Title', 'Sample Book'), details.fields)

    def test_search_snaps_to_page_with_match(self):
        page = self.page()
        page.query.setText('Paragraph 75:')
        page.find_next()
        self.assertGreater(page.text.page_index, 0)
        self.assertEqual(page.text.textCursor().selectedText(), 'Paragraph 75:')
        self.assertEqual(page.text.verticalScrollBar().value(), page.text.page_index * page.text.page_height)

    def test_cover_page_fallback_and_broken_image_preserve_metadata(self):
        image = qt.QImage(100, 200, qt.QImage.Format.Format_RGB32)
        image.fill(qt.QColor('red'))
        output = qt.QBuffer()
        output.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        image.save(output, 'PNG')
        replace_members(self.path, {'OPS/Text/one.xhtml': '<html xmlns="http://www.w3.org/1999/xhtml"><body><img src="../cover.png"/></body></html>',
                                    'OPS/cover.png': bytes(output.data())})
        self.assertTrue(EPUBFile(self.path).browser_panels()[0].load().thumbnail)
        replace_members(self.path, {'OPS/cover.png': b'broken image'})
        details = EPUBFile(self.path).browser_panels()[0].load()
        self.assertIn(('Title', 'Sample Book'), details.fields)
        self.assertFalse(details.thumbnail)
        self.assertTrue(details.message)
