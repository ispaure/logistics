"""Downloads remain responsive, retain failures and cancel before closing."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from unittest.mock import patch

from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.youtube_downloader import downloader
from features.youtube_downloader.ui.dialog import YouTubeDownloaderDialog
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


class DownloaderWorkerTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root/'Configs').mkdir()
        (root/'remoteConfig.ini').write_text('[Youtube-Download]\nconfig_sub_path=Configs\n')
        with patch('features.registry.is_feature_enabled', return_value=False):
            self.dialog = YouTubeDownloaderDialog(FolderEntry('Videos', local=LocalFolder(root)))
        self.dialog.show()
        self.addCleanup(self.dialog.deleteLater)

    def until(self, condition):
        deadline = monotonic() + 5
        while not condition():
            self.assertLess(monotonic(), deadline)
            self.app.processEvents(); sleep(.005)

    def test_download_runs_off_gui_thread_and_reject_waits_for_cancellation(self):
        entered = Event()
        def download(path, *, report, cancelled):
            self.assertNotEqual(qt.QThread.currentThread(), self.app.thread())
            entered.set()
            deadline = monotonic() + 5
            while not cancelled() and monotonic() < deadline:
                sleep(.005)
            return False
        with patch.object(downloader, 'download_all', side_effect=download):
            self.dialog._download_all()
            self.until(entered.is_set)
            ticks = []
            qt.QTimer.singleShot(0, lambda: ticks.append(True))
            self.until(lambda: bool(ticks))
            self.dialog.reject()
            self.assertTrue(self.dialog.progress.busy)
            self.assertTrue(self.dialog.isVisible())
            self.until(lambda: not self.dialog.progress.busy)
            self.assertFalse(self.dialog.isVisible())

    def test_failed_batch_is_visible_and_button_availability_is_restored(self):
        states = [button.isEnabled() for button in self.dialog._buttons]
        with patch.object(downloader, 'download_all', return_value=False):
            self.dialog._download_all()
            self.until(lambda: not self.dialog.progress.busy)
        self.assertIn('failed', self.dialog.progress.message.text().lower())
        self.assertEqual([button.isEnabled() for button in self.dialog._buttons], states)
        self.assertTrue(self.dialog.isVisible())
