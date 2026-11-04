"""Project retention only touches declared generated build families."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys
from unittest.mock import patch

from logistics_build.build_retention import clean, enroll_output, scratch, storage_inventory
from build_manager.retention import lease


class BuildRetentionTests(unittest.TestCase):
    def test_five_day_window_expires_six_day_outputs_and_preserves_four_day_outputs(self):
        import time
        for snapshots in (False, True):
            with self.subTest(snapshots=snapshots), TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                parent = root / ('mobile_build/.tools/build-manager/snapshots'
                                 if snapshots else 'mobile_build/build')
                paths = []
                for index, days in enumerate((6, 4, 3, 2, 1)):
                    path = parent / (str(index) * 64 if snapshots else f'probe-{index}')
                    path.mkdir(parents=True)
                    if snapshots:
                        (path / '.manager-source.json').write_text('{}')
                    else:
                        enroll_output(path.name, root)
                    stamp = time.time() - days * 86400
                    os.utime(path, (stamp, stamp))
                    paths.append(path)
                self.assertEqual(clean(root), [str(paths[0])])
                self.assertEqual(clean(root, apply=True), [str(paths[0])])
                self.assertFalse(paths[0].exists())
                self.assertTrue(all(path.exists() for path in paths[1:]))

    def test_scratch_command_keeps_document_history_out_of_parent_storage(self):
        from logistics_build.build_retention import main
        from services.documents.catalog import DocumentCatalog
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            live = root / 'live'
            catalog = DocumentCatalog(live / 'Cache', recent=True)
            catalog.remember(dict(type='local', path='/personal/Note.md'), 'Note.md', {})
            before = catalog.path().read_bytes()
            evidence = root / 'probe.json'
            command = '''
import json, os, sys
from pathlib import Path
from commonUtils.filesystem.storage import cache_directory
from services.documents.catalog import DocumentCatalog
store = DocumentCatalog(cache_directory(), recent=True)
store.remember(dict(type='local', path=str(Path.cwd() / 'Welcome.md')), 'Welcome.md', {})
Path(sys.argv[1]).write_text(json.dumps(dict(storage=os.environ['COMMONUTILS_STORAGE_ROOT'],
    titles=[row['title'] for row in store.entries('recent')])))
'''
            arguments = ['retention', '--root', str(root), '--scratch', sys.executable, '-c', command, str(evidence)]
            with patch.dict(os.environ, COMMONUTILS_STORAGE_ROOT=str(live)), patch.object(sys, 'argv', arguments):
                self.assertEqual(main(), 0)
                self.assertEqual(os.environ['COMMONUTILS_STORAGE_ROOT'], str(live))
            result = json.loads(evidence.read_text())
            self.assertEqual(result['titles'], ['Welcome.md'])
            self.assertTrue(Path(result['storage']).is_relative_to(root / 'test-results/build-scratch'))
            self.assertFalse(Path(result['storage']).exists())
            self.assertEqual(catalog.path().read_bytes(), before)

    def setUp(self):
        # Project fixtures must never inventory the developer's real Xcode caches.
        mock = patch('logistics_build.xcode_storage.storage_group', return_value=dict(
            root=Path('/__no_xcode_fixture__'), eligible=lambda p: False))
        mock.start()
        self.addCleanup(mock.stop)

    def test_reviewed_legacy_outputs_respect_age_pins_leases_and_unknown_evidence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / 'mobile_build/build'
            for number in range(1, 9):
                path = parent / f'probe-{number}'
                path.mkdir(parents=True)
                enroll_output(path.name, root)
                os.utime(path, (number, number))
            (parent / 'probe-1/.keep').touch()
            os.utime(parent / 'probe-1', (1, 1))
            (parent / 'old-evidence').mkdir()
            (parent / 'old-evidence/report.json').write_text('{}')
            recent = parent / 'recent'
            recent.mkdir()
            enroll_output(recent.name, root)
            # Enrollment refreshes age, even when adopting an old directory.
            with lease(parent / 'probe-2'):
                os.utime(parent / 'probe-2', (2, 2))
                preview = clean(root)
                self.assertEqual({Path(p).name for p in preview}, {'probe-3', 'probe-4', 'probe-5', 'probe-6'})
                self.assertEqual(clean(root, apply=True), preview)
            for name in ('probe-1', 'probe-2', 'probe-7', 'probe-8', 'recent', 'old-evidence'):
                self.assertTrue((parent / name).is_dir(), name)
            rows = storage_inventory(root)
            self.assertTrue(any(row['group'] == 'Reviewed build outputs' for row in rows))
            self.assertFalse(any(row['name'] == 'old-evidence' for row in rows))

    def test_snapshot_budget_can_expire_recent_snapshots_but_keeps_pins_and_locks(self):
        import time
        from build_manager.locking import workspace_lock
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / 'mobile_build/.tools/build-manager/snapshots'
            stamp = time.time() - 7200
            for i in range(7):
                path = parent / (str(i) * 64); path.mkdir(parents=True)
                (path / '.manager-source.json').write_text('{}')
                os.utime(path, (stamp + i, stamp + i))
            (parent / ('0' * 64) / '.keep').touch()
            os.utime(parent / ('0' * 64), (stamp, stamp))
            with workspace_lock((parent / ('1' * 64)).with_suffix('.lock')), \
                    patch('build_manager.retention.allocated_bytes', return_value=10 * 1024 ** 3):
                preview = clean(root)
                self.assertEqual({Path(p).name for p in preview}, {'2' * 64, '3' * 64})
                self.assertEqual(clean(root, apply=True), preview)
            self.assertTrue(all((parent / (str(i) * 64)).exists() for i in (0, 1, 4, 5, 6)))

    def test_device_workspace_cleanup_uses_recipe_identity_and_operation_lock(self):
        import json
        from build_manager.locking import workspace_lock
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / 'mobile_build/.tools/build-manager/workspaces/devices/ios'
            for i in range(7):
                path = parent / (str(i) * 32); path.mkdir(parents=True)
                (path / 'recipe.json').write_text(json.dumps(dict(schema=1, platform='ios', workspace=str(path))))
                os.utime(path / 'recipe.json', (1000 + i, 1000 + i))
                os.utime(path, (1000 + i, 1000 + i))
            unknown = parent / ('a' * 32); unknown.mkdir()
            (parent / ('0' * 32) / '.keep').touch()
            os.utime(parent / ('0' * 32), (1000, 1000))
            with workspace_lock(parent / ('1' * 32) / 'operation.lock'):
                os.utime(parent / ('1' * 32), (1001, 1001))
                preview = clean(root)
                self.assertEqual({Path(p).name for p in preview}, {'2' * 32, '3' * 32})
                self.assertEqual(clean(root, apply=True), preview)
            self.assertTrue(unknown.exists())

    def test_enrollment_rejects_reserved_missing_and_linked_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            parent = root / 'mobile_build/build'
            parent.mkdir(parents=True)
            for name in ('testflight', 'firebase', 'physical-device', '../escape', '.hidden', 'missing'):
                with self.assertRaises(ValueError, msg=name):
                    enroll_output(name, root)
            outside = root / 'evidence'
            outside.mkdir()
            (parent / 'linked').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                enroll_output('linked', root)
            output = parent / 'marker-link'
            output.mkdir()
            (outside / 'marker').write_text('preserve')
            (output / '.manager-build-output').symlink_to(outside / 'marker')
            with self.assertRaises(ValueError):
                enroll_output(output.name, root)
            self.assertEqual(clean(root, apply=True), [])
            self.assertEqual((outside / 'marker').read_text(), 'preserve')

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
