"""Native reader navigation, archive access, browser views and desktop actions."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import zipfile
from PIL import Image

from features.comics.pages import ComicPages


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

    def native_reader(self, manga=''):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.reader import ComicReaderWindow
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.archive(manga)
        reader = ComicReaderWindow(ComicPages(self.path))
        reader.show()
        reader.activateWindow()
        self.wait_reader(reader)
        from shiboken6 import isValid
        def cleanup():
            if isValid(reader):
                reader.close()
                self.app.processEvents()
        self.addCleanup(cleanup)
        return reader

    def wait_reader(self, reader):
        deadline = time.monotonic() + 5
        while reader.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(reader.busy)

    def test_native_reader_direction_keys_progress_slider_and_fit(self):
        from commonUtils.ui import pyside as qt
        from PySide6.QtTest import QTest
        for manga, forward, backward in (('', qt.Qt.Key.Key_Right, qt.Qt.Key.Key_Left),
                                          ('YesAndRightToLeft', qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right)):
            reader = self.native_reader(manga)
            self.assertFalse(reader.canvas.pixmap.isNull())
            self.assertEqual(reader.progress.value(), 0)
            self.assertEqual(reader.progress.invertedAppearance(), bool(manga))
            def handle_x():
                option = qt.QStyleOptionSlider()
                reader.progress.initStyleOption(option)
                return reader.progress.style().subControlRect(qt.QStyle.ComplexControl.CC_Slider,
                    option, qt.QStyle.SubControl.SC_SliderHandle, reader.progress).center().x()
            first_x = handle_x()
            reader.progress.setFocus()
            QTest.keyClick(reader.progress, forward)
            self.wait_reader(reader)
            self.assertEqual(reader.page, 1)
            self.assertIn('2 / 3', reader.progress_label.text())
            QTest.keyClick(reader.progress, backward)
            self.wait_reader(reader)
            self.assertEqual(reader.page, 0)
            QTest.keyClick(reader.progress, qt.Qt.Key.Key_End)
            self.wait_reader(reader)
            self.assertIn('100%', reader.progress_label.text())
            self.assertEqual(reader.page, 2)
            self.assertTrue(handle_x() < first_x if manga else handle_x() > first_x)
            reader.progress.setValue(1)
            self.wait_reader(reader)
            self.assertEqual(reader.page, 1)
            QTest.keyClick(reader.progress, qt.Qt.Key.Key_Home)
            self.wait_reader(reader)
            reader.previous_button.click()
            self.assertEqual(reader.page, 0)
            reader.close()
            self.app.processEvents()

    def test_native_windows_reused_and_changed_archives_show_errors(self):
        from commonUtils.ui import pyside as qt
        from features.comics import reader
        self.app = qt.QApplication.instance() or qt.QApplication([])
        first = reader.open_reader(self.path)
        self.wait_reader(first)
        self.assertIs(reader.open_reader(self.path), first)
        self.archive('YesAndRightToLeft')
        first.go(1)
        self.wait_reader(first)
        self.assertIn('changed', first.canvas.message)
        updated = reader.open_reader(self.path)
        self.wait_reader(updated)
        self.assertIsNot(first, updated)
        self.assertTrue(updated.pages.right_to_left)
        first.close()
        updated.close()
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.assertFalse(reader._windows)

    def test_reader_rapid_navigation_and_close_during_page_load(self):
        from threading import Event
        from features.comics.ui import reader_pages as ui_reader
        reader = self.native_reader()
        released = Event()
        original = ui_reader.read_image
        def delayed(pages, index):
            released.wait(2)
            return original(pages, index)
        with patch.object(ui_reader, 'read_image', delayed):
            reader.go(1)
            reader.go(2)
            reader.go(0)
            released.set()
            self.wait_reader(reader)
            self.assertEqual(reader.page, 0)
            self.assertFalse(reader.canvas.pixmap.isNull())
            released.clear()
            reader.go(2)
            reader.close()
            self.assertTrue(reader.closing)
            self.assertFalse(reader.isVisible())
            released.set()
            self.wait_reader(reader)

    def test_tiff_is_converted_and_no_pages_reports_error(self):
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
        while (window.busy or window.catalog_busy or window.browser.cover_busy or window.reader_busy or window.folder_busy) and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(window.busy or window.catalog_busy or window.reader_busy)

    def test_closing_reader_restores_library_without_changing_location(self):
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        folder = self.root / 'Nested'
        folder.mkdir()
        window._navigate(folder)
        window._reader_opened(ComicPages(self.path), '')
        reader = window.reader_connections[0]
        deadline = time.monotonic() + 5
        while reader.busy and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(reader.busy)
        with patch.object(window, 'raise_') as raised, patch.object(window, 'activateWindow') as activated:
            reader.close()
            self.app.processEvents()
            raised.assert_called_once()
            activated.assert_called_once()
        self.assertEqual(window.browser.browsing_directory(), folder)
        self.assertTrue(window.isVisible())
        window.close()
        self.app.processEvents()

    def test_reader_close_does_not_reopen_hidden_library(self):
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        window.hide()
        with patch.object(window, 'raise_') as raised, patch.object(window, 'activateWindow') as activated:
            window._return_to_library()
            self.app.processEvents()
            raised.assert_not_called()
            activated.assert_not_called()
        window.close()
        self.app.processEvents()

    def test_modes_selection_preview_context_and_reader_activation(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
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
            self.assertEqual([Path(window.model.filePath(row)) for row in window.browser.selected_rows()], [self.path])
            # Catalog creation can insert a folder and move filesystem rows.
            index = window.model.index(str(self.path))
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
        with patch('features.comics.ui.browser_services.open_reader') as opened:
            window._activate(index)
            self.wait(window)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(opened.call_args.args[0].path, self.path)
        window.close()
        self.app.processEvents()

    def test_compression_menu_uses_whole_mixed_selection_and_labels_comics(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        folder = self.root / 'nested'
        folder.mkdir()
        other = self.root / 'notes.txt'
        other.write_text('notes')
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        for path in (self.path, folder, other):
            window.tree.selectionModel().select(window.model.index(str(path)),
                qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
        menu = window._context_menu_for(window.model.index(str(other)))
        labels = [action.text() for action in menu.actions()]
        self.assertEqual(labels[2:], ['Comics', 'Edit Metadata', 'Compress Comics…', 'Encrypt unencrypted comics…', 'Archives', 'Create encrypted ZIP…'])
        compress = next(action for action in menu.actions() if action.text() == 'Compress Comics…')
        self.assertEqual(compress.property('source'), 'Comics')
        with patch('features.comics.ui.dialogs.CompressCbzDialog') as dialog:
            compress.trigger()
            self.assertEqual(set(dialog.call_args.kwargs['targets']), {self.path, folder})
            dialog.return_value.exec.assert_called_once()
        menu.deleteLater()
        self.wait(window)
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
        window.browser.context_requested.disconnect(window.file_browser._context_menu)
        requested = []
        window.browser.context_requested.connect(requested.append)
        children = [view for view in window.browser.columns.findChildren(qt.QListView)
                    if view.isVisible() and view.model() is window.model
                    and Path(window.model.filePath(view.rootIndex())) == self.root]
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
        with patch('features.comics.pages.load_preview', delayed), patch('features.comics.ui.browser_services.open_reader') as opened:
            point = window.tree.visualRect(source).center()
            QTest.mouseClick(window.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
            self.assertTrue(window.busy)
            self.assertTrue(window.browser.isEnabled())
            QTest.mouseDClick(window.tree.viewport(), qt.Qt.MouseButton.LeftButton, pos=point)
            released.set()
            self.wait(window)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(opened.call_args.args[0].path, self.path)
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

    def test_nested_modes_history_parent_navigation_and_folder_details(self):
        from commonUtils.ui import pyside as qt
        from features.comics.ui.library import ComicLibraryWindow
        folder = self.root / 'series'
        nested = folder / 'volume'
        nested.mkdir(parents=True)
        comic = nested / 'nested.cbz'
        comic.write_bytes(self.path.read_bytes())
        (folder / 'notes.txt').write_bytes(b'abc')
        window = ComicLibraryWindow(self.root)
        window.show()
        self.wait(window)
        window.tree.expand(window.model.index(str(folder)))
        window.tree.expand(window.model.index(str(nested)))
        # Allow QFileSystemModel to populate the descendants asynchronously.
        self.app.processEvents()
        index = window.model.index(str(comic))
        window.tree.selectionModel().setCurrentIndex(index, qt.QItemSelectionModel.SelectionFlag.ClearAndSelect |
                                                     qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait(window)
        self.assertEqual(window.navigation.directory, nested)
        for mode in (1, 2, 0, 1):
            window.view_selector.setCurrentIndex(mode)
            self.wait(window)
            self.assertEqual(window.browser.root, nested)
            self.assertEqual(window.browser.selected_rows(), [index])
            self.assertEqual(window.navigation.directory, nested)
            self.assertTrue(window.up_button.isEnabled())
        window.up_button.click()
        self.assertEqual(window.browser.root, folder)
        window.navigation.back.click()
        self.assertEqual(window.browser.root, nested)
        window.navigation.forward.click()
        self.assertEqual(window.browser.root, folder)
        window.navigation.breadcrumbs.buttons[0].click()
        self.assertEqual(window.browser.root, self.root)
        self.assertFalse(window.up_button.isEnabled())
        folder_index = window.model.index(str(folder))
        window.browser.tiles.selectionModel().setCurrentIndex(window.browser.covers.mapFromSource(folder_index),
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
        self.assertIn(f'Path: {folder}', window.preview.toPlainText())
        self.assertIn('Comics: 1', window.preview.toPlainText())
        self.assertIn('Subfolders: 1', window.preview.toPlainText())
        from features.comics.folder_stats import format_size
        expected = format_size(comic.stat().st_size + 3)
        self.assertIn(f'Total size: {expected}', window.preview.toPlainText())
        self.assertEqual(window.model.data(folder_index.siblingAtColumn(1)), expected)
        window.browser.tiles.clearSelection()
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
        self.assertEqual(window.preview.toPlainText(), '')
        window.close()
        self.app.processEvents()


class FolderStatsTests(unittest.TestCase):
    def test_recursive_sizes_counts_links_and_cancellation(self):
        from features.comics.folder_stats import scan_folders
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / 'one' / 'two'
            nested.mkdir(parents=True)
            (root / 'a.cbz').write_bytes(b'12345')
            (nested / 'b.CBZ').write_bytes(b'123')
            (nested.parent / 'notes.txt').write_bytes(b'12')
            (nested / 'cycle').symlink_to(root, target_is_directory=True)
            totals = scan_folders(root)
            self.assertEqual(totals[root].size, 10)
            self.assertEqual(totals[root].files, 3)
            self.assertEqual(totals[root].extension_counts['cbz'], 2)
            self.assertEqual(totals[root].folders, 2)
            self.assertEqual(totals[root].skipped, 1)
            self.assertEqual(totals[nested].size, 3)
            self.assertIsNone(scan_folders(root, lambda: True))


class DesktopActionTests(unittest.TestCase):
    def test_platform_reveal_commands_and_linux_fallback(self):
        from commonUtils.osUtils import OS
        from commonUtils.ui import desktop_actions
        path = Path('/tmp/test name.cbz').absolute()
        with patch.object(desktop_actions, 'get_os', return_value=OS.MAC), patch.object(desktop_actions.subprocess, 'run') as run:
            desktop_actions.reveal(path)
            run.assert_called_once_with(['open', '-R', str(path)], check=True)
        with patch.object(desktop_actions, 'get_os', return_value=OS.WIN), patch.object(desktop_actions.subprocess, 'Popen') as start:
            desktop_actions.reveal(path)
            self.assertEqual(start.call_args.args[0][0], 'explorer')
        with patch.object(desktop_actions, 'get_os', return_value=OS.LINUX), patch.object(desktop_actions.subprocess, 'run', side_effect=FileNotFoundError), patch.object(desktop_actions, 'open_default') as opened:
            desktop_actions.reveal(path)
            opened.assert_called_once_with(path.parent)
