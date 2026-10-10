"""Content-preserving encryption and one fallback password across a selection."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
import zipfile
from commonUtils.archives.zip_access import open_archive, is_encrypted
from features.comics.encryption import plan_encryption, execute_encryption, encrypt_comic


class ComicEncryptionTests(QtTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def comic(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.comment = b'archive comment'
            archive.writestr('wrapper/empty/', b'')
            archive.writestr('wrapper/page 1.png', b'unchanged image bytes')
            archive.writestr('ComicInfo.xml', b'<ComicInfo/>')
        return path

    def contents(self, path, password=None):
        with open_archive(path, password=password) as archive:
            return archive.comment, [(i.filename, archive.read(i)) for i in archive.infolist()]

    def test_preserves_entries_and_content_and_skips_encrypted(self):
        path = self.comic('Comic.cbz')
        before = self.contents(path)
        self.assertTrue(encrypt_comic(path, 'secret'))
        self.assertTrue(is_encrypted(path))
        self.assertEqual(self.contents(path, 'secret'), before)
        encrypted = path.read_bytes()
        self.assertFalse(encrypt_comic(path, 'different'))
        self.assertEqual(path.read_bytes(), encrypted)

    def test_recursive_selection_deduplicates_and_shares_missing_password(self):
        first = self.comic('one.cbz')
        second = self.comic('nested/two.CBZ')
        configured = self.comic('configured/three.cbz')
        (configured.parent / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=local\n')
        plan = plan_encryption([self.root, first])
        self.assertEqual(set(plan.missing), {first, second})
        result = execute_encryption(plan, 'shared')
        self.assertEqual(len(result['encrypted']), 3)
        self.assertFalse(result['failed'])
        for path, password in [(first, 'shared'), (second, 'shared'), (configured, 'local')]:
            self.contents(path, password)

    def test_failed_verification_preserves_original(self):
        path = self.comic('Comic.cbz')
        before = path.read_bytes()
        with patch('features.comics.encryption.stream_signature', side_effect=ValueError('verification failed')):
            with self.assertRaises(ValueError):
                encrypt_comic(path, 'secret')
        self.assertEqual(path.read_bytes(), before)

    def test_empty_archive_is_not_replaced_by_unencrypted_output(self):
        path = self.root / 'empty.cbz'
        with zipfile.ZipFile(path, 'w'):
            pass
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'empty'):
            encrypt_comic(path, 'secret')
        self.assertEqual(path.read_bytes(), before)

    def test_missing_password_preserves_original(self):
        path = self.comic('Comic.cbz')
        before = path.read_bytes()
        result = execute_encryption(plan_encryption([path]))
        self.assertIn(path, result['failed'])
        self.assertEqual(path.read_bytes(), before)

    def test_cancellation_finishes_current_and_leaves_remaining_unchanged(self):
        from threading import Event
        first, second = self.comic('one.cbz'), self.comic('two.cbz')
        before = second.read_bytes()
        plan = plan_encryption([first, second])
        cancel = Event()
        updates = []
        def encrypt(path, password):
            cancel.set()  # User cancellation arriving during the first archive.
            return encrypt_comic(path, password)
        with patch('features.comics.encryption.encrypt_comic', side_effect=encrypt):
            result = execute_encryption(plan, 'shared', cancelled=cancel.is_set,
                                        progress=lambda *args: updates.append(args))
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['encrypted'], [first])
        self.assertEqual(result['remaining'], [second])
        self.assertEqual(second.read_bytes(), before)
        self.contents(first, 'shared')
        self.assertEqual(updates[-1], (1, 2, None))

    def test_cancel_before_start_touches_no_comics(self):
        path = self.comic('one.cbz')
        original = path.read_bytes()
        result = execute_encryption(plan_encryption([path]), 'shared', cancelled=lambda: True)
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['remaining'], [path])
        self.assertEqual(path.read_bytes(), original)

    def test_progress_counts_failures_as_processed(self):
        path = self.comic('one.cbz')
        updates = []
        result = execute_encryption(plan_encryption([path]), progress=lambda *args: updates.append(args))
        self.assertIn(path, result['failed'])
        self.assertEqual(updates[-1], (1, 1, None))
        self.assertFalse(result['cancelled'])


class EncryptionDialogTests(ComicEncryptionTests):
    def setUp(self):
        super().setUp()
        from commonUtils.ui import pyside as qt
        self.app = qt.QApplication.instance() or qt.QApplication([])

    def test_zip_suggests_stem_and_prompts_without_configuration(self):
        from features.archives.ui.create_zip import CreateZipDialog
        path = self.comic('Comic.cbz')
        dialog = CreateZipDialog([path])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(Path(dialog.output.text()), self.root / 'Comic.zip')
        with patch('features.archives.ui.create_zip.confirmed_password', return_value='shared') as prompt, \
                patch.object(dialog.task, 'start') as operation:
            dialog._create()
            prompt.assert_called_once()
            work = operation.call_args.args[0]
            work(lambda *args: None, lambda: False)
        self.contents(self.root / 'Comic.zip', 'shared')
        with open_archive(self.root / 'Comic.zip', password='shared') as archive:
            self.assertEqual(archive.namelist(), ['Comic.cbz'])
            self.assertEqual(archive.read('Comic.cbz'), path.read_bytes())

    def test_comic_dialog_refuses_missing_configured_password(self):
        from features.comics.ui.encryption import EncryptComicsDialog
        path = self.comic('one.cbz')
        original = path.read_bytes()
        dialog = EncryptComicsDialog([path])
        self.addCleanup(dialog.deleteLater)
        dialog.plan = plan_encryption([path])
        with patch.object(dialog, '_run') as run:
            dialog._start()
            run.assert_not_called()
        self.assertIn('Cannot continue', dialog.message.text())
        self.assertEqual(path.read_bytes(), original)

    def test_comic_dialog_assesses_on_open(self):
        from features.comics.ui.encryption import EncryptComicsDialog
        path = self.comic('one.cbz')
        with patch.object(EncryptComicsDialog, '_run') as run:
            dialog = EncryptComicsDialog([path])
            self.addCleanup(dialog.deleteLater)
            dialog.show()
            self.app.processEvents()
            run.assert_called_once()
            self.assertIn(path, run.call_args.args[0]().missing)
        dialog.close()

    def test_folder_zip_keeps_root_and_uses_config_without_prompt(self):
        from features.archives.ui.create_zip import CreateZipDialog
        path = self.comic('Books/Comic.cbz')
        folder = path.parent
        (folder / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=configured\n')
        dialog = CreateZipDialog([folder])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(Path(dialog.output.text()), self.root / 'Books.zip')
        with patch('features.archives.ui.create_zip.confirmed_password') as prompt, \
                patch.object(dialog.task, 'start') as operation:
            dialog._create()
            prompt.assert_not_called()
            operation.call_args.args[0](lambda *args: None, lambda: False)
        with open_archive(self.root / 'Books.zip', password='configured') as archive:
            self.assertIn('Books/Comic.cbz', archive.namelist())
            self.assertEqual(archive.read('Books/Comic.cbz'), path.read_bytes())

    def test_prompt_requires_nonempty_matching_confirmation(self):
        from commonUtils.ui import pyside as qt
        from services.password_prompt import confirmed_password
        def interact(dialog):
            fields = dialog.findChildren(qt.QLineEdit)
            buttons = dialog.findChild(qt.QDialogButtonBox)
            fields[0].setText('one')
            fields[1].setText('two')
            buttons.accepted.emit()
            self.assertNotEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
            fields[1].setText('one')
            buttons.accepted.emit()
            self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
            return dialog.result()
        with patch.object(qt.QDialog, 'exec', interact):
            self.assertEqual(confirmed_password(None, 'Shared batch password'), 'one')

    def test_background_dialog_cancel_waits_for_current_comic(self):
        from threading import Event
        import time
        from features.comics.ui.encryption import EncryptComicsDialog
        first, second = self.comic('one.cbz'), self.comic('two.cbz')
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=shared\n')
        original = second.read_bytes()
        entered, release = Event(), Event()
        dialog = EncryptComicsDialog([first, second])
        dialog.plan = plan_encryption([first, second])
        self.addCleanup(dialog.deleteLater)
        def encrypt(path, password):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test did not release encryption')
            return encrypt_comic(path, password)
        with patch('features.comics.encryption.encrypt_comic', side_effect=encrypt):
            dialog._start()
            try:
                deadline = time.monotonic() + 5
                while not entered.is_set():
                    self.assertLess(time.monotonic(), deadline)
                    self.app.processEvents()
                    time.sleep(.005)
                self.app.processEvents()
                self.assertTrue(dialog.cancel_button.isEnabled())
                dialog.cancel_button.click()
                self.assertTrue(dialog.busy)
                self.assertFalse(dialog.cancel_button.isEnabled())
            finally:
                release.set()
                deadline = time.monotonic() + 5
                while dialog.busy:
                    self.assertLess(time.monotonic(), deadline)
                    self.app.processEvents()
                    time.sleep(.005)
        self.assertEqual(dialog.progress_bar.value(), 1)
        self.assertEqual(dialog.progress_bar.maximum(), 2)
        self.assertIn('Cancelled.', dialog.message.text())
        self.assertIn('not processed: 1', dialog.message.text())
        self.assertEqual(second.read_bytes(), original)
        self.contents(first, 'shared')
