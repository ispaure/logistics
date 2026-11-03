"""Verified ZIP password replacement, credential lifetime and favourite migration."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import pyzipper
from features.rclone import session
from features.rclone.credential_password import change_password
from features.rclone.desktop_credentials import DesktopCredentialLoad
from features.rclone.desktop_service import service
from services.documents.catalog import DocumentCatalog
from services.documents.credential_state import DesktopCredentialCipher


class CredentialPasswordTests(TestCase):
    def package(self, root):
        package = root / 'Account.zip'
        with pyzipper.AESZipFile(package, 'w', encryption=pyzipper.WZ_AES) as archive:
            archive.setpassword(b'old password')
            archive.writestr('Local.txt', '[Local]\ntype = local\n')
        context = root / 'config/Account.session'
        service.credentials.load(DesktopCredentialLoad(package, context, False), 'old password')
        self.addCleanup(lambda: session.forget(context))
        return package, context

    def test_reencrypts_verifies_reloads_and_migrates_favourites_without_plaintext_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package, context = self.package(root)
            old_grant = service.credentials.capture(context)
            cipher = DesktopCredentialCipher(SimpleNamespace(context=context))
            catalog = DocumentCatalog(root)
            source = dict(type='crypt', path='private-sentinel.md')
            catalog.remember(source, 'private-sentinel', {}, favourite=True, cipher=cipher)
            with patch('commonUtils.filesystem.storage.cache_directory', return_value=root):
                message = change_password(package, context, 'new password')
            self.assertIn('password changed', message)
            self.assertTrue(old_grant.revoked())
            self.assertEqual(session.read_package(package, 'new password'), {'Local': {'type': 'local'}})
            with self.assertRaises(Exception):
                session.read_package(package, 'old password')
            self.assertEqual(catalog.read(cipher)['favourites'][0]['title'], 'private-sentinel')
            self.assertFalse(any(b'private-sentinel' in path.read_bytes() for path in root.rglob('*') if path.is_file()))
            self.assertFalse(any(path.suffix == '.txt' for path in root.rglob('*')))

    def test_wrong_current_password_cancel_and_stale_credentials_preserve_original(self):
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as directory:
            package, context = self.package(Path(directory))
            original = package.read_bytes()
            with self.assertRaises(Exception):
                change_password(package, context, 'new password', current_password='wrong')
            self.assertEqual(package.read_bytes(), original)
            with self.assertRaises(OperationCancelled):
                change_password(package, context, 'new password', cancelled=lambda: True)
            self.assertEqual(package.read_bytes(), original)
            session.remember(context, {'Other': {'type': 'local'}}, state_password='old password', state_identity='a' * 64)
            with self.assertRaisesRegex(ValueError, 'differ'):
                change_password(package, context, 'new password')
            self.assertEqual(package.read_bytes(), original)
