"""General browser extension installation, actions and worker-safe closure."""
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
from features import registry
from features.contributions import BrowserExtensionContribution, FeatureContributions, RegisteredContribution
from ui_new.file_browser import FileBrowserWindow, open_file_browser
from ui_new.pages.debug import DebugPage


def _install_browser_extension(host):
    return registry.get_feature_definition('comics').install_browser(host.file_browser, host=host)


class BrowserWindowTests(QtTestCase):
    def test_new_unconstrained_tab_starts_at_home_and_can_go_up(self):
        from ui_new.file_browser import FileBrowserPage
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
        deadline = time.monotonic() + 5
        while (window.file_browser.busy or window.file_browser.folder_busy or
               window.file_browser.views.cover_busy or any(getattr(getattr(extension, 'controller', extension), 'reader_busy', False) for extension in window.extensions)):
            self.assertLess(time.monotonic(), deadline)
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
        from ui_new.file_browser import FileBrowserPage
        from commonUtils.filesystem.index import DirectoryCache
        cache_temp = TemporaryDirectory()
        self.addCleanup(cache_temp.cleanup)
        with DirectoryCache(database=Path(cache_temp.name) / 'index.sqlite3') as directory_cache:
            for name in ('commonUtils.directory_index.directory_cache',
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
        with patch.object(browser, '_update_pause_button', wraps=browser._update_pause_button) as layout:
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
        for placement in ('tabs', 'left', 'tabs', 'right'):
            source.workspace.arrange(dock, placement)
            self.app.processEvents()
            if placement != 'tabs':
                other = next(candidate for candidate in source.workspace.docks if candidate is not dock)
                self.assertFalse(dock.geometry().intersects(other.geometry()))
                self.assertEqual(dock.geometry().left() < other.geometry().left(), placement == 'left')
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
        self.assertEqual(detached_window.windowTitle(), 'File Browser: renamed')
        detached_window.close(); self.wait(window)
        self.app.processEvents()
        self.assertIn(browser, window.index_status.connected)
        self.assertEqual(len(window.workspace.docks), 3)
        self.assertFalse(browser.stopping)

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
        with patch('ui_new.file_browser.open_file_browser') as opened:
            page.open_browser_button.click()
            opened.assert_called_once_with(page.window())
        page.deleteLater()

    def test_debug_bulk_rename_opens_logistics_tool_and_cancel_opens_nothing(self):
        with patch.object(registry, 'get_debug_actions', return_value=[]):
            page = DebugPage()
            page.refresh()
        self.addCleanup(page.deleteLater)
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=str(self.root)), \
                patch('ui_new.bulk_rename.open_bulk_rename') as opened:
            page.bulk_rename_button.click()
            opened.assert_called_once_with(str(self.root), parent=page.window())
        with patch.object(qt.QFileDialog, 'getExistingDirectory', return_value=''), \
                patch('ui_new.bulk_rename.open_bulk_rename') as opened:
            page.bulk_rename_button.click()
            opened.assert_not_called()

    def test_choose_folder_cancel_and_window_retention(self):
        from ui_new import file_browser
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
        self.assertEqual(len(window.file_browser.activation_handlers), 1)
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
        other_handlers = tuple(handler for handler in original_handlers
                               if handler.__self__.feature.id not in ('books', 'comics'))
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
