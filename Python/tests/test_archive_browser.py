"""Real browser installation, activation, explicit archive actions and refresh."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils import archives
from features.archives import register
from features.archives.ui.page import ArchivePage
from features.archives.ui.window import _windows
from features import registry
from features.contributions import BrowserExtensionContribution, RegisteredContribution
from ui_new.file_browser import BrowserView


class ArchiveBrowserTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.note = self.root / 'notes.txt'
        self.note.write_text('Archive payload')
        self.zip = self.root / 'sample.zip'
        self.tar = self.root / 'sample.tar.gz'
        self.cbz = self.root / 'sample.cbz'
        for path, format in ((self.zip, 'zip'), (self.tar, 'tar.gz'), (self.cbz, 'zip')):
            archives.create([self.note], path, format=format)
        self.feature = register()
        self.feature.register_types()
        self.addCleanup(self.feature.set_enabled, True)
        extension = RegisteredContribution('archives', 'Archives', BrowserExtensionContribution(
            lambda host: self.feature.install_browser(host.file_browser, host=host)))
        self.host = qt.QWidget()
        layout = qt.QVBoxLayout(self.host)
        self.tabs = qt.QTabWidget()
        layout.addWidget(self.tabs)
        with patch.object(registry, 'get_browser_extensions', return_value=[extension]):
            self.view = BrowserView(root_path=self.root)
        self.browser = self.view.file_browser
        self.binding = self.view._extensions_by_feature['archives']
        self.page = ArchivePage()
        self.tabs.addTab(self.view, 'File Browser')
        self.tabs.addTab(self.page, 'Archives')
        self.host.resize(1200, 750)
        self.host.show()
        self.addCleanup(self.host.deleteLater)
        self.addCleanup(self.close_archive_documents)
        self.wait()

    def close_archive_documents(self):
        for window in tuple(_windows):
            window.close()
        self.app.processEvents()

    def wait(self):
        deadline = time.monotonic() + 10
        self.app.processEvents()
        while self.browser.busy or self.browser.folder_busy or self.browser.views.cover_busy or self.page.busy or any(window.page.busy for window in tuple(_windows)):
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()

    def select(self, path):
        index = self.browser.model.index(str(path))
        self.assertTrue(index.isValid())
        self.browser.tree.selectionModel().setCurrentIndex(index,
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait()
        return index

    def menu(self, path):
        return self.browser.context_menu_for(self.select(path))

    def test_zip_and_tar_activation_open_the_local_archive_page(self):
        for path in (self.zip, self.tar):
            self.tabs.setCurrentWidget(self.view)
            index = self.select(path)
            with patch('commonUtils.ui.desktop_actions.open_default') as fallback:
                self.browser._activate(index)
                self.wait()
            fallback.assert_not_called()
            opened = next(window for window in _windows if window.page.path == path)
            self.assertTrue(opened.isVisible())
            self.assertIsNone(self.page.path)

    def test_cbz_keeps_reader_activation_and_offers_explicit_archive_actions(self):
        handled = []
        def comic_reader(item, context):
            if item.path.suffix.lower() == '.cbz':
                handled.append(item.path)
                return True
            return False
        self.browser.install_extension('fixture.comics', activation_handlers=(comic_reader,))
        index = self.select(self.cbz)
        self.browser._activate(index)
        self.wait()
        self.assertEqual(handled, [self.cbz])
        self.assertIsNone(self.page.path)
        menu = self.browser.context_menu_for(index)
        self.addCleanup(menu.deleteLater)
        self.assertIn('Open archive manager…', [action.text() for action in menu.actions()])
        self.assertIn('Extract archive…', [action.text() for action in menu.actions()])

    def test_regular_files_offer_creation_but_not_archive_open_or_extract(self):
        menu = self.menu(self.note)
        self.addCleanup(menu.deleteLater)
        labels = [action.text() for action in menu.actions() if action.property('source') == 'Archives']
        self.assertEqual(labels, ['Create archive…', 'Create encrypted ZIP…'])

    def test_direct_extraction_uses_password_worker_and_refreshes_the_browser(self):
        destination = self.root / 'unpacked'
        menu = self.menu(self.tar)
        self.addCleanup(menu.deleteLater)
        with patch('features.archives.ui.page.extraction_destination', return_value=destination), \
             patch.object(self.browser, 'refresh_item') as refresh, \
             patch.object(self.browser, 'refresh_changed') as changed:
            next(action for action in menu.actions() if action.text() == 'Extract archive…').trigger()
            self.wait()
            self.wait()
        self.assertEqual((destination / 'notes.txt').read_text(), 'Archive payload')
        refresh.assert_called_once_with(destination)
        changed.assert_called_once_with((destination.parent,))

    def test_toggle_removes_actions_and_activation_and_reuses_controller(self):
        controller = self.binding.controller
        self.feature.set_enabled(False)
        menu = self.menu(self.zip)
        self.addCleanup(menu.deleteLater)
        self.assertFalse(any(action.property('source') == 'Archives' for action in menu.actions()))
        with patch('commonUtils.ui.desktop_actions.open_default') as fallback:
            self.browser._activate(self.browser.model.index(str(self.zip)))
        fallback.assert_called_once_with(self.zip)
        self.feature.set_enabled(True)
        self.assertIs(self.binding.controller, controller)
        self.browser._activate(self.browser.model.index(str(self.zip)))
        self.wait()
        self.assertTrue(any(window.page.path == self.zip for window in _windows))

    def test_encrypted_direct_extraction_retries_credentials_in_the_same_flow(self):
        encrypted = self.root / 'protected.zip'
        archives.create([self.note], encrypted, password='browser-secret')
        destination = self.root / 'unlocked'
        menu = self.menu(encrypted)
        self.addCleanup(menu.deleteLater)
        with patch('features.archives.ui.page.extraction_destination', return_value=destination), \
             patch('features.archives.ui.session.resolve_password', side_effect=[None, 'browser-secret']), \
             patch('features.archives.ui.session.ask_password', return_value='browser-secret') as prompt:
            next(action for action in menu.actions() if action.text() == 'Extract archive…').trigger()
            self.wait()
            self.wait()
        prompt.assert_called_once()
        self.assertEqual((destination / 'notes.txt').read_text(), 'Archive payload')

    def test_folder_creation_routes_selected_sources_to_the_local_page(self):
        folder = self.root / 'shipment'
        folder.mkdir()
        (folder / 'manifest.txt').write_text('Shipment manifest')
        self.browser.refresh()
        self.wait()
        menu = self.menu(folder)
        self.addCleanup(menu.deleteLater)
        with patch.object(ArchivePage, 'new_archive') as create:
            next(action for action in menu.actions() if action.text() == 'Create archive…').trigger()
        create.assert_called_once_with(sources=(folder,))
        self.assertTrue(any(window.page is self.binding.controller._window.page for window in _windows))

    def test_archive_details_use_the_file_hook_in_the_browser_worker(self):
        self.select(self.zip)
        titles = [self.browser.tabs.tabText(i) for i in range(self.browser.tabs.count())]
        self.assertIn('Archive Contents', titles)
        self.select(self.tar)
        titles = [self.browser.tabs.tabText(i) for i in range(self.browser.tabs.count())]
        self.assertIn('Archive Contents', titles)

    def test_standalone_browser_does_not_route_into_an_unrelated_main_window(self):
        self.tabs.removeTab(self.tabs.indexOf(self.page))
        other = qt.QWidget()
        other_tabs = qt.QTabWidget(other)
        other_page = ArchivePage()
        other_tabs.addTab(other_page, 'Archives')
        other.show()
        self.addCleanup(other.deleteLater)
        controller = self.binding.controller
        controller.open([self.zip])
        window = next(window for window in _windows if window._requested_path == self.zip)
        deadline = time.monotonic() + 5
        while window.page.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.assertEqual(window.page.path, self.zip)
        self.assertIsNone(other_page.path)
