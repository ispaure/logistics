"""Configured encrypted ZIP creation preserves sources and rejects conflicts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from commonUtils.tests.qt_test_case import QtTestCase
from unittest.mock import patch
from commonUtils.ui import pyside as qt
from commonUtils.archives.zip_access import is_encrypted, open_archive
from services.documents.zip_passwords import clear_passwords
from features.archives.ui.create_zip import CreateZipDialog


class ArchivePasswordUITests(QtTestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.temp = self.temporary_directory()
        self.root = Path(self.temp.name)
        clear_passwords()
        self.addCleanup(clear_passwords)

    def wait(self, dialog):
        self.wait_until(lambda: not dialog.busy, message='Encrypted ZIP creation did not finish')

    def test_creation_uses_config_and_keeps_source(self):
        (self.root / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password = test-only\n')
        source = self.root / 'source.txt'
        source.write_text('original')
        dialog = CreateZipDialog([source])
        with patch('features.archives.ui.create_zip.confirmed_password') as prompt:
            dialog._create()
            self.wait(dialog)
        prompt.assert_not_called()
        self.assertTrue(dialog.succeeded)
        self.assertEqual(source.read_text(), 'original')
        output = Path(dialog.output.text())
        self.assertTrue(is_encrypted(output))
        with open_archive(output, password='test-only') as archive:
            self.assertEqual(archive.read('source.txt'), b'original')

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
        with patch('features.archives.ui.create_zip.confirmed_password') as prompt:
            dialog._create()
            self.wait(dialog)
        prompt.assert_not_called()
        self.assertFalse(dialog.succeeded)
        self.assertIn('different configured passwords', dialog.message.text())
        self.assertFalse(Path(dialog.output.text()).exists())

    def test_cancelled_password_prompt_starts_no_job_or_output(self):
        source = self.root / 'source.txt'
        source.write_bytes(b'Original source')
        dialog = CreateZipDialog([source])
        with patch('features.archives.ui.create_zip.confirmed_password', return_value=None) as prompt, \
             patch.object(dialog.task, 'start') as start:
            dialog._create()
        prompt.assert_called_once()
        start.assert_not_called()
        self.assertFalse(dialog.busy)
        self.assertFalse(dialog.succeeded)
        self.assertTrue(dialog.create_button.isEnabled())
        self.assertFalse(Path(dialog.output.text()).exists())
        self.assertEqual(source.read_bytes(), b'Original source')
