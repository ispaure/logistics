"""Password prompts stay interactive; configured archive creation avoids prompts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.zip_access import archive_manifest, open_archive
from services.zip_passwords import clear_passwords
from features.archives.ui.create_zip import CreateZipDialog


class ArchivePasswordUITests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        clear_passwords()
        self.addCleanup(clear_passwords)

    def wait(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.01)
        self.app.processEvents()

    def test_creation_uses_config_and_keeps_source(self):
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password = test-only\n')
        source = self.root / 'source.txt'
        source.write_text('original')
        dialog = CreateZipDialog([source])
        self.addCleanup(dialog.deleteLater)
        dialog._create()
        self.wait(dialog)
        self.assertTrue(dialog.succeeded)
        self.assertEqual(source.read_text(), 'original')
        self.assertIn('source.txt', archive_manifest(Path(dialog.output.text()), password='test-only'))

    def test_mixed_password_creation_fails_without_output_or_prompt(self):
        sources = []
        for name in ('one', 'two'):
            folder = self.root / name
            folder.mkdir()
            (folder / 'remoteConfig.ini').write_text(f'[LogisticsZIP]\narchive_password = test-{name}\n')
            source = folder / f'{name}.txt'
            source.write_text(name)
            sources.append(source)
        dialog = CreateZipDialog(sources)
        self.addCleanup(dialog.deleteLater)
        with patch('ui_new.dialogs.archive_password.ask_password', side_effect=AssertionError('Unexpected prompt')):
            dialog._create()
            self.wait(dialog)
        self.assertFalse(dialog.succeeded)
        self.assertIn('different configured passwords', dialog.message.text())
        self.assertFalse(Path(dialog.output.text()).exists())

    def test_reader_retries_password_on_gui_thread_then_cancel_is_safe(self):
        from features.comics import reader
        from features.comics.pages import ComicPages
        source = self.root / 'comic.cbz'
        with open_archive(source, 'w', password='test-only') as archive:
            archive.writestr('ComicInfo.xml', '<ComicInfo/>')
            archive.writestr('1.png', b'page payload')
        before = source.read_bytes()
        def prompt(*args):
            self.assertEqual(qt.QThread.currentThread(), self.app.thread())
            return next(answers)
        answers = iter(['wrong-test', 'test-only'])
        with patch.object(reader, 'ask_password', side_effect=prompt) as ask, patch.object(reader, 'ComicReaderWindow') as window:
            opened = reader.open_reader(source)
            self.assertEqual(ask.call_count, 2)
            pages = window.call_args.args[0]
            self.assertIsInstance(pages, ComicPages)
            self.assertEqual(pages.read_page(0)[0], b'page payload')
            reader._windows.remove(opened)
        clear_passwords()
        with patch.object(reader, 'ask_password', return_value=None):
            self.assertIsNone(reader.open_reader(source))
        self.assertEqual(source.read_bytes(), before)

    def test_single_metadata_editor_prompts_then_saves_with_session_password(self):
        from features.comics.ui.metadata_editor import MetadataEditor
        from features.comics.library import ComicDocument
        source = self.root / 'comic.cbz'
        with open_archive(source, 'w', password='test-only') as archive:
            archive.writestr('ComicInfo.xml', '<ComicInfo><Writer>Old</Writer></ComicInfo>')
            archive.writestr('1.png', b'unchanged page')
        def prompt(*args):
            self.assertEqual(qt.QThread.currentThread(), self.app.thread())
            return 'test-only'
        with patch('features.comics.ui.metadata_editor.ask_password', side_effect=prompt) as ask:
            editor = MetadataEditor(source)
            self.addCleanup(editor.deleteLater)
            self.wait(editor)
            self.assertEqual(ask.call_count, 1)
            self.assertIsNotNone(editor.selection)
            editor.editors['Writer'].setText('Edited')
            editor._save()
            self.wait(editor)
        self.assertEqual(ComicDocument(source).info.get_field('Writer'), 'Edited')
        with open_archive(source, password='test-only') as archive:
            self.assertEqual(archive.read('1.png'), b'unchanged page')
        editor.reject()

    def test_adjacent_reader_unlock_retry_preserves_current_comic_on_cancel(self):
        from io import BytesIO
        from PIL import Image
        from features.comics.pages import ComicPages
        from features.comics.ui.reader import ComicReaderWindow
        image = BytesIO()
        Image.new('RGB', (20, 30), 'orange').save(image, 'PNG')
        first, second = self.root / 'first.cbz', self.root / 'second.cbz'
        for path, password in ((first, None), (second, 'test-only')):
            with open_archive(path, 'w', password=password) as archive:
                archive.writestr('1.png', image.getvalue())
        reader = ComicReaderWindow(ComicPages(first))
        self.wait(reader)
        with patch('features.comics.ui.reader.ask_password', return_value=None) as ask:
            reader._request_file(second)
            self.wait(reader)
            ask.assert_called_once()
        self.assertEqual(reader.pages.path, first)
        self.assertFalse(reader.busy)
        with patch('features.comics.ui.reader.ask_password', side_effect=['wrong-test', 'test-only']) as ask:
            reader._request_file(second)
            self.wait(reader)
            self.assertEqual(ask.call_count, 2)
        self.assertEqual(reader.pages.path, second)
        self.assertEqual(reader.shown_page, 0)
        reader.close()
        self.app.processEvents()

    def test_browser_worker_password_retry_runs_on_gui_thread(self):
        from unittest.mock import MagicMock
        from features.comics.ui.browser_extension import ComicBrowserExtension
        source = self.root / 'comic.cbz'
        with open_archive(source, 'w', password='test-only') as archive:
            archive.writestr('1.png', b'page payload')
        host = qt.QWidget()
        host.file_browser = MagicMock()
        controller = ComicBrowserExtension(host)
        self.addCleanup(host.deleteLater)
        answers = iter(['wrong-test', 'test-only'])
        def prompt(*args):
            self.assertEqual(qt.QThread.currentThread(), self.app.thread())
            return next(answers)
        with patch('features.comics.ui.browser_services.ask_password', side_effect=prompt) as ask, patch('features.comics.ui.browser_services.open_reader', return_value=None) as opened:
            controller._read(source)
            deadline = time.monotonic() + 5
            while not opened.called or controller.reader_busy:
                self.assertLess(time.monotonic(), deadline)
                self.app.processEvents()
                time.sleep(.01)
            self.assertEqual(ask.call_count, 2)
            self.assertEqual(opened.call_args.args[0].read_page(0)[0], b'page payload')
        host.file_browser.refresh_item.assert_called_once_with(source)

    def test_queued_password_retry_does_not_restart_after_browser_close(self):
        from unittest.mock import MagicMock
        from features.comics.ui.browser_extension import ComicBrowserExtension
        host = qt.QWidget()
        host.file_browser = MagicMock()
        self.addCleanup(host.deleteLater)
        controller = ComicBrowserExtension(host)
        controller.reader_busy = True
        controller.reader_operation = MagicMock()
        controller._reader_password_retry = (self.root / 'comic.cbz', 'test-only')
        with patch('features.comics.ui.browser_services.Operation') as operation:
            controller._reader_finished()
            self.assertTrue(controller.prepare_close())
            self.app.processEvents()
            operation.assert_not_called()
            self.assertFalse(controller.reader_busy)
