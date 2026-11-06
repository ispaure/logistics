"""Archive navigation, worker lifecycle, password retries and document registration."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.archives import register
from commonUtils import archives
from features.archives.ui.page import ArchivePage
from features.archives.ui.create import NewArchiveDialog
from services.documents.zip_passwords import clear_passwords


class ArchiveWorkspaceUITests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        folder = self.root / 'source'
        folder.mkdir()
        (folder / 'nested').mkdir()
        (folder / 'nested' / 'notes.txt').write_text('Nested preview')
        (folder / 'hello.txt').write_text('Hello preview')
        self.page = ArchivePage()
        self.page.resize(1200, 750)
        self.page.show()
        clear_passwords()
        self.addCleanup(clear_passwords)

    @property
    def path(self):
        path = self.root / 'sample.zip'
        if not path.exists():
            archives.create([self.root / 'source'], path)
        return path

    def wait(self):
        self.wait_until(lambda: not self.page.busy, timeout=10,
                        message=lambda: f'Archive operation did not finish: {self.page.status.text()}')

    def open(self):
        self.page.open_archive(self.path)
        self.wait()
        self.assertEqual(self.page.path, self.path)

    def test_folder_navigation_search_and_preview(self):
        self.open()
        self.assertEqual(self.page.contents.files.topLevelItemCount(), 1)
        self.page.contents._activate(self.page.contents.files.topLevelItem(0))
        self.assertEqual(self.page.contents.folder, 'source/')
        self.page.contents.search.setText('notes')
        self.wait_until(lambda: self.page.contents.files.topLevelItemCount() == 1)
        self.assertEqual(self.page.contents.files.topLevelItemCount(), 1)
        item = self.page.contents.files.topLevelItem(0)
        self.assertEqual(item.text(0), 'source/nested/notes.txt')
        item.setSelected(True)
        self.page.preview_selected()
        self.wait()
        self.assertEqual(self.page.contents.preview_text.toPlainText(), 'Nested preview')
        self.page.contents.up_folder()
        self.assertEqual(self.page.contents.folder, '')

    def test_invalid_open_keeps_current_archive_and_shows_error(self):
        self.open()
        self.page.open_archive(self.root / 'missing.zip')
        self.wait()
        self.assertEqual(self.page.path, self.path)
        self.assertIn('Operation failed', self.page.status.text())
        self.assertTrue(self.page.commands['extract'].isEnabled())

    def test_password_retry_on_gui_thread(self):
        encrypted = self.root / 'encrypted.zip'
        archives.create([self.root / 'source'], encrypted, password='secret')
        self.page.open_archive(encrypted)
        self.wait()
        answers = iter(['wrong', 'secret'])
        def prompt(*args):
            self.assertEqual(qt.QThread.currentThread(), self.app.thread())
            return next(answers)
        with patch('features.archives.ui.session.ask_password', side_effect=prompt) as ask:
            self.page.test()
            self.wait()
            self.assertEqual(ask.call_count, 2)
        self.assertIn('Integrity check passed', self.page.status.text())

    def test_password_cancel_restores_controls(self):
        encrypted = self.root / 'encrypted.zip'
        archives.create([self.root / 'source'], encrypted, password='secret')
        self.page.open_archive(encrypted)
        self.wait()
        with patch('features.archives.ui.session.ask_password', return_value=None), \
             patch('desktop.notifications.notify') as notification:
            self.page.test()
            self.wait()
        notification.assert_called_once()
        self.assertEqual(notification.call_args.kwargs['outcome'], 'cancelled')
        self.assertFalse(self.page.busy)
        self.assertTrue(self.page.commands['open'].isEnabled())
        self.assertIn('Cancelled. No output was published.', self.page.status.text())

    def test_close_cancels_active_worker(self):
        from threading import Event
        started = Event()
        def long_job(progress, cancelled, password):
            started.set()
            while not cancelled():
                time.sleep(.002)
            from commonUtils.runtime.operations import check_cancelled
            check_cancelled(cancelled)
        self.page._run('test', long_job, self.path)
        self.wait_until(started.is_set, message='Archive cancellation worker did not start')
        self.assertFalse(self.page.prepare_close())
        self.wait()
        self.assertTrue(self.page.prepare_close())
        self.assertFalse(self.page.commands['open'].isEnabled())

    def test_close_prevents_queued_password_retry_from_starting(self):
        from features.archives.ui.session import ArchiveJob
        session = self.page.session
        session._pending = ArchiveJob('test', self.path, lambda *args: None, unlock=True)
        idle = []
        session.idle.connect(lambda: idle.append(True))
        with patch('features.archives.ui.session.ask_password', return_value='secret') as prompt, \
             patch.object(session, 'start') as start:
            session._completed(None, 'Archive password required: sample.zip')
            prompt.assert_called_once()
            self.assertTrue(session.busy)
            self.assertTrue(self.page.prepare_close())
            self.wait_until(lambda: bool(idle), message='Queued archive retry did not retire after closure')
            start.assert_not_called()
        self.assertEqual(idle, [True])
        self.assertFalse(session.busy)
        self.assertFalse(self.page.commands['open'].isEnabled())

    def test_new_archive_options_and_source_deduplication(self):
        dialog = NewArchiveDialog([self.root / 'source'])
        self.addCleanup(dialog.deleteLater)
        dialog.add_sources([self.root / 'source'])
        self.assertEqual(dialog.sources.count(), 1)
        dialog.format.setCurrentIndex(1)
        self.assertFalse(dialog.encrypt.isEnabled())
        dialog.output.setText(str(self.root / 'new.tar.gz'))
        dialog._accept()
        options = dialog.options()
        self.assertEqual(options['format'], 'tar.gz')
        self.assertEqual(options['sources'], [self.root / 'source'])
        self.assertIsNone(options['password'])

    def test_tar_disables_zip_editing(self):
        tar = self.root / 'sample.tar.gz'
        archives.create([self.root / 'source'], tar, format='tar.gz')
        self.page.open_archive(tar)
        self.wait()
        self.assertFalse(self.page.edit_menu.isEnabled())
        self.assertTrue(self.page.commands['extract'].isEnabled())

    def test_empty_archive_and_welcome_state(self):
        self.assertFalse(self.page.contents.files.isVisible())
        self.assertTrue(self.page.contents.empty.isVisible())
        empty = self.root / 'empty.zip'
        import zipfile
        with zipfile.ZipFile(empty, 'w'):
            pass
        self.page.open_archive(empty)
        self.wait()
        self.assertEqual(self.page.contents.files.topLevelItemCount(), 0)
        self.assertFalse(self.page.contents.empty.isVisible())
        self.assertTrue(self.page.contents.files.isVisible())

    def test_image_preview_displays_and_does_not_force_large_panel(self):
        from io import BytesIO
        from PIL import Image
        from commonUtils.archives.zip_access import open_archive
        image = BytesIO()
        Image.new('RGB', (1600, 900), 'orange').save(image, 'PNG')
        path = self.root / 'image.zip'
        with open_archive(path, 'w') as archive:
            archive.writestr('picture.png', image.getvalue())
        self.page.open_archive(path)
        self.wait()
        self.page.contents.files.topLevelItem(0).setSelected(True)
        self.page.preview_selected()
        self.wait()
        self.assertTrue(self.page.contents.image_scroll.isVisible())
        self.assertFalse(self.page.contents.preview_text.isVisible())
        self.assertLess(self.page.contents.preview_panel.width(), 600)
        self.assertFalse(self.page.contents.preview_image.pixmap().isNull())

    def test_edit_keeps_verified_password_in_session_for_next_action(self):
        from commonUtils.archives.zip_access import open_archive
        encrypted = self.root / 'encrypted.zip'
        archives.create([self.root / 'source'], encrypted, password='secret')
        original = encrypted.read_bytes()
        self.page.open_archive(encrypted)
        self.wait()
        extra = self.root / 'extra.txt'
        extra.write_text('new')
        with patch('features.archives.ui.session.ask_password', return_value='secret') as ask:
            opened = []
            self.page.session.completed.connect(lambda kind, *args: opened.append(kind) if kind == 'open' else None)
            self.page._edit(sources=[extra])
            self.wait_until(lambda: bool(opened) and not self.page.busy, timeout=10,
                            message='Edited archive did not finish its queued refresh')
            self.assertNotEqual(encrypted.read_bytes(), original)
            with open_archive(encrypted, password='secret') as archive:
                self.assertEqual(archive.read('extra.txt'), b'new')
                self.assertEqual(archive.read('source/hello.txt'), b'Hello preview')
            self.assertIn('extra.txt', [self.page.contents.files.topLevelItem(i).text(0)
                                       for i in range(self.page.contents.files.topLevelItemCount())])
            self.page.test()
            self.wait()
            self.assertEqual(ask.call_count, 1)
        self.assertIn('Integrity check passed', self.page.status.text())

    def test_standalone_window_waits_for_its_worker_before_deletion(self):
        from features.archives.ui.window import ArchiveWindow, _windows
        from threading import Event
        window = ArchiveWindow()
        window.show()
        started = Event()
        def long_job(progress, cancelled, password):
            started.set()
            while not cancelled():
                time.sleep(.002)
            from commonUtils.runtime.operations import check_cancelled
            check_cancelled(cancelled)
        window.page._run('test', long_job, self.path)
        self.wait_until(started.is_set, message='Standalone archive worker did not start')
        self.assertFalse(window.close())
        self.wait_until(lambda: window not in _windows, drain_deferred=True,
                        message='Closed archive window outlived its worker')

    def test_browser_action_opens_retained_archive_document(self):
        from features.archives import _manage
        from commonUtils.ui.features import ActionContext
        from commonUtils.filesystem.files import File
        from features.archives.ui.window import _windows
        host = qt.QWidget()
        self.addCleanup(host.deleteLater)
        context = ActionContext(host, host, None, (File(self.path),))
        _manage(context)
        window = next(window for window in _windows if not window.page.closing)
        self.addCleanup(window.close)
        self.wait_until(lambda: window.page.path == self.path and not window.page.busy,
                        message='Browser action did not finish opening its archive')
        self.assertEqual(window.page.path, self.path)
        _manage(context)
        self.assertEqual(len([view for view in _windows if not view.page.closing]), 1)

    def test_standalone_window_reuses_only_its_current_archive(self):
        from features.archives.ui.window import open_archive_window

        first = self.path
        second = self.root / 'other.zip'
        archives.create([self.root / 'source'], second)
        window = open_archive_window(first)
        self.assertIs(open_archive_window(first), window)
        self.wait_until(lambda: not window.page.busy)
        self.assertEqual(window.page.path, first)

        window.page.open_archive(second)
        self.wait_until(lambda: not window.page.busy)
        self.assertEqual(window.page.path, second)

        reopened = open_archive_window(first)
        self.assertIsNot(reopened, window)
        self.wait_until(lambda: not reopened.page.busy)
        self.assertEqual(reopened.page.path, first)
        self.assertIs(open_archive_window(second), window)
        self.assertIs(open_archive_window(first), reopened)


class ArchiveDeclarationTests(unittest.TestCase):
    def test_archive_contributes_document_launcher(self):
        declaration = register()
        self.assertEqual(declaration.pages, [])
        self.assertEqual(declaration.document_launchers[0].editor_id, 'archive')
        self.assertEqual(declaration.document_launchers[0].icon, 'archives')
