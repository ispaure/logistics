"""Xcode cache ownership and activity checks use metadata, never display names."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from datetime import datetime, timezone
import os
from pathlib import Path
import plistlib
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager.locking import workspace_lock
from build_manager.retention import prune
from logistics_build.xcode_storage import storage_group, access_order


class XcodeStorageTests(unittest.TestCase):
    def test_owned_caches_prune_while_foreign_corrupt_linked_and_active_survive(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); project = root / 'project'; cache = root / 'cache'
            source_root = project / 'mobile_build/.tools/build-manager/snapshots'
            for i in range(7):
                snapshot = source_root / (str(i) * 64); snapshot.mkdir(parents=True)
                source = snapshot / 'mobile_build/build/logisticsmobile/ios/xcode/App.xcodeproj'
                path = cache / ('cache-' + str(i)); path.mkdir(parents=True)
                (path / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(source),
                    LastAccessedDate=datetime.fromtimestamp(1000 + i, timezone.utc).replace(tzinfo=None))))
                os.utime(path, (1000 + i, 1000 + i))
            # The folder name is not the project identity.
            foreign = cache / 'Logistics_Mobile-foreign'; foreign.mkdir()
            (foreign / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(root / 'other/build/App.xcodeproj'))))
            corrupt = cache / 'bad'; corrupt.mkdir(); (corrupt / 'info.plist').write_bytes(b'bad')
            (cache / 'link').symlink_to(cache / 'cache-0', target_is_directory=True)
            (source_root / ('0' * 64) / '.keep').touch()
            processes = 'xcodebuild -project ' + str(source_root / ('1' * 64)) + '/mobile_build/build/App.xcodeproj'
            spec = storage_group(project, cache_root=cache, processes=processes, now=100000)
            with workspace_lock((source_root / ('2' * 64)).with_suffix('.lock')):
                selected = prune(**spec, keep=1, age_days=0, order_key=access_order, apply=True)
            self.assertEqual({Path(p).name for p in selected}, {'cache-3', 'cache-4', 'cache-5'})
            self.assertTrue(all((cache / n).exists() for n in ('cache-0', 'cache-1', 'cache-2', 'cache-6', 'bad', foreign.name)))

    def test_recent_access_and_open_xcode_are_protected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = root / 'cache'; path.mkdir()
            source = root / 'mobile_build/build/App.xcodeproj'
            (path / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(source),
                LastAccessedDate=datetime.fromtimestamp(10000, timezone.utc).replace(tzinfo=None))))
            os.utime(path, (1, 1))
            for processes, now in [('', 10001), ('/Applications/Xcode 27.1.app/Contents/MacOS/Xcode', 100000)]:
                self.assertFalse(storage_group(root, processes=processes, now=now)['eligible'](path))

    def test_unavailable_process_inventory_fails_closed(self):
        with patch('logistics_build.xcode_storage.subprocess.check_output', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                storage_group(Path('/project'))
