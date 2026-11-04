"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from commonUtils.filesystem.native_paths import native_path
from commonUtils.ui import pyside as qt
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import mapping as copy_mapping
from features.comics.library import ComicDocument
from tests.local_crypt_fixture import crypt_fixture


from tests.resources.localcrypt_cases import LocalCryptCase


class LocalCryptBrowserTests(LocalCryptCase):
    def test_regular_browser_routes_navigation_and_reuses_private_tab(self):
        from desktop.file_browser import FileBrowserPage, _browser_view, _new_browser_tab, _crypt_location
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.application.registry.get_browser_extensions', return_value=[]), \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary):
            page = FileBrowserPage(root_path=f.root)
            original = page.workspace.active_view
            browser = original.file_browser
            try:
                browser.navigate(f.item.data)
                self.wait(lambda: isinstance(page.workspace.active_view, CryptBrowserView))
                private = page.workspace.active_view
                self.wait(lambda: not private.file_browser.operation.busy)
                self.assertTrue(private.view_title.startswith('🕵️ Private - '))
                self.assertEqual(private.file_browser.tree.topLevelItemCount(), 5)
                self.assertIn('note.md', [private.file_browser.tree.topLevelItem(i).text(0) for i in range(5)])
                self.assertEqual(browser.navigation.directory, f.root)
                with patch('desktop.file_browser.time.monotonic', return_value=123), \
                     patch('desktop.file_browser._crypt_location', return_value=(f.item, True)) as resolve, \
                     patch.object(copy_mapping, 'storage_root', return_value=f.item.root) as root_lookup:
                    for _ in range(1000):
                        self.assertTrue(original._directory_boundary(f.item.data))
                    resolve.assert_called_once()
                    root_lookup.assert_called_once()
                # Ciphertext I/O paths may carry Windows' extended prefix.
                # Both spellings must route privately before any OS activation.
                for raw in (f.item.data, native_path(f.item.data), f.provider.encrypted_path('note.md')):
                    self.assertEqual(_crypt_location(raw), (f.item, True))
                index = browser.model.index(str(f.item.data))
                self.assertTrue(index.isValid())
                self.assertEqual(browser.model.rowCount(index), 0)
                self.assertFalse(browser.model.canFetchMore(index))
                browser.set_directory(f.item.data)
                self.wait(lambda: not original._crypt_route_pending)
                self.assertEqual(len(page.workspace.docks), 2)
                # Breadcrumb, tree expansion, columns and direct view roots all route.
                for invoke in (lambda: browser.navigation.requested.emit(f.item.data),
                               lambda: browser.views.set_root(f.item.data),
                               lambda: browser.views._expanded(browser.sort_model.mapFromSource(index)),
                               lambda: browser._activate_path(f.provider.encrypted_path('note.md'))):
                    invoke()
                    self.wait(lambda: not original._crypt_route_pending)
                    self.assertEqual(browser.navigation.directory, f.root)
                    self.assertEqual(len(page.workspace.docks), 2)
                browser.views.set_mode(2)
                browser.views.select_source(index)
                self.wait(lambda: not browser.views._column_selection_pending and not original._crypt_route_pending)
                self.assertEqual(browser.navigation.directory, f.root)
                self.assertEqual(len(page.workspace.docks), 2)
                alias = f.root / 'alias'
                alias.symlink_to(f.item.data, target_is_directory=True)
                aliased = _browser_view(alias)
                try:
                    self.assertIsInstance(aliased, CryptBrowserView)
                    self.wait(lambda: not aliased.file_browser.operation.busy)
                    self.assertEqual(aliased.file_browser.navigation.directory, f.item.data)
                finally:
                    self.wait(aliased.prepare_close)
                    aliased.close()
                # A private new tab keeps a logical path, never a ciphertext path.
                f.provider.mkdir('Readable folder')
                private.file_browser.navigate(f.item.data / 'Readable folder')
                self.wait(lambda: not private.file_browser.operation.busy)
                page.workspace._activate(next(dock for dock in page.workspace.docks if dock.widget() is private))
                cloned = _new_browser_tab(page.workspace)
                self.wait(lambda: not cloned.file_browser.operation.busy)
                self.assertEqual(cloned.file_browser.navigation.directory, f.item.data / 'Readable folder')
                unmapped = f.item.root / 'unmapped'
                unmapped.mkdir()
                with patch.object(qt.QMessageBox, 'warning') as warning:
                    browser.navigate(unmapped)
                    self.wait(lambda: not original._crypt_route_pending)
                    warning.assert_called_once()
            finally:
                self.wait(page.prepare_close)
                page.close()

    def test_hub_refresh_reads_local_and_crypt_folders_once_for_many_accounts(self):
        from features.rclone.ui_contributions import _get_remote_sources
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.credentials.get_loaded_credential_config_paths',
                   return_value=[f.context, *(f.root / f'account{i}.session' for i in range(7))]), \
             patch('models.folder_discovery.get_local_folders', return_value=[]) as ordinary, \
             patch.object(copy_mapping, 'connections', wraps=copy_mapping.connections) as copies:
            sources = _get_remote_sources()
            for source in sources:
                source.get_local_folders()
            ordinary.assert_called_once()
            copies.assert_called_once()

    def test_folder_sources_do_not_duplicate_the_same_encrypted_copy(self):
        from features.rclone.ui_contributions import _get_remote_sources, CopyContext
        from types import SimpleNamespace
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.credentials.get_loaded_credential_config_paths', return_value=[f.context]), \
             patch('models.folder_discovery.get_local_folders', return_value=[]) as local:
            sources = _get_remote_sources()
            self.assertEqual(len(sources), 1)
            self.assertIsInstance(sources[0].get_local_folders()[0], local_crypt.LocalCryptFolder)
            local.return_value = [SimpleNamespace(name='Secret', path=f.root / 'Local' / 'Secret')]
            sources = _get_remote_sources()
            self.assertEqual(len(sources), 2)
            self.assertIsInstance(sources[1].context, CopyContext)
            with patch('features.rclone.credentials.get_loaded_credential_config_paths', return_value=[]):
                self.assertEqual(len(_get_remote_sources()), 1)

    def test_private_browser_shared_views_render_comic_covers_in_memory(self):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from commonUtils.ui.file_browser.views import BrowserViews
        from commonUtils.ui.readers.reader_menus import RecentFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f, \
             patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary), \
             patch.object(RecentFiles, 'add', side_effect=AssertionError('Private thumbnails wrote recents')):
            view = CryptBrowserView(f.item)
            view.resize(1100, 750)
            view.show()
            browser = view.file_browser
            try:
                self.wait(lambda: not browser.busy)
                self.assertIsInstance(browser.views, BrowserViews)
                self.assertIsNone(browser.views.storage)
                self.assertEqual(set(browser.view_selector.buttons), {0, 1, 2})
                document = ComicDocument(f.item.data / 'plain.cbz', source=f.provider)
                document.save({'Title': 'Private panel metadata'})
                browser.refresh()
                self.wait(lambda: not browser.busy)
                browser.views.select_source(browser.model.browse_index(f.item.data / 'plain.cbz'))
                self.wait(lambda: browser.tabs.count() == 2 and not browser.busy)
                self.assertIn('Private panel metadata', browser.tabs.widget(1).toPlainText())
                self.assertEqual(browser.tabs.tabText(1), 'Comic Metadata')
                self.assertTrue(browser.preview_panel.isVisible())
                browser.views.select_source(browser.model.browse_index(f.item.data / 'page.png'))
                self.wait(lambda: browser.tabs.count() == 2 and browser.tabs.tabText(1) == 'Image Information' and not browser.busy)
                self.assertIn('Width: 24', browser.tabs.widget(1).toPlainText())
                self.assertIn('Height: 32', browser.tabs.widget(1).toPlainText())
                browser.view_selector.setCurrentIndex(1)
                paths = [f.item.data / name for name in ('plain.cbz', 'encrypted.cbz', 'page.png')]
                self.wait(lambda: all(path in browser.views.covers.icons for path in paths) and not browser.busy)
                self.assertTrue(all(not browser.views.covers.icons[path].isNull() for path in paths))
                self.assertFalse(browser.persistent_index)
                f.provider.mkdir('Readable folder')
                browser.refresh()
                self.wait(lambda: not browser.busy)
                browser.view_selector.setCurrentIndex(2)
                browser.views.select_source(browser.model.browse_index(f.item.data / 'Readable folder'))
                self.wait(lambda: browser.navigation.directory == f.item.data / 'Readable folder' and not browser.busy)
            finally:
                self.wait(view.prepare_close)
                self.assertEqual(len(browser.views.covers.icons), 0)
                view.close()

    def test_regular_and_private_file_passwords_retry_in_the_same_prompt(self):
        from PySide6.QtTest import QTest
        from desktop.dialogs.archive_password import ask_password, ValidatedPasswordDialog
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            for source, path in ((None, f.plain / 'encrypted.cbz'), (f.provider, f.item.data / 'encrypted.cbz')):
                state = {'phase': 0, 'checks': [], 'timeout': time.monotonic() + 10}
                timer = qt.QTimer()
                def drive():
                    dialogs = [widget for widget in self.app.topLevelWidgets()
                               if isinstance(widget, ValidatedPasswordDialog) and widget.isVisible()]
                    if not dialogs:
                        return
                    dialog = dialogs[0]
                    if time.monotonic() > state['timeout']:
                        dialog.reject()
                    elif state['phase'] == 0:
                        state['phase'] = 1
                        dialog.password.setText('wrong password')
                        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Return)
                    elif state['phase'] == 1 and dialog.error.text() and not dialog.operation.busy:
                        state['checks'] = [dialog.password.text() == '', dialog.password.hasFocus(),
                                           'Incorrect password' in dialog.error.text()]
                        state['phase'] = 2
                        dialog.password.setText('synthetic-archive-password')
                        QTest.keyClick(dialog.password, qt.Qt.Key.Key_Enter)
                timer.timeout.connect(drive)
                timer.start(10)
                try:
                    self.assertEqual(ask_password(path, 'Unlock this file.', source=source), 'synthetic-archive-password')
                    self.assertEqual(state['checks'], [True, True, True])
                finally:
                    timer.stop()
                    timer.deleteLater()

    def test_browser_markdown_and_metadata_use_memory_only_hosts(self):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        from features.comics.ui.metadata_editor import MetadataEditor
        from commonUtils.ui.readers.reader_menus import RecentFiles
        with TemporaryDirectory() as directory, crypt_fixture(directory, self.binary, pull=False) as f:
            with patch('features.rclone.localcrypt.ui.views.executable.get_rclone_path', return_value=self.binary), \
                 patch.object(RecentFiles, 'add', side_effect=AssertionError('Private reader must not persist a recent filename')):
                view = CryptBrowserView(f.item)
                self.wait(lambda: not view.file_browser.operation.busy)
                self.assertFalse(view.file_browser.persistent_index)
                self.assertEqual(view.file_browser.tree.topLevelItemCount(), 5)
                self.assertFalse(hasattr(view.file_browser, 'index_search'))
                with patch('features.rclone.localcrypt.ui.views.show_document') as present:
                    view.open_document(f.item.data / 'note.md')
                    self.wait(lambda: not view.open_operation.busy)
                window = present.call_args.args[0]
                try:
                    self.assertEqual(window.viewer.editor.toPlainText(), f.original.decode())
                    self.assertIs(window.viewer.pages.currentWidget(), window.viewer.browser)
                    self.assertFalse(window.viewer.edit_button.isChecked())
                    self.assertTrue(window.viewer.save_as_action.isEnabled())
                    self.assertTrue(window.viewer.open_action.isEnabled())
                    image = window.viewer.browser.loadResource(qt.QTextDocument.ResourceType.ImageResource,
                                                               qt.QUrl.fromLocalFile(str(f.item.data / 'page.png')))
                    self.assertFalse(image.isNull())
                    window.viewer.set_edit_mode('source')
                    window.viewer.editor.setPlainText('# Changed through private Markdown UI')
                    window.viewer.editor.document().setModified(True)
                    self.assertFalse(window.viewer.save_document())
                    self.wait(lambda: not window.viewer.storage.operation.busy)
                    self.assertEqual(f.provider.read_bytes('note.md'), b'# Changed through private Markdown UI')
                    self.assertFalse(window.viewer.is_modified)
                finally:
                    window.close()
                editor = MetadataEditor(f.item.data / 'encrypted.cbz', source=f.provider)
                try:
                    self.wait(lambda: not editor.busy)
                    self.assertIsNotNone(editor.document, editor.message.text())
                    self.assertTrue(editor.document.private)
                finally:
                    editor.close()
                    view.prepare_close()
                    self.wait(lambda: not view.open_operation.busy and not view.file_browser.operation.busy)
                    view.close()
