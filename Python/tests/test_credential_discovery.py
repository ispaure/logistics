"""Credential roots aggregate without creating or sourcing external software folders."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from commonUtils import marcUtils
from features.rclone import credentials


class CredentialDiscoveryTests(unittest.TestCase):
    def test_checkout_and_existing_dropbox_packages_are_aggregated(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / 'checkout/RemoteCredentials'
            dropbox = root / 'dropbox'
            extra = dropbox / 'Software/GIT/logistics/RemoteCredentials'
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
            local = root / 'RemoteCredentials'
            local.mkdir()
            (local / 'package.zip').touch()
            missing = root / 'missing-dropbox'
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=missing):
                self.assertEqual(len(credentials.get_logistics_remote_credentials_zip_lst()), 1)
                self.assertFalse(missing.exists())
            extra = root / 'Software/GIT/logistics/RemoteCredentials'
            extra.parent.mkdir(parents=True)
            extra.symlink_to(local, target_is_directory=True)
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(marcUtils, 'get_marc_dropbox_root', return_value=root):
                self.assertEqual(credentials.get_credential_package_directories(), (local,))

    def test_external_packages_get_distinct_stable_config_names(self):
        from features.rclone import configuration
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            local = root / 'checkout/RemoteCredentials'
            packages = [local / 'same.zip', root / 'dropbox/same.zip', local / 'nested/same.zip']
            with patch.object(credentials.config, 'LogisticsConfig', return_value=SimpleNamespace(path_logistics_remote_cred=local)), patch.object(configuration, 'get_rclone_config_dir', return_value=root / 'configs'):
                configs = [configuration.get_credential_config_path(package) for package in packages]
                self.assertEqual(configs[0], root / 'configs/same.conf')
                self.assertEqual(len(set(configs)), 3)
                self.assertEqual(configuration.get_credential_config_path(packages[1]), configs[1])
