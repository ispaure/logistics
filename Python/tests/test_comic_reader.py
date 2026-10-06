"""Page ordering, local reader routes, browser views and desktop actions."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request
import zipfile
from PIL import Image

from features.comics.pages import ComicPages
from features.comics.reader import ReaderSession


class ReaderFixture:
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'comic.cbz'
        stream = BytesIO()
        Image.new('RGB', (600, 900), 'orange').save(stream, format='PNG')
        self.image = stream.getvalue()
        self.archive()

    def archive(self, manga='', entries=('10.png', '2.png', '1.png')):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('ComicInfo.xml', f'<ComicInfo><Series>Test series</Series><Writer>Writer</Writer><Volume>1</Volume><Number>2</Number><Manga>{manga}</Manga></ComicInfo>')
            for name in entries:
                archive.writestr(name, self.image)
            archive.writestr('__MACOSX/._0.png', b'not a page')


class ReaderTests(ReaderFixture, unittest.TestCase):
    def test_pages_natural_order_default_and_metadata_direction_cover_and_stale_archive(self):
        before = self.path.read_bytes()
        pages = ComicPages(self.path)
        self.assertEqual(pages.pages, ['1.png', '2.png', '10.png'])
        self.assertFalse(pages.right_to_left)
        self.assertEqual(pages.read_page(0), (self.image, 'image/png'))
        with Image.open(BytesIO(pages.cover())) as cover:
            self.assertLessEqual(cover.width, 360)
            self.assertLessEqual(cover.height, 500)
        self.assertEqual(self.path.read_bytes(), before)
        self.archive('YesAndRightToLeft')
        self.assertTrue(ComicPages(self.path).right_to_left)
        with self.assertRaises(RuntimeError):
            pages.read_page(0)

    def test_local_routes_serve_only_selected_archive_pages(self):
        self.archive('YesAndRightToLeft')
        reader = ReaderSession(self.path)
        self.addCleanup(reader.close)
        with urlopen(reader.url) as response:
            html = response.read().decode()
            self.assertIn('rtl=true', html)
            self.assertIn('ArrowRight', html)
            self.assertIn('aria-live="polite"', html)
            self.assertIn('Content-Security-Policy', response.headers)
        with urlopen(reader.url + 'page/1') as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertEqual(response.read(), self.image)
        for url in (reader.url + 'page/99', reader.url + '../anything',
                    reader.url.replace(reader.token, 'invalid')):
            with self.assertRaises(HTTPError) as error:
                urlopen(url)
            self.assertEqual(error.exception.code, 404)
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(reader.url, headers={'Host': 'outside.example'}))
        self.assertEqual(error.exception.code, 403)

    def test_browser_open_reuses_unchanged_sessions_and_replaces_changed_ones(self):
        from features.comics import reader
        with patch.object(reader.webbrowser, 'open', return_value=True):
            first = reader.open_reader(self.path)
            self.addCleanup(reader.close_readers)
            self.assertIs(reader.open_reader(self.path), first)
            self.archive('YesAndRightToLeft')
            updated = reader.open_reader(self.path)
            self.assertIsNot(first, updated)
            self.assertTrue(updated.pages.right_to_left)
        with patch.object(reader.webbrowser, 'open', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'could not be opened'):
                reader.open_reader(self.path)

    def test_tiff_is_converted_for_browser_and_no_pages_reports_error(self):
        stream = BytesIO()
        Image.new('RGB', (20, 30), 'blue').save(stream, format='TIFF')
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('01.tif', stream.getvalue())
        data, mime = ComicPages(self.path).read_page(0)
        self.assertEqual(mime, 'image/png')
        self.assertTrue(data.startswith(b'\x89PNG'))
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('notes.txt', 'no pages')
        with self.assertRaisesRegex(ValueError, 'no supported'):
            ComicPages(self.path)


class BrowserViewTests(ReaderFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def wait(self, window):
        deadline = time.monotonic() + 5
        while (window.busy or window.catalog_busy or window.browser.cover_busy or window.reader_busy) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(window.busy or window.catalog_busy or window.reader_busy)

    def test_modes_selection_preview_context_and_reader_activation(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        self.assertTrue(window.preview_panel.isHidden())
        index = window.model.index(str(self.path))
        window.tree.selectionModel().select(index, qt.QItemSelectionModel.SelectionFlag.Select |
                                            qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
        self.assertFalse(window.cover_pixmap.isNull())
        self.assertIn('Series: Test series', window.preview.toPlainText())
        self.assertIn('Author: Writer', window.preview.toPlainText())
        for mode in (1, 2, 0):
            window.view_selector.setCurrentIndex(mode)
            self.wait(window)
            self.assertEqual(window.browser.selected_rows(), [index])
            view = window.browser.currentWidget()
            selected = window.browser.covers.mapFromSource(index) if mode == 1 else index
            # Tile/column clicks select an item, rather than every model column.
            view.selectionModel().select(selected, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
            self.wait(window)
            self.assertFalse(window.preview_panel.isHidden())
            menu = window._context_menu_for(index)
            labels = [action.text() for action in menu.actions()]
            self.assertEqual(labels[0], 'Open in Default App')
            self.assertTrue(labels[1].startswith('Reveal in '))
            self.assertIn('Edit Metadata', labels)
            menu.deleteLater()
        with patch('features.comics.ui.library.open_reader') as opened:
            window._activate(index)
            self.wait(window)
            opened.assert_called_once_with(self.path)
        window.close()
        self.app.processEvents()

    def test_context_menu_reaches_column_child_views(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        window.view_selector.setCurrentIndex(2)
        self.app.processEvents()
        window.browser.context_requested.disconnect(window._context_menu)
        requested = []
        window.browser.context_requested.connect(requested.append)
        children = [view for view in window.browser.columns.findChildren(qt.QListView)
                    if view.isVisible() and view.model() is window.model
                    and window.model.filePath(view.rootIndex()) == str(self.root)]
        self.assertTrue(children)
        child = children[0]
        index = window.model.index(str(self.path))
        point = child.visualRect(index).center()
        event = qt.QContextMenuEvent(qt.QContextMenuEvent.Reason.Mouse, point,
                                    child.viewport().mapToGlobal(point))
        self.app.sendEvent(child.viewport(), event)
        self.assertEqual(requested, [index])
        window.close()
        self.app.processEvents()

    def test_double_click_can_open_reader_while_selection_cover_is_loading(self):
        from threading import Event
        from PySide6.QtTest import QTest
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        from features.comics.pages import load_preview
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        source = window.model.index(str(self.path))
        released = Event()
        def delayed(path):
            released.wait(2)
            return load_preview(path)
        with patch('features.comics.ui.library.load_preview', delayed), patch('features.comics.ui.library.open_reader') as opened:
            point = window.tree.visualRect(source).center()
            QTest.mouseClick(window.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
            self.assertTrue(window.busy)
            self.assertTrue(window.browser.isEnabled())
            QTest.mouseDClick(window.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
            released.set()
            self.wait(window)
            opened.assert_called_once_with(self.path)
        window.close()
        self.app.processEvents()

    def test_tiles_folder_navigation_and_cover_cache_are_bounded(self):
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        folder = self.root / 'nested'
        folder.mkdir()
        window.view_selector.setCurrentIndex(1)
        window._activate(window.model.index(str(folder)))
        self.assertEqual(window.browser.root, folder)
        window._up()
        self.assertEqual(window.browser.root, self.root)
        small = ComicPages(self.path).cover((120, 165))
        for i in range(140):
            window.browser.covers.complete(str(self.root / f'{i}.cbz'), small)
        self.assertEqual(len(window.browser.covers.icons), 128)
        window.close()
        self.app.processEvents()


class DesktopActionTests(unittest.TestCase):
    def test_platform_reveal_commands_and_linux_fallback(self):
        from commonUtils.osUtils import OS
        from features.comics import desktop_actions
        path = Path('/tmp/test name.cbz')
        with patch.object(desktop_actions, 'get_os', return_value=OS.MAC), patch.object(desktop_actions.subprocess, 'run') as run:
            desktop_actions.reveal(path)
            run.assert_called_once_with(['open', '-R', str(path)], check=True)
        with patch.object(desktop_actions, 'get_os', return_value=OS.WIN), patch.object(desktop_actions.subprocess, 'Popen') as start:
            desktop_actions.reveal(path)
            self.assertEqual(start.call_args.args[0][0], 'explorer')
        with patch.object(desktop_actions, 'get_os', return_value=OS.LINUX), patch.object(desktop_actions.subprocess, 'run', side_effect=FileNotFoundError), patch.object(desktop_actions, 'open_default') as opened:
            desktop_actions.reveal(path)
            opened.assert_called_once_with(path.parent)
