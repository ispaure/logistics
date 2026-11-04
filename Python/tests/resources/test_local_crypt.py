"""Ciphertext mirror, streaming readers/editors, private UI and credential lifetime."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from features.rclone.localcrypt import mapping as copy_mapping


class LocalCryptNamingTests(unittest.TestCase):
    def test_browser_recognizes_relocated_copy_and_external_aliases(self):
        from desktop.file_browser import _crypt_location
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            item = copy_mapping.Connection(root / 'one.zip', 'Secret', root / 'LocalCrypt')
            with patch('services.local_storage.install_local_storage_policy'), \
                 patch.object(copy_mapping, 'storage_root', return_value=item.root):
                item.publish()
                target = root / 'relocated'
                item.data.rename(target)
                item.data.symlink_to(target, target_is_directory=True)
                alias = root / 'shortcut'
                alias.symlink_to(target, target_is_directory=True)
                for path in (item.data, target, alias, alias / 'opaque-subfolder'):
                    self.assertEqual(_crypt_location(path), (item, True))
                self.assertEqual(_crypt_location(root), (None, False))

    def test_clean_name_repeat_publish_and_conflicts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'LocalCrypt'
            first = copy_mapping.Connection(Path(directory) / 'one.zip', 'Legacy-ComicRack', root)
            with patch('services.local_storage.install_local_storage_policy'):
                first.publish()
                self.assertEqual(first.data, root / 'Legacy-ComicRack')
                (first.data / 'sentinel').write_bytes(b'ciphertext')
                first.publish()
                self.assertEqual(copy_mapping.connections(root), [first])
                self.assertEqual(copy_mapping.for_path(first.data / 'sentinel', root), first)
                for name in ('Legacy-ComicRack', 'legacy-comicrack'):
                    other = copy_mapping.Connection(Path(directory) / 'two.zip', name, root)
                    with self.assertRaisesRegex(ValueError, 'another credential package'):
                        other.publish()
                    self.assertFalse(other.record.exists())
                self.assertEqual((first.data / 'sentinel').read_bytes(), b'ciphertext')
                first.record.unlink()
                with self.assertRaisesRegex(ValueError, 'without this credential mapping'):
                    first.publish()

    def test_unsupported_mapping_is_preserved_and_invalid_names_are_refused(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / 'LocalCrypt'
            current = copy_mapping.Connection(Path(directory) / 'one.zip', 'Secret', root)
            current.record.parent.mkdir(parents=True)
            original = json.dumps({'schema': 1, 'package': str(current.package), 'remote': current.remote}).encode()
            current.record.write_bytes(original)
            old_data = root / 'old-package-hash' / 'Secret-oldhash'
            old_data.mkdir(parents=True)
            (old_data / 'sentinel').write_bytes(b'preserve old ciphertext')
            with patch('services.local_storage.install_local_storage_policy'):
                self.assertEqual(copy_mapping.connections(root), [])
                with self.assertRaisesRegex(ValueError, 'existing LocalCrypt credential mapping is invalid'):
                    current.publish()
                self.assertFalse(current.data.exists())
                self.assertEqual(current.record.read_bytes(), original)
                self.assertEqual((old_data / 'sentinel').read_bytes(), b'preserve old ciphertext')
                for name in ('../escape', '.connections', 'a/b', 'a\\b', 'CON', 'trailing.', 'trailing '):
                    with self.assertRaises(ValueError):
                        copy_mapping.Connection(current.package, name, root).publish()
