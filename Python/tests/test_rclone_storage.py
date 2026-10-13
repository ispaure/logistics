"""Application storage relocation uses only isolated synthetic files."""
import errno
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from features.rclone import storage, local_crypt, local_connections


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

    def test_conflicting_destination_preserves_both_locations(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir(); new.mkdir()
            old.joinpath('file').write_bytes(b'old')
            new.joinpath('file').write_bytes(b'new')
            with self.assertRaisesRegex(ValueError, 'Both storage locations exist'):
                storage.relocate(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'old')
            self.assertEqual(new.joinpath('file').read_bytes(), b'new')

    def test_cross_device_copy_verifies_before_removing_source_and_rebases_links(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            old, new, outside = root / 'old', root / 'new', root / 'outside'
            old.mkdir(); outside.mkdir()
            old.joinpath('file').write_bytes(b'ciphertext')
            old.joinpath('relocated-copy').symlink_to('../outside', target_is_directory=True)
            storage.relocate(old, new)
            self.assertFalse(old.exists())
            self.assertEqual(new.joinpath('relocated-copy').resolve(), outside.resolve())
            self.assertEqual(new.joinpath('file').read_bytes(), b'ciphertext')
            old.mkdir()
            old.joinpath('other').write_bytes(b'other ciphertext')
            real_rename = storage.rename_exclusive
            def different_device(source, destination):
                if Path(source) == old:
                    raise OSError(errno.EXDEV, 'Synthetic cross-device rename')
                return real_rename(source, destination)
            with patch.object(storage, 'rename_exclusive', side_effect=different_device):
                storage.relocate(old, root / 'another-volume')
            self.assertEqual(root.joinpath('another-volume/other').read_bytes(), b'other ciphertext')
            self.assertFalse(old.exists())

    def test_failed_copy_keeps_original_and_does_not_publish_destination(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir()
            old.joinpath('file').write_bytes(b'original ciphertext')
            with patch.object(storage, 'rename_exclusive', side_effect=OSError(errno.EXDEV, 'Cross device')), \
                 patch.object(storage.shutil, 'copytree', side_effect=OSError('Synthetic copy failure')):
                with self.assertRaisesRegex(OSError, 'copy failure'):
                    storage.relocate(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'original ciphertext')
            self.assertFalse(new.exists())
            self.assertEqual(sorted(path.name for path in old.parent.iterdir()), ['old'])

    def test_relocated_root_and_internal_links_keep_their_targets(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / 'outside'
            outside.mkdir()
            old, new = root / 'old', root / 'new'
            old.symlink_to('outside', target_is_directory=True)
            storage.relocate(old, new)
            self.assertTrue(new.is_symlink())
            self.assertEqual(new.resolve(), outside.resolve())
            self.assertFalse(old.exists())
            old.mkdir()
            old.joinpath('ciphertext').mkdir()
            old.joinpath('ciphertext/file').write_bytes(b'ciphertext')
            old.joinpath('copy').symlink_to(old / 'ciphertext', target_is_directory=True)
            destination = root / 'moved'
            storage.relocate(old, destination)
            self.assertEqual(destination.joinpath('copy/file').read_bytes(), b'ciphertext')
            self.assertEqual(destination.joinpath('copy').resolve(), destination.joinpath('ciphertext').resolve())

    def test_changed_source_during_copy_is_preserved_and_not_published(self):
        with TemporaryDirectory() as directory:
            old, new = Path(directory) / 'old', Path(directory) / 'new'
            old.mkdir()
            old.joinpath('file').write_bytes(b'original')
            actual_copy = storage.shutil.copytree
            def changing_copy(source, destination, **options):
                result = actual_copy(source, destination, **options)
                old.joinpath('file').write_bytes(b'externally changed')
                return result
            with patch.object(storage, 'rename_exclusive', side_effect=OSError(errno.EXDEV, 'Cross device')), \
                 patch.object(storage.shutil, 'copytree', side_effect=changing_copy):
                with self.assertRaisesRegex(ValueError, 'changed during relocation'):
                    storage.relocate(old, new)
            self.assertEqual(old.joinpath('file').read_bytes(), b'externally changed')
            self.assertFalse(new.exists())
