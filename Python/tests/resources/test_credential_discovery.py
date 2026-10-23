"""Credential roots aggregate without creating or sourcing external software folders."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from services import personal_paths as marcUtils
from features.rclone import credentials


class CredentialDiscoveryTests(unittest.TestCase):
    def test_personal_dropbox_defaults_preserve_windows_probe_and_home_fallback(self):
        from services import personal_paths
        from commonUtils.runtime.platform import OS
        with patch.object(personal_paths, 'get_os', return_value=OS.WIN), \
                patch.object(personal_paths.os.path, 'isdir', return_value=True):
            self.assertEqual(personal_paths.get_marc_dropbox_root(),
                             Path(r'B:\Yagi Dropbox\Marc-Andre Voyer'))
        for system in (OS.WIN, OS.MAC, OS.LINUX):
            with self.subTest(system=system), \
                    patch.object(personal_paths, 'get_os', return_value=system), \
                    patch.object(personal_paths.os.path, 'isdir', return_value=False), \
                    patch.object(personal_paths.fileUtils, 'get_user_home_dir', return_value=Path('/fixture')):
                self.assertEqual(personal_paths.get_marc_dropbox_root(),
                                 Path('/fixture/Yagi Dropbox/Marc-Andre Voyer'))

    def test_checkout_and_existing_dropbox_packages_are_aggregated(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / 'checkout/Credentials/rclone'
            dropbox = root / 'dropbox'
            extra = dropbox / 'Software/GIT/logistics/Credentials/rclone'
            for directory in (local, extra):
                directory.mkdir(parents=True)
                (directory / 'package.zip').write_bytes(b'fixture')
                (directory / 'not-a-package.txt').write_text('fixture')
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=dropbox):
                self.assertEqual({file.path for file in credentials.get_logistics_remote_credentials_zip_lst()},
                                 {local.resolve() / 'package.zip', extra.resolve() / 'package.zip'})

    def test_missing_dropbox_is_not_created_and_same_root_is_deduplicated(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / 'Credentials/rclone'
            local.mkdir(parents=True)
            (local / 'package.zip').touch()
            missing = root / 'missing-dropbox'
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=missing):
                self.assertEqual(len(credentials.get_logistics_remote_credentials_zip_lst()), 1)
                self.assertFalse(missing.exists())
            extra = root / 'Software/GIT/logistics/Credentials/rclone'
            extra.parent.mkdir(parents=True)
            extra.symlink_to(local, target_is_directory=True)
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=root):
                self.assertEqual(credentials.get_credential_package_directories(), (local,))

    def test_obsolete_and_blender_credential_roots_are_not_discovered(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / 'checkout/Credentials/rclone'
            local.mkdir(parents=True)
            for directory in (root / 'checkout/RemoteCredentials',
                              root / 'Software/GIT/logistics/RemoteCredentials',
                              root / 'Software/GIT/logistics/Credentials/blender_addons'):
                directory.mkdir(parents=True)
                (directory / 'private.zip').touch()
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=root):
                self.assertEqual(credentials.get_logistics_remote_credentials_zip_lst(), [])

    def test_all_package_locations_use_zip_names_and_find_existing_configs(self):
        from features.rclone import configuration
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_dir = root / 'configs'
            config_dir.mkdir()
            existing = config_dir / 'Personal.account.conf'
            existing.write_text('[fixture]\n')
            packages = [root / location / 'Personal.account.zip'
                        for location in ('checkout/Credentials/rclone', 'dropbox', 'checkout/Credentials/rclone/nested')]
            with patch.object(configuration, 'get_rclone_config_dir', return_value=config_dir):
                for package in packages:
                    config_path = configuration.get_credential_config_path(package)
                    self.assertEqual(config_path, existing)
                    self.assertTrue(config_path.is_file())
                self.assertEqual(configuration.get_credential_config_path(root / 'Other.zip'),
                                 config_dir / 'Other.conf')
