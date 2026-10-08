"""Cancellation preserves ZIP sources and finishes the current comic transaction."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest
from unittest.mock import patch

from PIL import Image
from commonUtils.ui import pyside as qt
from commonUtils.zip_access import create_archive, open_archive, archive_manifest, is_encrypted
from commonUtils.operations import OperationCancelled, BatchResult
from features.comics import cbz, archive_io
from features.comics.ui.dialogs import CompressCbzDialog, ComicAuthorDialog, ComicSeriesDialog, ConvertCbrDialog, CbzIndividualFoldersDialog
from features.archives.ui.create_zip import CreateZipDialog


class AsyncComicTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def wait(self, dialog):
        deadline = time.monotonic() + 5
        while dialog.busy:
            self.assertLess(time.monotonic(), deadline)
            self.app.processEvents()
            time.sleep(.005)
        self.app.processEvents()

    def comic(self, name, password=None):
        path = self.root / name
        image = BytesIO()
        Image.new('RGB', (40, 60), 'orange').save(image, 'PNG')
        with open_archive(path, 'w', password=password) as archive:
            archive.writestr('01.png', image.getvalue())
        return path

    def test_zip_cancellation_in_each_phase_discards_output_and_keeps_sources(self):
        source = self.root / 'large.bin'
        original = os.urandom(2 * 1024 * 1024 + 13)
        source.write_bytes(original)
        for phase in ('Checking ', 'Creating ZIP:', 'Verifying ', 'Publishing verified ZIP:'):
            with self.subTest(phase=phase):
                cancel = Event()
                output = self.root / 'cancelled.zip'
                def progress(done, total, message):
                    if message.startswith(phase):
                        cancel.set()
                with self.assertRaises(OperationCancelled):
                    create_archive([source], output, password='test-only',
                                   progress=progress, cancelled=cancel.is_set)
                self.assertTrue(cancel.is_set())
                self.assertFalse(output.exists())
                self.assertFalse(list(self.root.glob('.logistics-zip-*')))
                self.assertEqual(source.read_bytes(), original)

    def test_zip_cancel_before_start_does_not_create_workspace(self):
        source = self.root / 'source'
        source.write_bytes(b'original')
        output = self.root / 'output/new.zip'
        with self.assertRaises(OperationCancelled):
            create_archive([source], output, password='test-only', cancelled=lambda: True)
        self.assertFalse(output.parent.exists())

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

    def test_zip_dialog_cancel_does_not_close_or_destroy_active_worker(self):
        source = self.root / 'source.txt'
        source.write_bytes(b'original')
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=test-only\n')
        entered, release = Event(), Event()
        dialog = CreateZipDialog([source])
        self.addCleanup(dialog.deleteLater)
        def create(*args, cancelled, **kwargs):
            entered.set()
            release.wait(5)
            if cancelled():
                raise OperationCancelled('Operation cancelled')
            raise AssertionError('Test should cancel')
        with patch('features.archives.ui.create_zip.create_archive', side_effect=create):
            dialog._create()
            try:
                self.assertTrue(entered.wait(2))
                dialog.reject()
                self.assertTrue(dialog.busy)
                self.assertTrue(dialog.task.cancelled.is_set())
            finally:
                release.set()
                self.wait(dialog)
        self.assertFalse(dialog.succeeded)
        self.assertIn('Cancelled.', dialog.message.text())
        self.assertFalse(Path(dialog.output.text()).exists())
        self.assertEqual(source.read_bytes(), b'original')

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
