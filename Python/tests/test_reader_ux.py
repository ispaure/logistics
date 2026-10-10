"""Readers keep format boundaries while sharing discoverable controls and shortcuts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from PIL import Image
from PySide6.QtTest import QTest
from commonUtils.ui import pyside as qt
from features.books.epub import EPUBBook
from features.books.reader import BooksPage
from features.comics.pages import ComicPages
from features.comics.ui.reader import ComicReaderWindow
from books_fixture import make_book


class ReaderUXTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.epub_path = make_book(self.root/'book.epub')
        self.comic_path = self.root/'comic.cbz'
        output = BytesIO()
        Image.new('RGB', (600, 900), 'blue').save(output, format='PNG')
        with ZipFile(self.comic_path, 'w') as archive:
            for number in range(5):
                archive.writestr(f'{number}.png', output.getvalue())
        self.book = BooksPage(state_folder=self.root/'state')
        self.addCleanup(self.book.deleteLater)
        self.book.resize(900, 650)
        self.book.show()
        self.book._loaded(EPUBBook(self.epub_path))
        self.comic = ComicReaderWindow(ComicPages(self.comic_path))
        self.addCleanup(self.close_comic)
        self.comic.show()
        self.settle()

    def settle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
            if not self.comic.busy and not self.comic.page_cache.busy and not self.book._loading:
                break
        self.app.processEvents()
        self.assertFalse(self.comic.busy)

    def close_comic(self):
        from shiboken6 import isValid
        if isValid(self.comic):
            self.comic.shutdown()
            self.comic.close()
            self.app.processEvents()

    def test_reader_controls_keep_file_open_in_menu_and_compact_page_margins(self):
        self.assertTrue(self.book.open_button.isHidden())
        self.assertTrue(self.comic.controls.open_button.isHidden())
        self.assertTrue(self.book.menus.open_action.isEnabled())
        self.assertTrue(self.comic.menus.shared.open_action.isEnabled())
        for controls in (self.book, self.comic.controls):
            margins = controls.layout().contentsMargins()
            self.assertEqual((margins.top(), margins.bottom()), (2, 3))
            self.assertEqual(controls.layout().spacing(), 4)

    def test_open_dialogs_and_recent_files_are_format_specific(self):
        self.assertEqual(self.book.menus.open_action.text(), 'Open EPUB…')
        with patch.object(qt.QFileDialog, 'getOpenFileName', return_value=('', '')) as dialog:
            self.book.choose_book()
            self.assertNotIn('cbz', dialog.call_args.args[3].lower())
            self.assertIn('epub', dialog.call_args.args[3].lower())
            self.comic._choose_file()
            self.assertNotIn('epub', dialog.call_args.args[3].lower())
            self.assertIn('cbz', dialog.call_args.args[3].lower())
        self.book.open_book(self.comic_path)
        self.assertIsNone(self.book.worker)
        self.assertEqual(self.book.book.path, self.epub_path.resolve())
        self.comic._request_file(self.epub_path)
        self.assertFalse(self.comic.file_loading)
        self.assertEqual(self.comic.pages.path, self.comic_path)
        history = self.book.menus.history
        history.add(self.epub_path)
        history.add(self.comic_path)
        self.comic.menus.shared.history = history
        self.book.menus._refresh_recent()
        self.comic.menus.shared._refresh_recent()
        self.assertEqual([action.text() for action in self.book.menus.recent.actions()], ['book.epub'])
        self.assertEqual([action.text() for action in self.comic.menus.shared.recent.actions()], ['comic.cbz'])

    def test_fullscreen_buttons_match_and_escape_closes_search_before_fullscreen(self):
        book_button = self.book.fullscreen_button
        comic_button = self.comic.controls.fullscreen_button
        self.assertEqual(book_button.iconSize(), comic_button.iconSize())
        size = qt.QSize(24, 24)
        self.assertEqual(book_button.icon().pixmap(size).toImage(), comic_button.icon().pixmap(size).toImage())
        self.book.activateWindow()
        self.book.toggle_fullscreen()
        self.book.show_find()
        self.app.processEvents()
        QTest.keyClick(self.book.query, qt.Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.book.find_panel.isVisible())
        self.assertTrue(self.book.isFullScreen())
        QTest.keyClick(self.book.text, qt.Qt.Key.Key_Escape)
        self.app.processEvents()
        self.assertFalse(self.book.isFullScreen())
        self.assertFalse(self.book.menus.fullscreen_action.isChecked())

    def test_menu_turns_skip_displayed_comic_spread_and_go_to_page_uses_one_based_numbers(self):
        self.comic.set_mode('double')
        self.settle()
        end = self.comic.displayed_pages[-1]
        self.comic.menus.next_page_action.trigger()
        self.settle()
        self.assertEqual(self.comic.shown_page, end + 1)
        with patch.object(qt.QInputDialog, 'getInt', return_value=(5, True)):
            self.comic.go_to_page()
            self.settle()
        self.assertEqual(self.comic.shown_page, 4)
        with patch.object(qt.QInputDialog, 'getInt', return_value=(1, True)):
            self.book.go_to_page()
        self.assertEqual(self.book.text.page_index, 0)

    def test_compact_long_titles_keep_controls_inside_both_windows(self):
        for widget, controls, title in ((self.book, self.book, self.book.title),
                                       (self.comic, self.comic.controls, self.comic.title)):
            widget.resize(640, 480)
            title.setText('A very long title ' * 30)
            self.app.processEvents()
            self.app.processEvents()
            for button in controls.findChildren(qt.QToolButton):
                if button.isVisibleTo(controls):
                    rect = qt.QRect(button.mapTo(controls, qt.QPoint()), button.size())
                    self.assertTrue(controls.rect().contains(rect), button.accessibleName())
            self.assertFalse(title.wordWrap())
        self.assertLessEqual(self.book.sidebar.width(), 192)

    def test_repagination_after_theme_and_size_changes_keeps_text_visible(self):
        from commonUtils.ui.theme import apply_theme
        theme = apply_theme(mode='dark')
        for mode in ('dark', 'light'):
            theme.set_mode(mode)
            for width in (1000, 640):
                with self.subTest(mode=mode, width=width):
                    self.book.resize(width, 480)
                    QTest.qWait(30)
                    image = self.book.grab().toImage()
                    viewport = self.book.text.viewport()
                    point = viewport.mapTo(self.book, qt.QPoint())
                    color = self.book.text.palette().color(qt.QPalette.ColorRole.Text).rgb()
                    ink = sum(image.pixel(x, y) == color
                              for y in range(point.y(), point.y() + viewport.height(), 3)
                              for x in range(point.x(), point.x() + viewport.width(), 3))
                    self.assertGreater(ink, 10, 'The rendered text disappeared after repagination')
