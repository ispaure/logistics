"""Shared extraction retains rclone package layout and cleans private workspaces."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils.zip_access import open_archive
from features.rclone import credentials


class ArchiveCredentialsTests(unittest.TestCase):
    def test_plain_and_aes_credential_packages_have_identical_results(self):
        for password in (None, 'test-only-password'):
            with self.subTest(encrypted=password is not None), TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, output = root / 'credentials.zip', root / 'credentials.conf'
                with open_archive(source, 'w', password=password) as archive:
                    archive.writestr('remote.txt', '[TestRemote]\ntype = local\n')
                before = source.read_bytes()
                with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(temp_path=root / 'temp')), patch.object(credentials.configuration, 'get_credential_config_path', return_value=output):
                    self.assertTrue(credentials.load_remote_from_zip_to_config(source, password))
                self.assertEqual(output.read_text().strip(), '[TestRemote]\ntype = local')
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(list((root / 'temp').iterdir()), [])

    def test_incorrect_password_keeps_existing_config_and_removes_workspace(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'credentials.zip', root / 'credentials.conf'
            output.write_text('existing config')
            with open_archive(source, 'w', password='test-only-correct') as archive:
                archive.writestr('remote.txt', '[Remote]\ntype = local\n')
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(temp_path=root / 'temp')), patch.object(credentials.configuration, 'get_credential_config_path', return_value=output), patch.object(credentials.ui, 'display_msg_box_ok') as message:
                self.assertFalse(credentials.load_remote_from_zip_to_config(source, 'test-only-wrong'))
            message.assert_called_once()
            self.assertEqual(output.read_text(), 'existing config')
            self.assertEqual(list((root / 'temp').iterdir()), [])
