"""Archive navigation, worker lifecycle, password retries and sidebar placement."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.archives import register, backend
from features.archives.ui.page import ArchivePage
from features.archives.ui.create import NewArchiveDialog
from services.zip_passwords import clear_passwords


class ArchiveWorkspaceUITests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        folder = self.root / 'source'
        folder.mkdir()
        (folder / 'nested').mkdir()
        (folder / 'nested' / 'notes.txt').write_text('Nested preview')
        (folder / 'hello.txt').write_text('Hello preview')
        self.path = self.root / 'sample.zip'
        backend.create([folder], self.path)
        self.page = ArchivePage()
        self.page.resize(1200, 750)
        self.page.show()
        self.addCleanup(self.page.deleteLater)
        clear_passwords()
        self.addCleanup(clear_passwords)

    def wait(self):
        deadline = time.monotonic() + 10
        while self.page.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()

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
        backend.create([self.root / 'source'], encrypted, password='secret')
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
        backend.create([self.root / 'source'], encrypted, password='secret')
        self.page.open_archive(encrypted)
        self.wait()
        with patch('features.archives.ui.session.ask_password', return_value=None):
            self.page.test()
            self.wait()
        self.assertFalse(self.page.busy)
        self.assertTrue(self.page.commands['open'].isEnabled())

    def test_close_cancels_worker_and_prevents_queued_retry(self):
        from threading import Event
        started = Event()
        def long_job(progress, cancelled, password):
            started.set()
            while not cancelled():
                time.sleep(.002)
            from commonUtils.operations import check_cancelled
            check_cancelled(cancelled)
        self.page._run('test', long_job, self.path)
        self.assertTrue(started.wait(1))
        self.assertFalse(self.page.prepare_close())
        self.wait()
        self.assertTrue(self.page.prepare_close())
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

    def test_navigation_position_between_sync_and_git(self):
        from ui_new.sidebar import DestinationRail
        documents = qt.QWidget()
        documents.count = 0
        documents.records = {}
        rail = DestinationRail(documents)
        self.addCleanup(rail.deleteLater)
        tabs = qt.QTabWidget()
        self.addCleanup(tabs.deleteLater)
        git = qt.QWidget()
        git.setProperty('navigation_icon', 'git')
        git.setProperty('navigation_position', 'workspace')
        git.setProperty('navigation_order', 20)
        self.page.setProperty('navigation_icon', 'archives')
        tabs.addTab(git, 'Git')
        tabs.addTab(self.page, 'Archives')
        rail.refresh(tabs, [])
        buttons = [rail.workspace_destinations.itemAt(i).widget().text() for i in range(rail.workspace_destinations.count())]
        self.assertEqual(buttons, ['Archives', 'Git'])
        outer = rail.layout()
        sync_index = next(i for i in range(outer.count()) if outer.itemAt(i).widget() is rail.buttons['actions'])
        workspace_index = next(i for i in range(outer.count()) if outer.itemAt(i).layout() is rail.workspace_destinations)
        self.assertLess(sync_index, workspace_index)
        self.assertEqual(register().pages[0].navigation_icon, 'archives')

    def test_tar_disables_zip_editing(self):
        tar = self.root / 'sample.tar.gz'
        backend.create([self.root / 'source'], tar, format='tar.gz')
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
        from commonUtils.zip_access import open_archive
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
        encrypted = self.root / 'encrypted.zip'
        backend.create([self.root / 'source'], encrypted, password='secret')
        self.page.open_archive(encrypted)
        self.wait()
        extra = self.root / 'extra.txt'
        extra.write_text('new')
        with patch('features.archives.ui.session.ask_password', return_value='secret') as ask:
            self.page._edit(sources=[extra])
            self.wait()
            # Complete the queued refresh after successful editing.
            self.wait()
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
            from commonUtils.operations import check_cancelled
            check_cancelled(cancelled)
        window.page._run('test', long_job, self.path)
        self.assertTrue(started.wait(1))
        self.assertFalse(window.close())
        deadline = time.monotonic() + 5
        while window in _windows:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            self.app.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            time.sleep(.005)

    def test_browser_action_reuses_main_workspace(self):
        from features.archives import _manage
        from commonUtils.features import ActionContext
        from commonUtils.fileUtils import File
        host = qt.QWidget()
        tabs = qt.QTabWidget(host)
        tabs.addTab(qt.QWidget(), 'Browser')
        tabs.addTab(self.page, 'Archives')
        context = ActionContext(host, host, None, (File(self.path),))
        self.addCleanup(host.deleteLater)
        _manage(context)
        self.wait()
        self.assertIs(tabs.currentWidget(), self.page)
        self.assertEqual(self.page.path, self.path)
