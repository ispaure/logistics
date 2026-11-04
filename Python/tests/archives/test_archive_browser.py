"""Real browser installation, activation, explicit archive actions and refresh."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from commonUtils import archives
from features.archives import register
from features.archives.ui.page import ArchivePage
from features.archives.ui.window import _windows
from features.application import registry
from features.contributions import BrowserExtensionContribution, RegisteredContribution
from desktop.file_browser import BrowserView


class ArchiveBrowserTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        self.note = self.root / 'notes.txt'
        self.note.write_text('Archive payload')
        self.feature = register()
        self.feature.register_types()
        self.addCleanup(self.feature.set_enabled, True)
        extension = RegisteredContribution('archives', 'Archives', BrowserExtensionContribution(
            lambda host: self.feature.install_browser(host.file_browser, host=host)))
        self.host = qt.QWidget()
        layout = qt.QVBoxLayout(self.host)
        def without_folder_index(*args, **kwargs):
            # Archive routing/details use real browser workers. Folder-size
            # indexing has its own suite and must not gate these assertions.
            kwargs['calculate_folder_sizes'] = False
            return FileBrowser(*args, **kwargs)
        with patch.object(registry, 'get_browser_extensions', return_value=[extension]), \
             patch('desktop.file_browser.FileBrowser', side_effect=without_folder_index):
            self.view = BrowserView(root_path=self.root)
        self.browser = self.view.file_browser
        self.binding = self.view._extensions_by_feature['archives']
        layout.addWidget(self.view)
        self.host.resize(1200, 750)
        self.host.show()
        self.wait()

    def archive(self, name, format='zip'):
        path = self.root / name
        if not path.exists():
            archives.create([self.note], path, format=format)
        return path

    @property
    def zip(self):
        return self.archive('sample.zip')

    @property
    def tar(self):
        return self.archive('sample.tar.gz', 'tar.gz')

    @property
    def cbz(self):
        return self.archive('sample.cbz')

    def pending(self):
        return dict(details=self.browser.busy, refresh=self.browser.refresh_pending,
                    index=self.browser.folder_busy, index_pending=self.browser.folder_pending,
                    covers=self.browser.views.cover_busy,
                    documents=[str(window.page.path) for window in tuple(_windows) if window.page.busy])

    def wait(self):
        self.wait_until(lambda: not any(self.pending().values()), timeout=10,
                        message=lambda: f'Archive browser did not settle: {self.pending()}; '
                                        f'index status: {self.browser.index_status.text()}')

    def wait_for_archive(self, path):
        self.wait_until(lambda: any(window.page.path == path and not window.page.busy
                                   for window in tuple(_windows)), timeout=10,
                        message=lambda: f'Archive document did not finish opening: {path}; '
                                        + repr([(getattr(window, '_requested_path', None), window.page.path,
                                                 window.page.busy, window.page.status.text())
                                                for window in tuple(_windows)]))
        self.wait()

    def select(self, path):
        self.wait_until(lambda: self.browser.model.index(str(path)).isValid(), timeout=10,
                        message=f'Browser model did not discover {path}')
        index = self.browser.model.index(str(path))
        self.assertTrue(index.isValid())
        self.browser.tree.selectionModel().setCurrentIndex(index,
            qt.QItemSelectionModel.SelectionFlag.ClearAndSelect | qt.QItemSelectionModel.SelectionFlag.Rows)
        self.wait()
        # QFileSystemModel can sort newly discovered fixtures while events are
        # pumped. A plain QModelIndex retained across that wait can name a
        # different row; resolve the requested path again before activation.
        index = self.browser.model.index(str(path))
        self.assertTrue(index.isValid())
        self.assertEqual(self.browser.model.item(index).path, path)
        return index

    def menu(self, path):
        return self.browser.context_menu_for(self.select(path))

    def test_zip_and_tar_activation_open_retained_archive_documents(self):
        for path in (self.zip, self.tar):
            index = self.select(path)
            with patch('commonUtils.ui.desktop_actions.open_default') as fallback:
                self.browser._activate(index)
                self.wait_for_archive(path)
            fallback.assert_not_called()
            opened = next(window for window in _windows if window.page.path == path)
            self.assertTrue(opened.isVisible())

    def test_cbz_keeps_reader_activation_and_offers_explicit_archive_actions(self):
        from features.comics import register as register_comics
        comics = register_comics()
        comics.register_types()
        binding = comics.install_browser(self.browser, host=self.view)
        index = self.select(self.cbz)
        with patch.object(binding.controller, '_read') as read, \
             patch('commonUtils.ui.desktop_actions.open_default') as fallback:
            self.browser._activate(index)
            self.wait()
        read.assert_called_once_with(self.cbz)
        fallback.assert_not_called()
        self.assertFalse(_windows)
        menu = self.menu(self.cbz)
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
            self.wait_for_archive(self.tar)
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
        self.wait_for_archive(self.zip)
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
            self.wait_for_archive(encrypted)
        prompt.assert_called_once()
        self.assertEqual((destination / 'notes.txt').read_text(), 'Archive payload')

    def test_failed_or_cancelled_extraction_preserves_sources_without_refresh(self):
        encrypted = self.root / 'protected.zip'
        archives.create([self.note], encrypted, password='browser-secret')
        for name, path, status in (('failure', self.tar, 'Operation failed'),
                                   ('cancelled', encrypted, 'Cancelled.')):
            with self.subTest(outcome=name):
                destination = self.root / name
                if name == 'failure':
                    destination.mkdir()
                    (destination / 'keep.txt').write_text('Existing output')
                original = path.read_bytes()
                existing = set(_windows)
                with patch('features.archives.ui.page.extraction_destination', return_value=destination), \
                     patch('features.archives.ui.session.ask_password', return_value=None) as prompt, \
                     patch.object(self.browser, 'refresh_item') as refresh, \
                     patch.object(self.browser, 'refresh_changed') as changed:
                    self.binding.controller.open([path], extract=True)
                    window, = set(_windows) - existing
                    self.wait_until(lambda: not window.page.busy, timeout=10,
                                    message=lambda: window.page.status.text())
                    self.assertIn(status, window.page.status.text())
                    refresh.assert_not_called()
                    changed.assert_not_called()
                if name == 'failure':
                    prompt.assert_not_called()
                    self.assertEqual((destination / 'keep.txt').read_text(), 'Existing output')
                    self.assertEqual({item.name for item in destination.iterdir()}, {'keep.txt'})
                else:
                    prompt.assert_called_once()
                    self.assertFalse(destination.exists())
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(self.note.read_text(), 'Archive payload')

    def test_folder_creation_routes_selected_sources_to_an_archive_document(self):
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

    def test_browser_uses_registered_document_host_and_reuses_its_archive(self):
        from desktop.documents import DocumentsPage, register_document_host
        from commonUtils.ui.document_host import document_is_open
        other = qt.QMainWindow()
        documents = DocumentsPage(lambda: None, other)
        other.setCentralWidget(documents)
        other.show()
        # Restore registration before the managed fixture retires its windows.
        with patch.object(self.app, '_commonutils_document_hosts', {}, create=True), \
             patch.object(self.app, '_commonutils_document_host', None, create=True):
            register_document_host(documents)
            self.binding.controller.open([self.zip])
            self.wait_for_archive(self.zip)
            window = next(window for window in _windows if window._requested_path == self.zip)
            self.assertIn(window, documents.records)
            self.assertTrue(document_is_open(window))
            self.binding.controller.open([self.zip])
            self.assertEqual(len(documents.records), 1)
            self.wait_until(self.view.prepare_close, message='Originating browser did not close')
            self.assertTrue(document_is_open(window))
            self.assertFalse(window.page.closing)
            window.page.test()
            self.wait_until(lambda: not window.page.busy, timeout=10,
                            message='Retained archive did not finish checking after browser closure')
            self.assertIn('Integrity check passed', window.page.status.text())
        self.assertEqual(window.page.path, self.zip)
