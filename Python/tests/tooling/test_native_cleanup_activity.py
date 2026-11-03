"""Xcode activity is refreshed during pruning, not frozen at inventory time."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.xcode_storage import storage_group
from logistics_build.build_retention import storage_groups, device_group


class NativeCleanupActivityTests(unittest.TestCase):
    def test_xcode_started_after_inventory_blocks_cache_deletion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); cache = root / 'caches/one'; cache.mkdir(parents=True)
            source = root / 'mobile_build/build/App.xcodeproj'
            (cache / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(source))))
            os.utime(cache, (1, 1))
            with patch('logistics_build.xcode_storage.subprocess.check_output', side_effect=[
                    '', '/Applications/Xcode.app/Contents/MacOS/Xcode', '']):
                spec = storage_group(root, cache_root=cache.parent, now=100000)
                self.assertFalse(spec['eligible'](cache))
                self.assertTrue(spec['eligible'](cache))
            self.assertEqual(spec['ownership_files'], ('info.plist',))

    def test_failed_activity_refresh_preserves_cache(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); cache = root / 'caches/one'; cache.mkdir(parents=True)
            (cache / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(root / 'mobile_build/build/App.xcodeproj'))))
            os.utime(cache, (1, 1))
            with patch('logistics_build.xcode_storage.subprocess.check_output', side_effect=['', PermissionError('fixture denied')]):
                spec = storage_group(root, cache_root=cache.parent, now=100000)
                self.assertFalse(spec['eligible'](cache))

    def test_project_owned_families_declare_retryable_ownership_markers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with patch('logistics_build.xcode_storage.storage_group', return_value=dict(root=root / 'unused', eligible=lambda p: False)):
                groups = storage_groups(root)
            self.assertEqual(groups['Source snapshots']['ownership_files'], ('.manager-source.json',))
            self.assertEqual(groups['Disposable scratch']['ownership_files'], ('.manager-scratch',))
            self.assertEqual(groups['Reviewed build outputs']['ownership_files'], ('.manager-build-output',))
            self.assertEqual(device_group(root, 'ios')['ownership_files'], ('recipe.json',))
