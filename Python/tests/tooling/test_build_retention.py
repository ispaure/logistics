"""Project retention only touches declared generated build families."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from Scripts.build_retention import clean, scratch


class BuildRetentionTests(unittest.TestCase):
    def test_preview_and_cleanup_preserve_configuration_and_unknown_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for provider in ('firebase', 'testflight'):
                for number in range(1, 6):
                    path = root / 'mobile_build/build' / provider / str(number)
                    path.mkdir(parents=True)
                    os.utime(path, (number, number))
                (path.parent / 'manual-backup').mkdir()
            private = root / 'mobile_build/.tools/build-manager'
            private.mkdir(parents=True)
            profile = private / 'profile.json'
            profile.write_text('private configuration')
            preview = clean(root)
            self.assertEqual(len(preview), 4)
            self.assertTrue(all(Path(p).exists() for p in preview))
            self.assertEqual(clean(root, apply=True), preview)
            self.assertTrue(profile.exists())
            self.assertTrue((root / 'mobile_build/build/firebase/manual-backup').exists())

    def test_scratch_removed_after_error_and_keep_is_explicit(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError), scratch(directory) as path:
                (path / 'big-output').touch()
                raise ValueError('failed probe')
            self.assertFalse(path.exists())
            with scratch(directory) as kept:
                (kept / '.keep').touch()
            self.assertTrue(kept.exists())


if __name__ == '__main__':
    unittest.main()
