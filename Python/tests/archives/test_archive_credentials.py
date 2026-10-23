"""Credential package loading validates in memory and never extracts plaintext TXT."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.archives.zip_access import open_archive
from features.rclone import credentials


class ArchiveCredentialsTests(unittest.TestCase):
    def package(self, source):
        with open_archive(source, 'w', password='test-only-password') as archive:
            archive.writestr('remote.txt', '[TestRemote]\ntype = local\n')

    def test_aes_package_writes_only_the_selected_config_and_preserves_zip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'credentials.zip', root / 'credentials.conf'
            self.package(source)
            before = source.read_bytes()
            with patch.object(credentials.configuration, 'get_credential_config_path', return_value=output), patch(
                    'commonUtils.archives.legacy.unzip_file', side_effect=AssertionError('Must not extract')):
                self.assertTrue(credentials.load_remote_from_zip_to_config(source, 'test-only-password'))
            self.assertEqual(output.read_text().strip(), '[TestRemote]\ntype = local')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(set(root.iterdir()), {source, output})

    def test_write_failure_preserves_config_zip_and_leaves_no_extracted_files(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'credentials.zip', root / 'credentials.conf'
            self.package(source)
            output.write_bytes(b'original config')
            before = source.read_bytes()
            with patch.object(credentials.configuration, 'get_credential_config_path', return_value=output), patch(
                    'commonUtils.persistence.atomic_write_bytes', side_effect=OSError('Fixture failure')), patch.object(
                    credentials.ui, 'display_msg_box_ok'):
                self.assertFalse(credentials.load_remote_from_zip_to_config(source, 'test-only-password'))
            self.assertEqual(output.read_bytes(), b'original config')
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(set(root.iterdir()), {source, output})

    def test_incorrect_password_keeps_existing_config(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, output = root / 'credentials.zip', root / 'credentials.conf'
            self.package(source)
            output.write_text('existing config')
            with patch.object(credentials.configuration, 'get_credential_config_path', return_value=output), patch.object(
                    credentials.ui, 'display_msg_box_ok') as message:
                self.assertFalse(credentials.load_remote_from_zip_to_config(source, 'test-only-wrong'))
            message.assert_called_once()
            self.assertEqual(output.read_text(), 'existing config')
            self.assertEqual(set(root.iterdir()), {source, output})
