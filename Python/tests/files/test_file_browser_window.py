"""General browser extension installation, actions and worker-safe closure."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from contextlib import closing

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
import zipfile
from PIL import Image
from commonUtils.ui import pyside as qt
from features.application import registry
from features.contributions import BrowserExtensionContribution, FeatureContributions, RegisteredContribution
from desktop.file_browser import FileBrowserWindow, open_file_browser
from desktop.pages.debug import DebugPage


def _install_browser_extension(host):
    return registry.get_feature_definition('comics').install_browser(host.file_browser, host=host)


class BrowserWindowTests(QtTestCase):
    def test_item_menu_favourites_and_drags_the_clicked_file(self):
        from desktop import document_catalog
        from desktop.browser_export import PreparedFiles
        from services.documents.catalog import DocumentCatalog

        selected = self.root / 'selected.txt'
        selected.write_bytes(b'Exact clicked file')
        original = self.path.read_bytes()
        store = DocumentCatalog(self.root / 'catalog')
        window = FileBrowserWindow(root_path=self.root)
        window.show()
        self.addCleanup(self.close_window, window)
        self.wait(window)
        browser = window.file_browser
        index = browser.model.index(str(selected))
        self.assertTrue(index.isValid())
        with patch.object(document_catalog, 'catalog', return_value=store), \
                patch.object(document_catalog, 'reference', side_effect=AssertionError('Do not use the open document')):
            menu = browser.context_menu_for(index)
            actions = {action.text(): action for action in menu.actions()}
            actions['Add to Favourites'].trigger()
            self.assertEqual([row['title'] for row in store.entries()], [selected.name])
            actions['Drag File to App…'].trigger()
            widget, = browser.findChildren(PreparedFiles)
            self.addCleanup(widget.window().close)
            self.assertEqual(widget.paths, (selected,))
            self.assertEqual(widget.paths[0].read_bytes(), b'Exact clicked file')
            menu = browser.context_menu_for(index)
            next(action for action in menu.actions() if action.text() == 'Remove from Favourites').trigger()
            self.assertEqual(store.entries(), [])
        self.assertEqual(self.path.read_bytes(), original)

    def test_new_unconstrained_tab_starts_at_home_and_can_go_up(self):
        from desktop.file_browser import FileBrowserPage
        home = self.root / 'home'
        home.mkdir()
        with patch.object(Path, 'home', return_value=home), patch.object(registry, 'get_browser_extensions', return_value=[]):
            page = FileBrowserPage()
            page.show()
            self.addCleanup(self.close_window, page)
            self.wait(page)
            view = page.workspace.add_view()
            self.wait(page)
            self.assertEqual(view.file_browser.navigation.directory, home)
            self.assertEqual(view.file_browser.navigation.library, Path(self.root.anchor))
            view.file_browser.navigation.up.click()
            self.wait(page)
            self.assertEqual(view.file_browser.navigation.directory, self.root)

    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'comic.cbz'
        image = BytesIO()
        Image.new('RGB', (20, 30), 'red').save(image, 'PNG')
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('01.png', image.getvalue())
            archive.writestr('ComicInfo.xml', '<ComicInfo><Writer>Old</Writer></ComicInfo>')

    def wait(self, window):
        self.app.processEvents()
        # Initial filesystem/index/thumbnail setup can exceed five seconds on
        # Windows CI. Await completion; this fixture does not assert scan speed.
        deadline = time.monotonic() + 15
        while (window.file_browser.busy or window.file_browser.folder_busy or
               window.file_browser.views.cover_busy or any(getattr(getattr(extension, 'controller', extension), 'reader_busy', False) for extension in window.extensions)):
            self.assertLess(time.monotonic(), deadline,
                            f'Browser workers did not settle: files={window.file_browser.busy}, '
                            f'index={window.file_browser.folder_busy}, covers={window.file_browser.views.cover_busy}')
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()

    def window(self, extensions):
        with patch.object(registry, 'get_browser_extensions', return_value=extensions):
            window = FileBrowserWindow(self.root)
        window.show()
        self.wait(window)
        self.addCleanup(self.close_window, window)
        return window

    def close_window(self, window):
        from shiboken6 import isValid
        if isValid(window):
            window.close()
            self.app.processEvents()

    def test_default_page_starts_at_home_with_filesystem_boundary_and_scoped_extra_tabs(self):
        from desktop.file_browser import FileBrowserPage
        from commonUtils.filesystem.index import DirectoryCache
        cache_temp = TemporaryDirectory()
        self.addCleanup(cache_temp.cleanup)
        with DirectoryCache(database=Path(cache_temp.name) / 'index.sqlite3') as directory_cache:
            for name in ('commonUtils.filesystem.index.directory_cache',
                         'commonUtils.ui.file_browser.index_worker.directory_cache',
                         'commonUtils.ui.file_browser.index_search.directory_cache'):
                patcher = patch(name, directory_cache)
                patcher.start()
                self.addCleanup(patcher.stop)
            directory_cache.get(self.root)
            with patch.object(Path,'home',return_value=self.root), patch.object(registry,'get_browser_extensions',return_value=[]):
                page = FileBrowserPage(); page.show()
            self.addCleanup(self.close_window,page)
            self.wait(page)
            browser = page.file_browser
            self.assertEqual(browser.navigation.library,Path(self.root.anchor))
            self.assertEqual(browser.navigation.directory,self.root)
            self.assertTrue(browser.navigation.up.isEnabled())
            self.assertFalse(browser.navigation.back.isEnabled())
            # Construction indexes the opened home scope, never the filesystem root.
            import sqlite3
            with closing(sqlite3.connect(directory_cache.database)) as db, db:
                self.assertIsNone(db.execute('SELECT 1 FROM roots WHERE root=?', (self.root.anchor,)).fetchone())
            extra = page.workspace.add_view(self.root); self.wait(page)
            self.assertEqual(extra.file_browser.navigation.library,self.root)
            self.assertFalse(extra.filesystem_scope)

    def test_repeated_index_progress_does_not_relayout_browser_controls(self):
        window = self.window([])
        browser = window.file_browser
        window.index_status.refresh()
        with patch.object(browser, '_update_index_controls', wraps=browser._update_index_controls) as layout:
            for _ in range(5):
                browser._index_progressed('Indexing files · 42 processed this run')
            layout.assert_not_called()
        self.assertIn('42 processed this run', window.index_status.label.text())

    def test_cached_size_loading_keeps_status_instead_of_flashing_scan_progress(self):
        window = self.window([])
        browser = window.file_browser
        before = browser.index_status.text()
        browser.folder_busy = True
        browser._loading_cached_only = True
        try:
            browser._index_progressed('Waiting for index writer · 0 entries/s')
            self.assertEqual(browser.index_status.text(), before)
            self.assertEqual(window.index_status.label.text(), before)
        finally:
            browser.folder_busy = False

    def test_workspace_shares_one_bottom_index_status_across_tabs(self):
        window = self.window([])
        first = window.file_browser
        second_view = window.workspace.add_view(self.root)
        self.wait(window)
        second = second_view.file_browser
        self.assertTrue(first.index_status.isHidden())
        self.assertTrue(second.index_status.isHidden())
        self.assertTrue(window.workspace.statusBar().isAncestorOf(window.index_status.label))
        second._index_progressed('Indexing /some/location · 42 processed this run')
        self.assertIn('42 processed this run', window.index_status.label.text())
        self.assertNotIn('/some/location', window.index_status.label.text())
        self.assertNotIn('/some/location', window.index_status.label.toolTip())
        window.workspace.docks[0].raise_()
        window.workspace._activate(window.workspace.docks[0])
        self.app.processEvents()
        self.assertEqual(window.index_status.label.text(), first.index_status.text())

    def test_tabs_keep_independent_navigation_and_update_titles(self):
        window = self.window([])
        first = window.workspace.active_view
        child = self.root / 'child'
        child.mkdir()
        first.file_browser.navigate(child)
        self.app.processEvents()
        self.assertEqual(window.workspace.docks[0].windowTitle(), 'child')
        second = window.workspace.add_view(self.root)
        self.wait(window)
        self.assertIsNot(first.file_browser, second.file_browser)
        self.assertEqual(second.file_browser.navigation.directory, self.root)
        self.assertEqual(first.file_browser.navigation.directory, child)
        window.workspace.docks[0].raise_()
        window.workspace._activate(window.workspace.docks[0])
        self.assertIs(window.file_browser, first.file_browser)
        window.workspace.docks[1].close()
        self.app.processEvents()
        self.assertEqual(len(window.workspace.docks), 1)
        self.assertEqual(first.file_browser.navigation.directory, child)

    def test_file_drop_pulses_then_opens_folder_and_escape_cancels_pending_hover(self):
        from PySide6.QtGui import QDragEnterEvent, QKeyEvent
        from desktop.browser_drop import BrowserDropTargets, MIME, SESSION

        target = self.root / 'Target'
        target.mkdir()
        window = self.window([])
        browser = window.file_browser
        controller = BrowserDropTargets.instance()
        self.addCleanup(controller.clear)
        view = browser.views.navigation_views[0]
        viewport = view.viewport()
        self.wait_until(lambda: browser.model.browse_index(target).isValid())
        index = browser.model.browse_index(target)
        self.wait_until(lambda: not view.visualRect(index).isEmpty())
        point = view.visualRect(index).center()
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.path))])
        mime.setData(MIME, SESSION)

        def enter():
            event = QDragEnterEvent(point, qt.Qt.DropAction.MoveAction, mime,
                                    qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.assertTrue(controller.eventFilter(viewport, event))
            self.assertTrue(event.isAccepted())

        enter()
        controller.eventFilter(viewport, QKeyEvent(qt.QEvent.Type.KeyPress, qt.Qt.Key.Key_Escape,
                                                   qt.Qt.KeyboardModifier.NoModifier))
        self.assertFalse(controller.timer.isActive())
        self.assertEqual(browser.navigation.directory, self.root)
        enter()
        controller.eventFilter(viewport, qt.QEvent(qt.QEvent.Type.DragLeave))
        self.assertFalse(controller.timer.isActive())
        enter()
        for visible in (False, True, False, True):
            controller.advance()
            self.assertEqual(controller.band.isVisible(), visible)
            self.assertEqual(browser.navigation.directory, self.root)
        controller.advance()
        self.assertEqual(browser.navigation.directory, target)
        self.assertTrue(self.path.is_file())

    def test_drop_transfers_between_internal_and_detached_browser_destinations(self):
        from PySide6.QtGui import QDropEvent
        from desktop.browser_drop import BrowserDropTargets, MIME, SESSION

        first, second, third, fourth = (self.root / name for name in ('First', 'Second', 'Third', 'Fourth'))
        for folder in (first, second, third, fourth):
            folder.mkdir()
        path = first / 'selection.txt'
        path.write_text('move across windows')
        window = self.window([])
        workspace = window.workspace
        views = [workspace.add_view(folder) for folder in (first, second, third, fourth)]
        self.wait(window)
        detached = workspace.detach_active()
        self.addCleanup(self.close_window, detached)
        self.app.processEvents()
        self.assertIs(detached.workspace.active_view, views[3])
        previous = next(dock for dock in workspace.docks if dock.widget() is views[2])
        previous.raise_()
        self.app.processEvents()
        workspace._activate(previous)
        another = workspace.detach_active()
        self.addCleanup(self.close_window, another)
        self.app.processEvents()
        self.assertIs(another.workspace.active_view, views[2])
        controller = BrowserDropTargets.instance()
        self.addCleanup(controller.clear)

        owners = {views[2]: another.workspace, views[3]: detached.workspace}
        for source, destination, host in ((first, second, views[1]), (second, third, views[2]),
                                          (third, fourth, views[3]), (fourth, first, views[0])):
            owner = owners.get(host, workspace)
            dock = next(dock for dock in owner.docks if dock.widget() is host)
            mime = qt.QMimeData()
            mime.setUrls([qt.QUrl.fromLocalFile(str(source / path.name))])
            mime.setData(MIME, SESSION)
            bar, tab = next(((bar, index) for bar in owner.findChildren(qt.QTabBar) if bar.isVisible()
                             for index in range(bar.count()) if owner._tab_dock(bar, index) is dock), (None, None))
            widget = bar if bar is not None else dock
            point = bar.tabRect(tab).center() if bar is not None else dock.rect().center()
            drop = QDropEvent(qt.QPointF(point), qt.Qt.DropAction.MoveAction, mime,
                              qt.Qt.MouseButton.LeftButton, qt.Qt.KeyboardModifier.NoModifier)
            self.assertTrue(controller.eventFilter(widget, drop))
            self.assertTrue(drop.isAccepted(), (str(destination), type(widget), point))
            self.wait_until(lambda: (destination / path.name).exists() and not host.move_actions.busy)
            self.assertFalse((source / path.name).exists())
            self.assertEqual((destination / path.name).read_text(), 'move across windows')

    def test_native_drop_uses_transfer_view_and_preserves_a_collision(self):
        from commonUtils.ui.tasks.process_progress import _windows

        source, target = self.root / 'Outside', self.root / 'Destination'
        (source / 'tree' / 'nested').mkdir(parents=True)
        target.mkdir()
        data = source / 'tree' / 'nested' / 'spaces #.txt'
        data.write_bytes(b'native drop bytes')
        (source / 'same.txt').write_bytes(b'source')
        (target / 'same.txt').write_bytes(b'existing')
        window = self.window([])
        host = window.workspace.add_view(target)
        browser = host.file_browser
        self.wait(window)
        viewport = browser.views.navigation_views[0].viewport()
        point = viewport.rect().bottomLeft() + qt.QPoint(4, -4)
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(path)) for path in (source / 'tree', data, source / 'same.txt')])
        actions = qt.Qt.DropAction.CopyAction | qt.Qt.DropAction.MoveAction
        left = qt.Qt.MouseButton.LeftButton
        before = set(_windows)

        def drop(modifiers):
            enter = qt.QDragEnterEvent(point, actions, mime, left, modifiers)
            qt.QApplication.sendEvent(viewport, enter)
            self.assertTrue(enter.isAccepted())
            event = qt.QDropEvent(qt.QPointF(point), actions, mime, left, modifiers)
            qt.QApplication.sendEvent(viewport, event)
            self.assertTrue(event.isAccepted())
            self.assertEqual(event.dropAction(), qt.Qt.DropAction.CopyAction)
            self.wait_until(lambda: bool(set(_windows) - before))
            transfer, = set(_windows) - before
            self.addCleanup(self.close_window, transfer)
            self.wait_until(lambda: transfer.result is not None)
            return transfer

        import sys
        flags = qt.Qt.KeyboardModifier
        copied = drop(flags.AltModifier if sys.platform == 'darwin' else flags.ControlModifier)
        self.assertEqual(copied.result.state, 'failed')
        self.assertIn('already exists', copied.result.error)
        self.assertIn('1 item(s) transferred', copied.details.text())
        self.assertEqual((target / 'tree' / 'nested' / data.name).read_bytes(), data.read_bytes())
        self.assertEqual((target / 'same.txt').read_bytes(), b'existing')
        self.assertEqual((source / 'same.txt').read_bytes(), b'source')

        before = set(_windows)
        moving = source / 'moving'
        moving.mkdir()
        (moving / 'one').write_bytes(b'move bytes')
        mime.setUrls([qt.QUrl.fromLocalFile(str(moving))])
        with patch('commonUtils.runtime.resources.mutations.try_rename', return_value=False) as cross_volume:
            moved = drop(flags.ControlModifier if sys.platform == 'darwin' else flags.ShiftModifier)
            cross_volume.assert_called_once()
        self.assertEqual(moved.result.state, 'succeeded')
        self.assertFalse(moving.exists())
        self.assertEqual((target / 'moving' / 'one').read_bytes(), b'move bytes')
        self.assertEqual(list(target.glob('.drag-*')), [])

    def test_outbound_mouse_drag_offers_local_urls_and_does_not_delete_sources(self):
        from PySide6.QtTest import QTest
        from commonUtils.filesystem.local_access import protect_local_root

        nested = self.root / 'Native folder' / 'sub'
        nested.mkdir(parents=True)
        (nested / 'sample.txt').write_bytes(b'selection')
        window = self.window([])
        browser = window.file_browser
        view = browser.views.navigation_views[0]
        self.wait_until(lambda: browser.model.browse_index(nested.parent).isValid())
        target = browser.sort_model.mapFromSource(browser.model.browse_index(nested.parent))
        self.wait_until(lambda: not view.visualRect(target).isEmpty())
        point = view.visualRect(target).center()
        left = qt.Qt.MouseButton.LeftButton
        modifiers = qt.Qt.KeyboardModifier.NoModifier
        viewport = view.viewport()
        def gesture():
            QTest.mousePress(viewport, left, modifiers, point)
            end = point + qt.QPoint(qt.QApplication.startDragDistance() + 1, 0)
            movement = qt.QMouseEvent(qt.QEvent.Type.MouseMove, qt.QPointF(end),
                                      qt.QPointF(viewport.mapToGlobal(end)), qt.Qt.MouseButton.NoButton, left, modifiers)
            qt.QApplication.sendEvent(viewport, movement)
            QTest.mouseRelease(viewport, left, modifiers, end)

        accepted = []

        def receive(drag, actions, default):
            from desktop.native_file_drag import local_drag_paths
            self.assertEqual(local_drag_paths(drag.mimeData()), (nested.parent,))
            self.assertTrue(actions & qt.Qt.DropAction.MoveAction)
            self.assertEqual(default, qt.Qt.DropAction.CopyAction)
            accepted.append(True)
            return qt.Qt.DropAction.MoveAction

        with patch.object(qt.QDrag, 'exec', receive):
            gesture()
        self.assertEqual(accepted, [True])
        self.assertEqual((nested / 'sample.txt').read_bytes(), b'selection')
        status = window.workspace.active_view.move_actions.operation.message
        self.assertIn('Check the file manager', status.text())
        release = protect_local_root(object(), nested, 'Use the protected provider.')
        try:
            with patch.object(qt.QDrag, 'exec', side_effect=AssertionError('Protected URLs must not be exported')):
                gesture()
            self.assertEqual(status.text(), 'Use the protected provider.')
        finally:
            release()

    def test_native_copy_cancellation_retires_nested_staging(self):
        from threading import Event
        from commonUtils.runtime.resources.local import LocalFiles
        from desktop.browser_moves import MoveSource, copy_selection

        cancelled = Event()
        nested = self.root / 'tree' / 'sub'
        nested.mkdir(parents=True)
        data = nested / 'file'
        data.write_bytes(b'cancel copy' * 90000)
        target = self.root / 'output'
        target.mkdir()

        def report(done, total, message):
            if done and message.startswith('Copying'):
                cancelled.set()

        result = copy_selection((MoveSource.local(nested.parent),), LocalFiles(target), '',
                                cancelled=cancelled.is_set, report=report)
        self.assertTrue(result.cancelled)
        self.assertEqual(result.completed, ())
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(data.read_bytes(), b'cancel copy' * 90000)

    def test_native_intent_and_cross_volume_protocol(self):
        from types import SimpleNamespace
        from desktop.native_file_drag import local_drag_paths, native_drop_action

        actions = qt.Qt.DropAction
        flags = qt.Qt.KeyboardModifier
        possible = actions.CopyAction | actions.MoveAction
        event = qt.QDragEnterEvent(qt.QPoint(), possible, qt.QMimeData(),
                                   qt.Qt.MouseButton.LeftButton, flags.NoModifier)
        source = SimpleNamespace(lstat=lambda: SimpleNamespace(st_dev=1))
        other = SimpleNamespace(lstat=lambda: SimpleNamespace(st_dev=2))
        destination = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
        for platform in ('darwin', 'win32'):
            self.assertEqual(native_drop_action(event, [source], destination, platform=platform), actions.MoveAction)
            self.assertEqual(native_drop_action(event, [source, other], destination, platform=platform), actions.CopyAction)
            self.assertEqual(native_drop_action(event, [source], destination, protected=True, platform=platform),
                             actions.CopyAction)
        linux = qt.QDragEnterEvent(qt.QPoint(), possible, qt.QMimeData(), qt.Qt.MouseButton.LeftButton,
                                   flags.ShiftModifier)
        self.assertEqual(native_drop_action(linux, [other], destination, platform='linux'), actions.MoveAction)
        mime = qt.QMimeData()
        mime.setUrls([qt.QUrl.fromLocalFile(str(self.path)), qt.QUrl('smb://example.invalid/file')])
        self.assertEqual(local_drag_paths(mime), ())

    def test_cocoa_ignore_action_reports_an_unknown_external_outcome(self):
        from desktop.native_file_drag import handoff_message

        with patch.object(qt.QApplication, 'platformName', return_value='cocoa'):
            self.assertEqual(handoff_message(qt.Qt.DropAction.IgnoreAction),
                             'Check the file manager for progress, conflicts and the outcome.')
            self.assertEqual(handoff_message(None), '')

    def test_keyboard_move_relocates_reader_progress_and_home_for_a_folder(self):
        from PySide6.QtTest import QTest
        from commonUtils.runtime.resources.local import LocalFiles
        from desktop.document_catalog import catalog
        from features.books.preferences import ReadingState
        from services.documents.progress import open_progress

        class Clipboard:
            mime = None

            def mimeData(self):
                return self.mime

            def setMimeData(self, data):
                self.mime = data

            def clear(self):
                self.mime = None

        reading, destination, state_root = (self.root / name for name in ('Reading', 'Destination', 'State'))
        for folder in (reading, destination, state_root):
            folder.mkdir()
        original = reading / 'fixture.epub'
        original.write_bytes(b'Generated book state fixture')
        window = self.window([])
        host = window.workspace.active_view
        browser = host.file_browser
        target_browser = window.workspace.add_view(destination).file_browser
        self.wait(window)
        provider = LocalFiles(self.root)
        state = {'position': 37, 'epub_bookmarks': ['passage']}
        reference = dict(type='local', path=str(original.resolve()))
        clipboard = Clipboard()
        with patch.object(qt.QApplication, 'clipboard', return_value=clipboard), \
                patch('desktop.document_catalog.cache_directory', return_value=state_root), \
                patch('commonUtils.filesystem.storage.cache_directory', return_value=state_root):
            def progress(path):
                return open_progress(provider, path, state_root, kind='desktop-epub',
                                     revision=provider.entry(path)['revision'])

            self.assertEqual(progress('Reading/fixture.epub').save(state).value, 'saved')
            legacy = ReadingState(original, folder=state_root / 'Books')
            legacy.save({'path': 'old-chapter.xhtml', 'position': 5})
            catalog(recent=True).remember(reference, original.name, dict(editor='epub'))
            window.workspace.docks[0].raise_()
            self.app.processEvents()
            browser.views.select_source(browser.model.browse_index(reading))
            view = browser.views.navigation_views[0]
            view.setFocus()
            QTest.keySequence(view, qt.QKeySequence(qt.QKeySequence.StandardKey.Cut))
            window.workspace.docks[1].raise_()
            self.app.processEvents()
            view = target_browser.views.navigation_views[0]
            view.setFocus()
            QTest.keySequence(view, qt.QKeySequence(qt.QKeySequence.StandardKey.Paste))
            moved = destination / 'Reading' / original.name
            self.wait_until(lambda: moved.exists() and not window.workspace.active_view.move_actions.busy)
            self.assertIsNone(clipboard.mime)
            self.assertEqual(progress('Destination/Reading/fixture.epub').load(), state)
            self.assertEqual(catalog(recent=True).entries('recent')[0]['source']['path'], str(moved.resolve()))
            reading.mkdir()
            original.write_bytes(b'Replacement')
            self.assertEqual(progress('Reading/fixture.epub').load(), {})
            self.assertEqual(legacy.legacy_load(), {})

    def test_detach_split_and_reattach_preserve_view_identity(self):
        source = self.window([])
        target = self.window([])
        original = source.workspace.active_view
        source.workspace.add_view(self.root)
        self.wait(source)
        dock = source.workspace.docks[0]
        source.workspace.arrange(dock, 'right')
        self.app.processEvents()
        self.assertFalse(dock.isFloating())
        source.workspace._activate(dock)
        source.workspace.detach_active()
        self.app.processEvents()
        self.assertTrue(dock.is_detached)
        target.workspace.adopt(dock, force=True)
        self.app.processEvents()
        self.assertIs(target.workspace.active_view, original)
        self.assertEqual(len(source.workspace.docks), 1)
        self.assertEqual(len(target.workspace.docks), 2)
        self.assertFalse(dock.isFloating())
        self.assertFalse(original.closing)
        self.assertFalse(original.file_browser.stopping)

    def test_detached_plus_and_index_status_belong_to_the_local_container(self):
        window = self.window([])
        original = window.workspace.active_dock
        window.workspace.add_view(self.root); self.wait(window)
        dock = window.workspace.active_dock
        detached_window = window.workspace.detach_active()
        detached = detached_window.workspace
        self.app.processEvents()
        browser = dock.widget().file_browser
        self.assertNotIn(browser, window.index_status.connected)
        self.assertIn(browser, detached.index_status.connected)
        dock.local_new_button.click(); self.wait(detached.active_view)
        self.assertEqual(window.workspace.docks, [original])
        self.assertEqual(len(detached.docks), 2)
        self.assertIsNot(detached.active_dock, dock)
        self.assertEqual(detached.active_view.file_browser.navigation.directory, self.root)
        child = self.root/'renamed'; child.mkdir()
        detached.active_view.file_browser.navigate(child); self.wait(detached.active_view)
        self.assertEqual(detached_window.windowTitle(), 'renamed — File Browser')
        from shiboken6 import isValid
        detached_window.close()
        deadline = time.monotonic() + 5
        while isValid(detached_window):
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            time.sleep(.01)
        self.assertNotIn(browser, window.index_status.connected)
        self.assertEqual(window.workspace.docks, [original])
        self.assertFalse(original.widget().file_browser.stopping)

    def test_busy_tab_disappears_immediately_and_retains_its_controller(self):
        class BusyExtension(qt.QObject):
            idle = qt.Signal()
            ready = False
            def prepare_close(self):
                return self.ready
        extension = RegisteredContribution('busy', 'Busy', BrowserExtensionContribution(lambda host: BusyExtension(host)))
        window = self.window([extension])
        dock = window.workspace.active_dock
        controller = window.extensions[0]
        window.workspace.add_view(self.root)
        window.extensions[0].ready = True
        self.wait(window)
        with patch.object(controller, 'prepare_close', wraps=controller.prepare_close) as cleanup:
            dock.close()
            cleanup.assert_not_called()
        self.assertEqual(len(window.workspace.docks), 1)
        self.assertIn(dock, window.workspace._retiring)
        self.assertFalse(dock.isVisible())
        self.app.processEvents()
        controller.ready = True
        controller.idle.emit()
        controller.idle.emit()
        self.app.processEvents()
        self.assertEqual(len(window.workspace.docks), 1)
        self.assertFalse(window.workspace._closing)
        window.workspace.add_view(self.root)
        window.extensions[0].ready = True
        self.wait(window)
        self.assertEqual(len(window.workspace.docks), 2)

    def test_debug_button_opens_browser_and_survives_empty_debug_contributions(self):
        with patch.object(registry, 'get_debug_actions', return_value=[]):
            page = DebugPage()
            page.refresh()
        with patch('desktop.file_browser.open_file_browser') as opened:
            page.open_browser_button.click()
            opened.assert_called_once_with(page.window())
        page.deleteLater()

    def test_debug_bulk_rename_opens_logistics_tool_and_cancel_opens_nothing(self):
        with patch.object(registry, 'get_debug_actions', return_value=[]):
            page = DebugPage()
            page.refresh()
        self.addCleanup(page.deleteLater)
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=str(self.root)), \
                patch('desktop.bulk_rename.open_bulk_rename') as opened:
            page.bulk_rename_button.click()
            opened.assert_called_once_with(str(self.root), parent=page.window())
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=''), \
                patch('desktop.bulk_rename.open_bulk_rename') as opened:
            page.bulk_rename_button.click()
            opened.assert_not_called()

    def test_choose_folder_cancel_and_window_retention(self):
        from desktop import file_browser
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=''):
            self.assertIsNone(open_file_browser())
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=str(self.root)), patch.object(
                registry, 'get_browser_extensions', return_value=[]):
            window = open_file_browser()
        self.assertIn(window, file_browser._windows)
        self.wait(window)
        self.close_window(window)
        self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.assertNotIn(window, file_browser._windows)

    def test_comics_extension_installs_all_actions_and_metadata_handler(self):
        extension = RegisteredContribution('comics', 'Comics', BrowserExtensionContribution(_install_browser_extension))
        window = self.window([extension])
        self.assertFalse(window.file_browser.services)
        from services.documents.ui.markdown import activate_markdown
        self.assertEqual(len(window.file_browser.activation_handlers), 2)
        self.assertIn(activate_markdown, window.file_browser.activation_handlers)
        self.assertEqual(window.file_browser.navigation.library, self.root)
        index = window.file_browser.model.index(str(self.path))
        menu = window.file_browser.context_menu_for(index)
        self.assertEqual([action.text() for action in menu.actions() if action.property('source') == 'Books & Comics'],
                         ['Edit metadata…', 'Compress Comics…'])
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=\n')
        configured_menu = window.file_browser.context_menu_for(index)
        self.assertIn('Encrypt unencrypted comics…', [action.text() for action in configured_menu.actions()])
        next(action for action in menu.actions() if action.text() == 'Edit metadata…').trigger()
        controller = window.extensions[0].controller
        editor = controller.metadata_windows[0]
        deadline = time.monotonic() + 5
        while editor.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.assertEqual(editor.editors['Writer'].text(), 'Old')
        editor.reject()
        with patch('features.comics.ui.dialogs.CompressCbzDialog') as dialog:
            next(action for action in menu.actions() if action.text() == 'Compress Comics…').trigger()
            self.assertEqual(dialog.call_args.kwargs['targets'], (self.path,))
        self.wait(window)
        menu.deleteLater()

    def test_no_extensions_keeps_generic_browser(self):
        window = self.window([])
        other = self.root / 'notes.bin'
        other.write_text('notes')
        deadline = time.monotonic() + 5
        while not window.file_browser.model.index(str(other)).isValid():
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
        menu = window.file_browser.context_menu_for(window.file_browser.model.index(str(other)))
        self.assertIn('Rename', [action.text() for action in menu.actions()])
        self.assertIn('Bulk Rename…', [action.text() for action in menu.actions()])
        self.assertFalse(window.file_browser.services)
        self.assertFalse(window.extensions)
        menu.deleteLater()

    def test_close_waits_for_extension_and_then_retries(self):
        class BusyExtension(qt.QObject):
            idle = qt.Signal()
            reader_busy = False
            ready = False
            def prepare_close(self):
                return self.ready
        controller = None
        def install(host):
            nonlocal controller
            controller = BusyExtension(host)
            return controller
        extension = RegisteredContribution('example', 'Example', BrowserExtensionContribution(install))
        window = self.window([extension])
        window.close()
        self.assertTrue(window.isVisible())
        controller.ready = True
        controller.idle.emit()
        self.app.processEvents()
        from shiboken6 import isValid
        self.assertTrue(not isValid(window) or not window.isVisible())

    def test_close_during_comic_reader_loading_waits_for_worker(self):
        from threading import Event
        from shiboken6 import isValid
        extension = RegisteredContribution('comics', 'Comics', BrowserExtensionContribution(_install_browser_extension))
        window = self.window([extension])
        controller = window.extensions[0].controller
        release = Event()
        def load(path):
            release.wait(5)
            return object()
        with patch('features.comics.ui.browser_services.ComicPages', side_effect=load), patch(
                'features.comics.ui.browser_services.open_reader'):
            controller._read(self.path)
            window.close()
            self.assertTrue(isValid(window))
            self.assertTrue(controller.reader_busy)
            release.set()
            deadline = time.monotonic() + 5
            while isValid(window):
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents()
                time.sleep(.01)

    def test_comics_toggle_updates_existing_browser_and_restores_same_controller(self):
        from commonUtils.filesystem.files import File
        from commonUtils.formats.registry import file_from_path
        from features.comics.cbz import CBZFile
        window = FileBrowserWindow(self.root)
        window.show()
        self.addCleanup(self.close_window, window)
        self.wait(window)
        binding = window._extensions_by_feature['comics']
        controller = binding.controller
        original_handlers = window.file_browser.activation_handlers
        # Books and Comics share one feature toggle; independent editors stay installed.
        reader_handlers = {handler for handler in original_handlers
                           if getattr(getattr(handler, '__self__', None), 'feature', None) is not None
                           and handler.__self__.feature.id in ('books', 'comics')}
        self.assertEqual(len(reader_handlers), 2)
        other_handlers = tuple(handler for handler in original_handlers
                               if handler not in reader_handlers)
        index = window.file_browser.model.index(str(self.path))
        window.file_browser.tree.selectionModel().setCurrentIndex(index,
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait(window)
        captured = window.file_browser.context()
        action = binding._actions_for(window.file_browser.model.item(index), captured)[0]
        registry.set_feature_enabled('comics', False)
        self.addCleanup(registry.set_feature_enabled, 'comics', True)
        self.wait(window)
        self.assertIs(type(file_from_path(self.path)), File)
        self.assertIs(type(window.file_browser.model.item(index)), File)
        self.assertNotIn('comics.read', window.file_browser.services)
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            action.run(captured)
        self.assertEqual(window.file_browser.activation_handlers, other_handlers)
        self.assertEqual([action.text() for action in window.file_browser.context_menu_for(index).actions()
                          if action.property('source') == 'Archives'],
                         ['Open archive manager…', 'Extract archive…', 'Create archive…', 'Create encrypted ZIP…'])
        self.assertEqual(window.file_browser.tabs.count(), 1)
        registry.set_feature_enabled('comics', True)
        self.wait(window)
        self.assertIsInstance(file_from_path(self.path), CBZFile)
        self.assertIs(window._extensions_by_feature['comics'].controller, controller)
        self.assertEqual(window.file_browser.activation_handlers, original_handlers)
        self.assertEqual(window.file_browser.tabs.count(), 2)

    def test_disable_comics_keeps_existing_editor_alive(self):
        from shiboken6 import isValid
        window = FileBrowserWindow(self.root)
        window.show()
        self.addCleanup(self.close_window, window)
        self.wait(window)
        controller = window._extensions_by_feature['comics'].controller
        editor = controller._open_editor(self.path)
        deadline = time.monotonic() + 5
        while editor.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        registry.set_feature_enabled('comics', False)
        self.addCleanup(registry.set_feature_enabled, 'comics', True)
        self.wait(window)
        self.assertTrue(isValid(editor))
        self.assertTrue(editor.isVisible())
        self.assertNotIn('comics.edit_metadata', window.file_browser.services)
        editor.reject()
        registry.set_feature_enabled('comics', True)
        self.wait(window)

    def test_archives_action_is_session_wide_and_toggles_independently(self):
        window = FileBrowserWindow(self.root)
        window.show()
        self.addCleanup(self.close_window, window)
        self.wait(window)
        index = window.file_browser.model.index(str(self.path))
        def archive_actions():
            menu = window.file_browser.context_menu_for(index)
            actions = [action for action in menu.actions() if action.property('source') == 'Archives']
            return menu, actions
        menu, actions = archive_actions()
        self.assertEqual([action.text() for action in actions],
                         ['Open archive manager…', 'Extract archive…', 'Create archive…', 'Create encrypted ZIP…'])
        with patch('features.archives.ui.create_zip.CreateZipDialog') as dialog:
            next(action for action in actions if action.text() == 'Create encrypted ZIP…').trigger()
            self.assertEqual(dialog.call_args.args[0], (self.path,))
            dialog.return_value.exec.assert_called_once()
        menu.deleteLater()
        registry.set_feature_enabled('archives', False)
        self.addCleanup(registry.set_feature_enabled, 'archives', True)
        self.wait(window)
        menu, actions = archive_actions()
        self.assertEqual(actions, [])
        menu.deleteLater()
        self.assertIn('Edit metadata…', [action.text() for action in window.file_browser.context_menu_for(index).actions()])
        registry.set_feature_enabled('archives', True)
        self.wait(window)
        menu, actions = archive_actions()
        self.assertEqual(len(actions), 4)
        menu.deleteLater()
