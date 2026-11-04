"""ZIP creation, password confirmation and cancellation preserve source files."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from threading import Event
from unittest.mock import patch
import zipfile

from commonUtils.archives.zip_access import is_encrypted, open_archive
from commonUtils.runtime.operations import OperationCancelled
from commonUtils.tests.qt_test_case import QtTestCase
from commonUtils.ui import pyside as qt
from features.archives.ui.create_zip import CreateZipDialog


class ZipCreationLifecycleTests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance()
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)

    def wait(self, dialog):
        self.wait_until(lambda: not dialog.busy, message='ZIP creation did not finish')

    def comic(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('01.png', b'unchanged page bytes')
        return path

    def test_zip_suggests_stem_and_prompts_without_configuration(self):
        path = self.comic('Comic.cbz')
        dialog = CreateZipDialog([path])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(Path(dialog.output.text()), self.root / 'Comic.zip')
        with patch('features.archives.ui.create_zip.confirmed_password', return_value='shared') as prompt:
            dialog._create()
            self.wait(dialog)
            prompt.assert_called_once()
        self.assertTrue(dialog.succeeded)
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.task.busy)
        self.assertTrue(is_encrypted(self.root / 'Comic.zip'))
        with open_archive(self.root / 'Comic.zip', password='shared') as archive:
            self.assertEqual(archive.namelist(), ['Comic.cbz'])
            self.assertEqual(archive.read('Comic.cbz'), path.read_bytes())

    def test_folder_zip_keeps_root_and_uses_config_without_prompt(self):
        path = self.comic('Books/Comic.cbz')
        folder = path.parent
        (folder / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=configured\n')
        dialog = CreateZipDialog([folder])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(Path(dialog.output.text()), self.root / 'Books.zip')
        with patch('features.archives.ui.create_zip.confirmed_password') as prompt:
            dialog._create()
            self.wait(dialog)
            prompt.assert_not_called()
        self.assertTrue(dialog.succeeded)
        self.assertEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
        self.assertFalse(dialog.task.busy)
        self.assertTrue(is_encrypted(self.root / 'Books.zip'))
        with open_archive(self.root / 'Books.zip', password='configured') as archive:
            self.assertIn('Books/Comic.cbz', archive.namelist())
            self.assertEqual(archive.read('Books/Comic.cbz'), path.read_bytes())

    def test_prompt_requires_nonempty_matching_confirmation(self):
        from commonUtils.ui import pyside as qt
        from services.documents.ui.password_prompt import confirmed_password
        def interact(dialog):
            fields = dialog.findChildren(qt.QLineEdit)
            buttons = dialog.findChild(qt.QDialogButtonBox)
            buttons.accepted.emit()
            self.assertNotEqual(dialog.result(), qt.QDialog.DialogCode.Accepted)
            self.assertTrue(any(label.text() == 'Enter a nonempty password.'
                                for label in dialog.findChildren(qt.QLabel)))
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


    def test_zip_dialog_cancel_does_not_close_or_destroy_active_worker(self):
        source = self.root / 'source.txt'
        source.write_bytes(b'original')
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=test-only\n')
        entered, release = Event(), Event()
        dialog = CreateZipDialog([source])
        self.addCleanup(dialog.deleteLater)
        def create(*args, cancelled, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test did not release ZIP creation')
            if cancelled():
                raise OperationCancelled('Operation cancelled')
            raise AssertionError('Test should cancel')
        with patch('features.archives.ui.create_zip.create_archive', side_effect=create):
            dialog._create()
            try:
                self.wait_until(entered.is_set, message='ZIP worker did not start')
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
