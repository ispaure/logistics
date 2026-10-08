"""General browser extension installation, actions and worker-safe closure."""

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
from commonUtils.ui import pyside as qt
from features import registry
from features.contributions import BrowserExtensionContribution, FeatureContributions, RegisteredContribution
from ui_new.file_browser import FileBrowserWindow, open_file_browser
from ui_new.pages.debug import DebugPage


def _install_browser_extension(host):
    return registry.get_feature_definition('comics').install_browser(host.file_browser, host=host)


class BrowserWindowTests(unittest.TestCase):
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
        self.assertEqual([action.text() for action in menu.actions() if action.property('source') == 'Comics'],
                         ['Edit Metadata', 'Compress Comics…'])
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=\n')
        configured_menu = window.file_browser.context_menu_for(index)
        self.assertIn('Encrypt unencrypted comics…', [action.text() for action in configured_menu.actions()])
        next(action for action in menu.actions() if action.text() == 'Edit Metadata').trigger()
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
        from commonUtils.fileUtils import File
        from commonUtils.fileTypes.registry import file_from_path
        from features.comics.cbz import CBZFile
        window = FileBrowserWindow(self.root)
        window.show()
        self.addCleanup(self.close_window, window)
        self.wait(window)
        binding = window._extensions_by_feature['comics']
        controller = binding.controller
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
        self.assertFalse(window.file_browser.activation_handlers)
        self.assertEqual([action.text() for action in window.file_browser.context_menu_for(index).actions()
                          if action.property('source') == 'Archives'], ['Create encrypted ZIP…'])
        self.assertEqual(window.file_browser.tabs.count(), 1)
        registry.set_feature_enabled('comics', True)
        self.wait(window)
        self.assertIsInstance(file_from_path(self.path), CBZFile)
        self.assertIs(window._extensions_by_feature['comics'].controller, controller)
        self.assertEqual(len(window.file_browser.activation_handlers), 1)
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
        self.assertEqual([action.text() for action in actions], ['Create encrypted ZIP…'])
        with patch('features.archives.ui.create_zip.CreateZipDialog') as dialog:
            actions[0].trigger()
            self.assertEqual(dialog.call_args.args[0], (self.path,))
            dialog.return_value.exec.assert_called_once()
        menu.deleteLater()
        registry.set_feature_enabled('archives', False)
        self.addCleanup(registry.set_feature_enabled, 'archives', True)
        self.wait(window)
        menu, actions = archive_actions()
        self.assertEqual(actions, [])
        menu.deleteLater()
        self.assertIn('Edit Metadata', [action.text() for action in window.file_browser.context_menu_for(index).actions()])
        registry.set_feature_enabled('archives', True)
        self.wait(window)
        menu, actions = archive_actions()
        self.assertEqual(len(actions), 1)
        menu.deleteLater()
