"""Native reader navigation, archive access, browser views and desktop actions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from contextlib import contextmanager
from pathlib import Path
import time
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
import zipfile
from PIL import Image

from features.comics.pages import ComicPages
from tests.comics.fixtures import comic_library, encoded_page


class ReaderFixture:
    def setUp(self):
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'comic.cbz'
        self.image = encoded_page(size=(600, 900))
        self.archive()

    def archive(self, manga='', entries=('10.png', '2.png', '1.png')):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('ComicInfo.xml', f'<ComicInfo><Series>Test series</Series><Writer>Writer</Writer><Volume>1</Volume><Number>2</Number><Manga>{manga}</Manga></ComicInfo>')
            for name in entries:
                archive.writestr(name, self.image)
            archive.writestr('__MACOSX/._0.png', b'not a page')


class ReaderTests(ReaderFixture, QtTestCase):
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
        self.wait_until(lambda: not reader.busy, message='Reader page load did not finish')

    def test_page_slide_follows_manga_direction(self):
        from services.documents.ui.page_transition import page_slide
        reader = self.native_reader('YesAndRightToLeft')
        reader.set_mode('single')
        reader.go(1)
        self.wait_reader(reader)
        slide = page_slide(reader.canvas)
        self.assertEqual(reader.shown_page, 1)
        self.assertEqual(slide.direction, -1)
        self.assertFalse(slide.image.isNull())
        reader.go(0)
        self.wait_reader(reader)
        self.assertEqual(slide.direction, 1)

    def test_wheel_notches_turn_once_even_for_small_or_large_deltas(self):
        from commonUtils.ui import pyside as qt
        reader = self.native_reader()
        def wheel(delta):
            event = qt.QWheelEvent(qt.QPointF(10, 10), qt.QPointF(10, 10), qt.QPoint(),
                qt.QPoint(0, delta), qt.Qt.MouseButton.NoButton,
                qt.Qt.KeyboardModifier.NoModifier, qt.Qt.ScrollPhase.NoScrollPhase, False)
            self.app.sendEvent(reader.canvas, event)
            self.wait_reader(reader)
        with patch('commonUtils.ui.readers.page_wheel.monotonic', return_value=10):
            wheel(-1)
            self.assertEqual(reader.page, 1)
            wheel(1)
            self.assertEqual(reader.page, 0)
            wheel(-1200)
            self.assertEqual(reader.page, 1)
        with patch('commonUtils.ui.readers.page_wheel.monotonic', return_value=11):
            wheel(1200)
            self.assertEqual(reader.page, 0)
        self.assertEqual(reader.keys.timer.interval(), 225)

    def test_smooth_wheel_sensitivity_reload_cooldown_and_busy_guard(self):
        from commonUtils.ui import pyside as qt
        reader = self.native_reader()
        path = self.root / 'settings.ini'
        path.write_text('[WheelNavigation]\nsensitivity=1\n')
        def wheel(pixel=0, angle=0):
            event = qt.QWheelEvent(qt.QPointF(10, 10), qt.QPointF(10, 10), qt.QPoint(0, pixel),
                qt.QPoint(0, angle), qt.Qt.MouseButton.NoButton,
                qt.Qt.KeyboardModifier.NoModifier, qt.Qt.ScrollPhase.ScrollUpdate, False)
            self.app.sendEvent(reader.canvas, event)
            self.wait_reader(reader)
        with patch('commonUtils.configuration.settings.settings_path', return_value=path):
            with patch('commonUtils.ui.readers.page_wheel.monotonic', return_value=10):
                wheel(pixel=-3)
                self.assertEqual(reader.page, 0)
                path.write_text('[WheelNavigation]\nsensitivity=20\n')
                wheel(pixel=-3)
                self.assertEqual(reader.page, 1)
                wheel(pixel=-600)
                self.assertEqual(reader.page, 1)
            with patch('commonUtils.ui.readers.page_wheel.monotonic', return_value=11):
                wheel(angle=6)
                self.assertEqual(reader.page, 0)
            with patch.object(reader, 'file_loading', True):
                event = qt.QWheelEvent(qt.QPointF(), qt.QPointF(), qt.QPoint(), qt.QPoint(0, -120),
                    qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier,
                    qt.Qt.ScrollPhase.NoScrollPhase, False)
                self.app.sendEvent(reader.canvas, event)
                self.assertEqual(reader.page, 0)

    def test_notch_mode_can_be_disabled_in_shared_ini(self):
        from commonUtils.ui import pyside as qt
        reader = self.native_reader()
        path = self.root / 'settings.ini'
        path.write_text('[WheelNavigation]\nimmediate_notches=false\nsensitivity=1\n')
        with patch('commonUtils.configuration.settings.settings_path', return_value=path), patch(
                'commonUtils.ui.readers.page_wheel.monotonic', return_value=10):
            for expected in (0, 1):
                event = qt.QWheelEvent(qt.QPointF(), qt.QPointF(), qt.QPoint(), qt.QPoint(0, -60),
                    qt.Qt.MouseButton.NoButton, qt.Qt.KeyboardModifier.NoModifier,
                    qt.Qt.ScrollPhase.NoScrollPhase, False)
                self.app.sendEvent(reader.canvas, event)
                self.wait_reader(reader)
                self.assertEqual(reader.page, expected)

    def test_vertical_arrows_use_the_same_hold_cadence(self):
        from commonUtils.ui import pyside as qt
        reader = self.native_reader()
        reader.keys._navigate(qt.Qt.Key.Key_Down)
        self.wait_reader(reader)
        self.assertEqual(reader.page, 1)
        self.assertTrue(reader.keys.timer.isActive())
        self.assertEqual(reader.keys.direction, 1)
        reader.keys.stop()
        reader.keys._navigate(qt.Qt.Key.Key_Up)
        self.wait_reader(reader)
        self.assertEqual(reader.page, 0)
        self.assertEqual(reader.keys.direction, -1)
        reader.keys.stop()

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
        from features.comics.ui import reader_opening as reader
        self.app = qt.QApplication.instance() or qt.QApplication([])
        first = reader.open_reader(self.path)
        self.wait_reader(first)
        first.toggle_fullscreen()
        self.assertIs(reader.open_reader(self.path), first)
        from features.comics.reader import open_reader as legacy_open
        with self.assertWarnsRegex(FutureWarning, r'features\.comics\.ui\.reader_opening\.open_reader'):
            self.assertIs(legacy_open(self.path), first)
        self.assertTrue(first.isFullScreen())
        self.assertTrue(first.fullscreen_action.isChecked())
        first.leave_fullscreen()
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
        deadline = time.monotonic() + 5
        while reader._windows and time.monotonic() < deadline:
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(reader._windows)

    @contextmanager
    def blocked_page_load(self, reader):
        from threading import Event
        from features.comics.ui import reader as ui_reader
        reader.page_cache.stop()
        self.wait_until(lambda: not reader.page_cache.busy)
        entered, released = Event(), Event()
        original = ui_reader.read_candidates
        def delayed(pages, index):
            entered.set()
            if not released.wait(5):
                raise TimeoutError('Test did not release the page load')
            return original(pages, index)
        with patch.object(reader.page_cache, 'lookup', return_value=None), patch.object(
                ui_reader, 'read_candidates', delayed):
            try:
                yield entered
            finally:
                released.set()
                self.wait_reader(reader)

    def test_reader_rapid_navigation_displays_only_latest_requested_page(self):
        reader = self.native_reader()
        reader.set_mode('single')
        with self.blocked_page_load(reader) as entered:
            reader.go(1)
            self.wait_until(entered.is_set, message='Page worker did not start')
            reader.go(2)
            reader.go(0)
            self.assertTrue(reader.busy)
            self.assertEqual(reader.pending_page, (0, False))
        self.assertEqual(reader.page, 0)
        self.assertEqual(reader.shown_page, 0)
        self.assertEqual(reader.displayed_pages, (0,))
        self.assertFalse(reader.canvas.pixmap.isNull())

    def test_close_waits_for_page_worker_and_discards_its_result(self):
        reader = self.native_reader()
        closed = []
        reader.closed.connect(lambda: closed.append(True))
        with self.blocked_page_load(reader) as entered:
            reader.go(2)
            self.wait_until(entered.is_set, message='Page worker did not start')
            reader.close()
            self.assertTrue(reader.closing)
            self.assertTrue(reader.busy)
            self.assertFalse(reader.isVisible())
            self.assertEqual(closed, [])
        self.wait_until(lambda: bool(closed), message='Reader did not close after its worker finished')
        self.assertEqual(reader.shown_page, 0)

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


class BrowserViewTests(ReaderFixture, QtTestCase):
    def setUp(self):
        super().setUp()
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def wait(self, window):
        deadline = time.monotonic() + 10
        idle_since = None
        while True:
            # Mode switches defer selection and cover work to the next Qt
            # event turn. Drain those callbacks before deciding we are idle.
            self.app.processEvents()
            active = {name: getattr(window, name) for name in
                      ('busy', 'catalog_busy', 'reader_busy', 'folder_busy')}
            active['cover_busy'] = window.browser.cover_busy
            now = time.monotonic()
            if any(active.values()):
                idle_since = None
            elif idle_since is None:
                idle_since = now
            elif now - idle_since >= .05:
                return
            self.assertLess(now, deadline, f'Comic browser did not settle: {active}')
            time.sleep(.005)

    def test_wait_drains_deferred_work_before_asserting_idle(self):
        from types import SimpleNamespace
        from commonUtils.ui import pyside as qt
        window = SimpleNamespace(busy=False, catalog_busy=False, reader_busy=False,
                                 folder_busy=False, browser=SimpleNamespace(cover_busy=False))
        completed = []
        def finish():
            window.busy = False
            completed.append(True)
        def start():
            window.busy = True
            qt.QTimer.singleShot(0, finish)
        qt.QTimer.singleShot(0, start)
        self.wait(window)
        self.assertEqual(completed, [True])

    def test_closing_reader_restores_library_without_changing_location(self):
        window = comic_library(self.root)
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
            deadline = time.monotonic() + 5
            while not raised.called and time.monotonic() < deadline:
                self.app.processEvents()
                time.sleep(.01)
            raised.assert_called_once()
            activated.assert_called_once()
        self.assertEqual(window.browser.browsing_directory(), folder)
        self.assertTrue(window.isVisible())
        window.close()
        self.app.processEvents()

    def test_reader_close_does_not_reopen_hidden_library(self):
        window = comic_library(self.root)
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
        window = comic_library(self.root)
        window.show()
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
        self.assertIn(f'Path: {self.root}', window.preview.toPlainText())
        index = window.model.index(str(self.path))
        window.tree.selectionModel().select(index, qt.QItemSelectionModel.SelectionFlag.Select |
                                            qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait(window)
        self.assertFalse(window.preview_panel.isHidden())
        self.assertFalse(window.cover_pixmap.isNull())
        self.assertIn('Series: Test series', window.preview.toPlainText())
        self.assertIn('Author: Writer', window.preview.toPlainText())
        self.assertEqual([window.file_browser.tabs.tabText(index) for index in range(window.file_browser.tabs.count())],
                         ['File Information', 'Comic Metadata'])
        self.assertNotIn('Panels', [button.text() for button in window.findChildren(qt.QToolButton)])
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
            self.assertEqual(labels[0], 'Open')
            self.assertIn('Open in Default App', labels)
            self.assertTrue(labels[-1].startswith('Reveal in '))
            self.assertIn('Edit metadata…', labels)
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
        folder = self.root / 'nested'
        folder.mkdir()
        other = self.root / 'notes.txt'
        other.write_text('notes')
        window = comic_library(self.root)
        window.show()
        self.wait(window)
        for path in (self.path, folder, other):
            window.tree.selectionModel().select(window.model.index(str(path)),
                qt.QItemSelectionModel.SelectionFlag.Select | qt.QItemSelectionModel.SelectionFlag.Rows)
        menu = window._context_menu_for(window.model.index(str(other)))
        labels = [action.text() for action in menu.actions()]
        self.assertEqual([action.text() for action in menu.actions() if action.property('source') in ('Books & Comics', 'Archives')],
                         ['Edit metadata…', 'Compress Comics…', 'Open archive manager…', 'Extract archive…',
                          'Create archive…', 'Create encrypted ZIP…'])
        self.assertLess(labels.index('Rename'), labels.index('Bulk Rename…'))
        compress = next(action for action in menu.actions() if action.text() == 'Compress Comics…')
        self.assertEqual(compress.property('source'), 'Books & Comics')
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
        window = comic_library(self.root)
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
        from features.comics.pages import load_preview
        window = comic_library(self.root)
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
        window = comic_library(self.root)
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
        from tempfile import TemporaryDirectory
        from commonUtils.filesystem.index import DirectoryCache
        # Exercise real indexing without the cross-process desktop coordinator.
        # Retire Qt workers while the cache and its patch are still alive.
        with TemporaryDirectory() as index_folder, DirectoryCache(
                database=Path(index_folder) / 'index.sqlite3') as cache:
            with patch('commonUtils.filesystem.index.directory_cache', cache):
                with self.temporary_directory() as collection:
                    root = Path(collection)
                    (root / 'comic.cbz').write_bytes(self.path.read_bytes())
                    from commonUtils.ui import pyside as qt
                    folder = root / 'series'
                    nested = folder / 'volume'
                    nested.mkdir(parents=True)
                    comic = nested / 'nested.cbz'
                    comic.write_bytes(self.path.read_bytes())
                    (folder / 'notes.txt').write_bytes(b'abc')
                    window = comic_library(root, folder_sizes=True)
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
                    self.assertEqual(window.browser.root, root)
                    self.assertFalse(window.up_button.isEnabled())
                    folder_index = window.model.index(str(folder))
                    window.browser.tiles.selectionModel().setCurrentIndex(window.browser.covers.mapFromSource(folder_index),
                        qt.QItemSelectionModel.SelectionFlag.ClearAndSelect)
                    self.wait(window)
                    self.assertFalse(window.preview_panel.isHidden())
                    self.assertIn(f'Path: {folder}', window.preview.toPlainText())
                    self.assertIn('Comics: 1', window.preview.toPlainText())
                    self.assertIn('Subfolders: 1', window.preview.toPlainText())
                    from commonUtils.filesystem import format_size
                    expected = format_size(comic.stat().st_size + 3)
                    self.assertIn(f'Total size: {expected}', window.preview.toPlainText())
                    self.assertEqual(window.model.data(folder_index.siblingAtColumn(1)), expected)
                    window.browser.tiles.clearSelection()
                    self.wait(window)
                    self.assertFalse(window.preview_panel.isHidden())
                    self.assertIn(f'Path: {window.navigation.directory}', window.preview.toPlainText())
                    window.close()
                    self.app.processEvents()
