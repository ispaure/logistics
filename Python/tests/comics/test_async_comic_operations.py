"""Cancellation preserves ZIP sources and finishes the current comic transaction."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from threading import Event
import time
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.archives.zip_access import open_archive, archive_manifest, is_encrypted
from commonUtils.runtime.operations import BatchResult
from features.comics import cbz, archive_io
from features.comics.ui.dialogs import CompressCbzDialog, ComicAuthorDialog, ComicSeriesDialog, ConvertCbrDialog, CbzIndividualFoldersDialog
from tests.comics.fixtures import encoded_page


class AsyncComicTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)

    def wait(self, dialog):
        self.wait_until(lambda: not dialog.busy)

    def comic(self, name, password=None):
        path = self.root / name
        with open_archive(path, 'w', password=password) as archive:
            archive.writestr('01.png', encoded_page(size=(40, 60)))
        return path


    def test_compression_cancel_during_zip_build_finishes_encrypted_comic(self):
        password = 'test-only'
        (self.root / 'remoteConfig.ini').write_text(f'[LogisticsZIP]\narchive_password={password}\n')
        first, second = self.comic('first.cbz', password), self.comic('second.cbz', password)
        original_second = second.read_bytes()
        cancel = Event()
        real_zip = archive_io.zipUtils.zip_file
        def build(*args, **kwargs):
            cancel.set()  # User cancellation while the current comic's ZIP is being built.
            return real_zip(*args, **kwargs)
        with patch.object(archive_io.zipUtils, 'zip_file', side_effect=build):
            stats = cbz.compress_selected_cbz([first, second], always_keep_compressed=True,
                                            cancelled=cancel.is_set)
        self.assertTrue(stats.cancelled)
        self.assertEqual(stats.compressed_file_count, 1)
        self.assertEqual(stats.error_during_compression, 0)
        self.assertEqual(stats.remaining, [second])
        self.assertTrue(is_encrypted(first))
        self.assertIn('CompressionLog.txt', archive_manifest(first, password=password))
        self.assertEqual(second.read_bytes(), original_second)
        self.assertFalse(list(self.root.glob('.logistics-comic-*')))

    def test_failure_during_cancelled_comic_keeps_original_and_reports_failure(self):
        first, second = self.comic('first.cbz'), self.comic('second.cbz')
        before = [first.read_bytes(), second.read_bytes()]
        cancel = Event()
        def fail(*args, **kwargs):
            cancel.set()
            raise OSError('simulated ZIP write failure')
        with patch.object(archive_io.zipUtils, 'zip_file', side_effect=fail):
            stats = cbz.compress_selected_cbz([first, second], cancelled=cancel.is_set)
        self.assertTrue(stats.cancelled)
        self.assertEqual(stats.error_during_compression, 1)
        self.assertEqual(stats.compressed_file_count, 0)
        self.assertIn('simulated ZIP write failure', stats.failed[first])
        self.assertEqual(stats.remaining, [second])
        self.assertEqual([first.read_bytes(), second.read_bytes()], before)

    def test_compression_dialog_stays_responsive_and_close_requests_cancellation(self):
        first, second = self.comic('first.cbz'), self.comic('second.cbz')
        entered, release = Event(), Event()
        dialog = CompressCbzDialog(targets=[first, second])
        self.addCleanup(dialog.deleteLater)
        ticks = []
        timer = qt.QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(1)
        real_compress = cbz.CBZFile.compress_to_webp
        def compress(comic, **options):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release comic')
            return real_compress(comic, **options)
        with patch.object(dialog, '_confirm', return_value=True), patch.object(cbz.CBZFile, 'compress_to_webp', compress):
            dialog._execute()
            try:
                deadline = time.monotonic() + 5
                while not entered.is_set() or len(ticks) < 3:
                    self.assertLess(time.monotonic(), deadline)
                    self.app.processEvents()
                    time.sleep(.005)
                dialog.close()
                self.assertTrue(dialog.busy)
                self.assertTrue(dialog.task.cancelled.is_set())
                self.assertFalse(dialog.action_button.isEnabled())
            finally:
                release.set()
                self.wait(dialog)
                timer.stop()
        self.assertIn('Cancelled.', dialog.task.message.text())
        self.assertIn('1 not processed', dialog.task.message.text())
        self.assertTrue(cbz.CBZFile(first).is_already_compressed())
        self.assertFalse(cbz.CBZFile(second).is_already_compressed())


    def test_other_comic_tools_capture_inputs_and_run_on_worker_threads(self):
        cases = [(ConvertCbrDialog, 'features.comics.conversion.dir_batch_convert_cbr_to_cbz'),
                 (ComicAuthorDialog, 'features.comics.metadata.batch_rename_author_to_dir_name'),
                 (ComicSeriesDialog, 'features.comics.metadata.batch_rename_series_to_dir_name'),
                 (CbzIndividualFoldersDialog, 'features.comics.actions.move_cbz_to_individual_folders')]
        for cls, function in cases:
            with self.subTest(dialog=cls.__name__):
                dialog = cls(initial_path=self.root)
                def work(*args, progress, cancelled, report, **kwargs):
                    self.assertNotEqual(qt.QThread.currentThread(), self.app.thread())
                    self.assertTrue(report)
                    progress(1, 1, 'Completed test operation')
                    return BatchResult(completed=[self.root])
                with patch.object(dialog, '_confirm', return_value=True), patch(function, side_effect=work):
                    dialog._execute()
                    self.wait(dialog)
                self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
                dialog.deleteLater()
