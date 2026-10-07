"""Content-preserving encryption and one fallback password across a selection."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from commonUtils.zip_access import open_archive, is_encrypted
from features.comics.encryption import plan_encryption, execute_encryption, encrypt_comic


class ComicEncryptionTests(unittest.TestCase):
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
                patch('features.archives.ui.create_zip.Operation') as operation:
            dialog._create()
            prompt.assert_called_once()
            work = operation.call_args.args[0]
            work()
        self.contents(self.root / 'Comic.zip', 'shared')
        with open_archive(self.root / 'Comic.zip', password='shared') as archive:
            self.assertEqual(archive.namelist(), ['Comic.cbz'])
            self.assertEqual(archive.read('Comic.cbz'), path.read_bytes())

    def test_comic_dialog_prompts_once_for_all_missing_files(self):
        from features.comics.ui.encryption import EncryptComicsDialog
        self.comic('one.cbz')
        self.comic('nested/two.cbz')
        dialog = EncryptComicsDialog([self.root])
        self.addCleanup(dialog.deleteLater)
        dialog.plan = plan_encryption([self.root])
        with patch('features.comics.ui.encryption.confirmed_password', return_value='shared') as prompt, \
                patch.object(dialog, '_run') as run:
            dialog._start()
            prompt.assert_called_once()
            self.assertIn('all 2 comics', prompt.call_args.args[1])
            result = run.call_args.args[0]()
        self.assertEqual(len(result['encrypted']), 2)

    def test_cancel_password_does_not_start_encryption(self):
        from features.comics.ui.encryption import EncryptComicsDialog
        path = self.comic('one.cbz')
        original = path.read_bytes()
        dialog = EncryptComicsDialog([path])
        self.addCleanup(dialog.deleteLater)
        dialog.plan = plan_encryption([path])
        with patch('features.comics.ui.encryption.confirmed_password', return_value=None), patch.object(dialog, '_run') as run:
            dialog._start()
            run.assert_not_called()
        self.assertEqual(path.read_bytes(), original)

    def test_folder_zip_keeps_root_and_uses_config_without_prompt(self):
        from features.archives.ui.create_zip import CreateZipDialog
        path = self.comic('Books/Comic.cbz')
        folder = path.parent
        (folder / 'remoteConfig.ini').write_text('[LogisticsZIP]\narchive_password=configured\n')
        dialog = CreateZipDialog([folder])
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(Path(dialog.output.text()), self.root / 'Books.zip')
        with patch('features.archives.ui.create_zip.confirmed_password') as prompt, \
                patch('features.archives.ui.create_zip.Operation') as operation:
            dialog._create()
            prompt.assert_not_called()
            operation.call_args.args[0]()
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
