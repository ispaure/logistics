"""Application storage relocation uses only isolated synthetic files."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from features.rclone import storage
from features.rclone.localcrypt import backend as local_crypt
from features.rclone.localcrypt import connections as local_connections


class RcloneStorageTests(unittest.TestCase):
    def test_application_root_uses_logistics_preferences_location(self):
        from features import preferences
        with patch.object(preferences.sys, 'platform', 'darwin'), patch.object(Path, 'home', return_value=Path('/fixture/home')):
            self.assertEqual(storage.application_root(), Path('/fixture/home/Library/Application Support/Logistics'))

    def test_legacy_copies_and_plain_associations_move_to_application_support(self):
        import config
        with TemporaryDirectory() as directory:
            root = Path(directory)
            support, server = root / 'Application Support/Logistics', root / 'Server'
            local = server / 'Local'
            package = root / 'Account.zip'
            old = local_crypt.Connection(package, 'Secret', server / 'LocalCrypt')
            old.data.mkdir(parents=True)
            old.data.joinpath('encrypted-name').write_bytes(b'ciphertext bytes')
            old.record.parent.mkdir()
            metadata = {'schema': 2, 'package': str(package), 'remote': 'Secret'}
            old.record.write_text(json.dumps(metadata))
            local.joinpath('Secret').mkdir(parents=True)
            legacy_records = server / '.local-connections'
            legacy_records.mkdir()
            legacy_records.joinpath(old.record.name).write_text(json.dumps({**metadata, 'schema': 1}))
            with patch.object(storage, 'application_root', return_value=support), \
                 patch.object(config, 'LogisticsConfig', return_value=SimpleNamespace(server_path=server, path_remote_local=local)):
                encrypted, = local_crypt.connections()
                ordinary, = local_connections.connections()
                self.assertEqual(encrypted.root, support / 'LocalCrypt')
                self.assertEqual(encrypted.data.joinpath('encrypted-name').read_bytes(), b'ciphertext bytes')
                self.assertEqual(ordinary.data, local / 'Secret')
                self.assertEqual(ordinary.record.parent, support / 'Connections/Local')
                self.assertFalse(old.root.exists())
                self.assertFalse(legacy_records.exists())
                self.assertEqual(local_crypt.connections(), [encrypted])
                self.assertEqual(local_connections.connections(), [ordinary])
