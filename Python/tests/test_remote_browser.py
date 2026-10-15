"""Real CLI remote reads against synthetic local and crypt backends."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from commonUtils.runtime.resource_provider import capabilities
from features.rclone import executable, session
from features.rclone.remote_resources import RemoteResources
from features.rclone.remote_policy import direct_kind, LocalCopyRequired
from local_crypt_fixture import crypt_fixture


class RemoteBrowserTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.binary = executable.get_rclone_path()
        if not cls.binary.is_file():
            raise unittest.SkipTest('Pinned rclone is not installed')

    def test_account_isolation_range_reads_and_revocation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            providers = []
            for index in range(2):
                data = root / str(index)
                data.mkdir()
                (data / 'note.txt').write_text(f'account {index}')
                context = root / f'{index}.session'
                session.remember(context, {'SameName': {'type': 'alias', 'remote': str(data)}})
                self.addCleanup(session.forget, context)
                provider = RemoteResources(context, 'SameName', binary=self.binary)
                providers.append(provider)
                self.addCleanup(provider.close)
                self.assertEqual(provider.list()[0]['name'], 'note.txt')
                with provider.open('note.txt') as stream:
                    stream.seek(8)
                    self.assertEqual(stream.read(), str(index).encode())
                self.assertFalse(capabilities(provider).replace)
            self.assertNotEqual(providers[0].root, providers[1].root)
            provider = providers[0]
            self.assertFalse(hasattr(provider, 'download'))
            with provider.open('note.txt') as stream:
                session.forget(provider.config_path)
                with self.assertRaisesRegex(ValueError, 'Credentials'):
                    stream.read(1)

    def test_crypt_direct_reads(self):
        with TemporaryDirectory() as folder, crypt_fixture(folder, self.binary) as fixture:
            provider = RemoteResources(fixture.context, 'Secret', binary=self.binary)
            self.addCleanup(provider.close)
            self.assertEqual(provider.read_bytes('note.md'), fixture.original)
            from features.comics.library import ComicDocument
            from features.comics.pages import ComicPages
            comic = ComicDocument(provider.root / 'plain.cbz', source=provider)
            self.assertEqual(ComicPages(comic.path, comic).read_page(0)[0], fixture.image)
    def test_nested_encrypted_folder_navigation(self):
        from commonUtils.integrations.wrappers.cmdShellWrapper.binary import run_bytes
        with TemporaryDirectory() as folder, crypt_fixture(folder, self.binary) as fixture:
            nested = fixture.plain / 'nested/subfolder'
            nested.mkdir(parents=True)
            (nested / 'note.txt').write_bytes(b'nested plaintext sentinel')
            env, source, dest = session.launch(fixture.context, str(fixture.plain / 'nested'), 'Secret:nested')
            run_bytes([str(self.binary), '--config', session.NULL_CONFIG, 'copy', str(source), str(dest)], environment=env)
            provider = RemoteResources(fixture.context, 'Secret', binary=self.binary)
            self.addCleanup(provider.close)
            self.assertEqual(provider.list('nested')[0]['name'], 'subfolder')
            self.assertEqual(provider.read_bytes('nested/subfolder/note.txt'), b'nested plaintext sentinel')

    def test_tab_duplication_current_folder_filter_and_read_only_text(self):
        from ui_new.file_browser import FileBrowserWindow, _new_browser_tab
        from features.rclone.ui.remote_browser import RemoteLocation
        with self.temporary_directory() as folder:
            data = Path(folder) / 'files'
            data.mkdir()
            (data / 'note.txt').write_text('read only')
            (data / 'nested').mkdir()
            (data / 'nested/deep.txt').write_text('hidden from current-folder search')
            context = Path(folder) / 'account.session'
            session.remember(context, {'Files': {'type': 'alias', 'remote': str(data)}})
            self.addCleanup(session.forget, context)
            with patch.object(executable, 'ensure_rclone', return_value=self.binary):
                window = FileBrowserWindow(RemoteLocation(context, 'Files'))
                view = window.workspace.active_view
                self.app = qt.QApplication.instance()
                self.wait_until(lambda: not view.file_browser.busy, timeout=15)
                self.assertFalse(view.file_browser.persistent_index)
                browser = view.file_browser
                with patch.object(view.provider, 'list', wraps=view.provider.list) as listing:
                    browser.filter.setText('deep')
                    self.app.processEvents()
                    self.assertFalse(browser.search_pending)
                    self.assertFalse(browser.search_operation.busy)
                    self.assertEqual(listing.call_count, 0)
                view.open_document(view.provider.root / 'note.txt')
                self.wait_until(lambda: not view.operation.busy, timeout=15)
                text = next(widget for widget in qt.QApplication.topLevelWidgets()
                            if isinstance(widget, qt.QMainWindow) and isinstance(widget.centralWidget(), qt.QPlainTextEdit))
                self.assertTrue(text.centralWidget().isReadOnly())
                self.assertEqual(text.centralWidget().toPlainText(), 'read only')
                text.close()
                duplicate = _new_browser_tab(window.workspace)
                self.assertEqual(duplicate.location, view.location)
                self.assertNotEqual(duplicate.provider.context, view.provider.context)
                self.wait_until(lambda: not duplicate.file_browser.busy, timeout=15)

    def test_unsupported_and_oversize_files_require_manual_copy(self):
        for name, size in [('movie.mp4', 30), ('large.txt', 2*1024*1024), ('photo.png', 20*1024*1024)]:
            with self.assertRaises(LocalCopyRequired):
                direct_kind(name, size)
        self.assertEqual(direct_kind('large.cbz', 1024**3), 'archive')

    def test_forgetting_saved_config_revokes_its_in_memory_snapshot(self):
        from features.rclone import configuration
        with TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'account.conf'
            config.write_text(f'[Files]\ntype=alias\nremote={root}\n')
            provider = RemoteResources(config, 'Files', binary=self.binary)
            self.addCleanup(provider.close)
            self.assertIsNotNone(session.credentials(provider.context))
            self.assertTrue(configuration.delete_config_file(config))
            self.assertIsNone(session.credentials(provider.context))
            with self.assertRaisesRegex(ValueError, 'Credentials'):
                provider.list()

    def test_desktop_preview_only_actions_and_manual_copy_dialog(self):
        from ui_new.file_browser import FileBrowserWindow
        from features.rclone.ui.remote_browser import RemoteLocation
        from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
        with self.temporary_directory() as folder:
            root = Path(folder)
            source, copies = root / 'source', root / 'copies'
            source.mkdir()
            copies.mkdir()
            (source / 'note.txt').write_text('Explicit local copy')
            (source / 'unsupported.bin').write_bytes(b'unsupported')
            (source / 'empty').mkdir()
            context = root / 'account.session'
            session.remember(context, {'Files': {'type': 'alias', 'remote': str(source)}})
            self.addCleanup(session.forget, context)
            with patch.object(executable, 'ensure_rclone', return_value=self.binary):
                window = FileBrowserWindow(RemoteLocation(context, 'Files'))
                window.show()
                view = window.workspace.active_view
                self.wait_until(lambda: not view.file_browser.busy, timeout=15)
                self.assertFalse(hasattr(view, 'download'))
                self.assertFalse(hasattr(view.provider, 'download'))
                menu = view.menuBar().actions()[0].menu()
                self.assertEqual([action.text() for action in menu.actions()], ['Open Remote…'])
                with patch.object(qt.QMessageBox, 'information') as dialog:
                    view.open_document(view.provider.root / 'unsupported.bin')
                    self.wait_until(lambda: not view.operation.busy, timeout=15)
                    self.assertEqual(dialog.call_args.args[2], LOCAL_COPY_MESSAGE)
                    self.assertEqual(list(copies.iterdir()), [])
                capture = os.environ.get('LOGISTICS_REMOTE_CAPTURE')
                if capture:
                    window.grab().save(capture)

    def test_real_reader_menus_corrupt_files_and_recovery(self):
        from ui_new.file_browser import FileBrowserWindow
        from features.rclone.ui.remote_browser import RemoteLocation
        from features.books.reader import BookWindow
        from features.comics.ui.reader import ComicReaderWindow
        from books_fixture import make_book
        from io import BytesIO
        from zipfile import ZipFile
        from PIL import Image
        from features.rclone.remote_policy import LOCAL_COPY_MESSAGE
        with self.temporary_directory() as folder:
            root = Path(folder)
            source = root / 'remote'
            source.mkdir()
            make_book(source / 'book.epub')
            image = BytesIO()
            Image.new('RGB', (20, 30), 'blue').save(image, 'PNG')
            (source / 'page.png').write_bytes(image.getvalue())
            (source / 'note.txt').write_text('Remote text')
            (source / 'large.txt').write_bytes(b'x' * (1024 * 1024 + 1))
            for name in ('broken.png', 'broken.cbz', 'broken.epub'):
                (source / name).write_bytes(b'Invalid document')
            with ZipFile(source / 'comic.cbz', 'w') as archive:
                archive.writestr('page.png', image.getvalue())
            context = root / 'account.session'
            session.remember(context, {'Files': {'type': 'alias', 'remote': str(source)}})
            self.addCleanup(session.forget, context)
            with patch.object(executable, 'ensure_rclone', return_value=self.binary):
                window = FileBrowserWindow(RemoteLocation(context, 'Files'))
                window.show()
                view = window.workspace.active_view
                self.wait_until(lambda: not view.file_browser.busy, timeout=15)
                self.assertEqual(view.file_browser.actions, ())
                for name, expected in [('book.epub', BookWindow), ('comic.cbz', ComicReaderWindow)]:
                    before = set(qt.QApplication.topLevelWidgets())
                    view.open_document(view.provider.root / name)
                    reader = next(widget for widget in qt.QApplication.topLevelWidgets()
                                  if widget not in before and isinstance(widget, expected))
                    if name == 'book.epub':
                        page = reader.reader
                        self.assertFalse(page.menus.metadata_action.isVisible())
                        self.assertTrue(page.metadata_button.isHidden())
                    else:
                        self.assertFalse(reader.edit_metadata_action.isVisible())
                    reader.close()
                    qt.QApplication.instance().processEvents()
                with patch.object(qt.QMessageBox, 'information') as info, patch.object(qt.QMessageBox, 'warning') as warning:
                    for name in ('large.txt', 'broken.png', 'broken.cbz', 'broken.epub', 'missing.txt'):
                        info.reset_mock()
                        warning.reset_mock()
                        view.open_document(view.provider.root / name)
                        self.wait_until(lambda: not view.operation.busy, timeout=15)
                        dialog = warning if warning.called else info
                        self.assertTrue(dialog.called, name)
                        self.assertIn(LOCAL_COPY_MESSAGE, dialog.call_args.args[2], name)
                view.open_document(view.provider.root / 'note.txt')
                self.wait_until(lambda: not view.operation.busy, timeout=15)
                text = next(widget for widget in qt.QApplication.topLevelWidgets()
                            if isinstance(widget, qt.QMainWindow) and isinstance(widget.centralWidget(), qt.QPlainTextEdit))
                self.assertEqual(text.centralWidget().toPlainText(), 'Remote text')
                self.assertTrue(text.centralWidget().isReadOnly())
                text.close()


if __name__ == '__main__':
    unittest.main()
