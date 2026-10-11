"""Retain real Qt owners through background failures and cancellation."""
import threading
from time import monotonic, sleep
from pathlib import Path
from tempfile import TemporaryDirectory
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.smart_home.ui.page import SmartHomePage
from features.dropbox.ui.dialogs import DropboxConflictsDialog
from features.media.ui.dialogs import RenameMkaDialog
from features.media import mka


class IntegrationWorkerTests(QtTestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = qt.QApplication.instance() or qt.QApplication([])

    def until(self, condition):
        deadline = monotonic() + 10
        while not condition():
            self.assertLess(monotonic(), deadline)
            self.app.processEvents()
            sleep(.005)

    def test_hue_failure_is_off_gui_thread_and_close_waits(self):
        page = SmartHomePage()
        started, release = threading.Event(), threading.Event()
        threads = []
        def bridge():
            threads.append(qt.QThread.currentThread())
            started.set()
            release.wait(5)
            raise OSError('bridge unavailable')
        try:
            page._run(bridge)
            self.until(started.is_set)
            self.assertNotEqual(threads[0], self.app.thread())
            self.assertFalse(page.prepare_close())
            self.assertFalse(page.connect_button.isEnabled())
        finally:
            release.set()
            self.until(lambda: not page.task.busy)
        self.assertTrue(page.prepare_close())
        self.assertTrue(page.connect_button.isEnabled())
        self.assertIn('bridge unavailable', page.task.message.text())
        page.close()

    def test_review_dialogs_show_names_and_allow_a_new_folder(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'Chapter_01.mka').write_bytes(b'audio')
            (path / 'chapters.csv').write_text('1,Introduction\n')
            rename = RenameMkaDialog(path)
            rename._reviewed(mka.plan_from_csv(path))
            self.assertEqual(rename.results.topLevelItem(0).text(1), '1 - Introduction.mka')
            rename.close()
            dropbox = DropboxConflictsDialog(path)
            dropbox._reviewed(())
            self.assertFalse(dropbox.action_button.isEnabled())
            dropbox.target_dir.setText(str(path / 'other'))
            self.assertTrue(dropbox.action_button.isEnabled())
            dropbox.close()
