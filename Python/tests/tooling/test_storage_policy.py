"""Owned cache/evidence separation and explicitly adopted scratch/session lifecycles."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import plistlib
import shutil
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from build_manager.locking import workspace_lock
from build_manager.retention import durable_hold, prune, pinned
from logistics_build.build_retention import clean, device_intermediates, storage_inventory, delete_storage
from logistics_build import storage_extras as extras
from logistics_build.xcode_storage import storage_group


class StoragePolicyTests(unittest.TestCase):
    def setUp(self):
        guard = patch('logistics_build.build_retention.cache_idle', return_value=True)
        guard.start()
        self.addCleanup(guard.stop)

    def test_snapshot_caches_preserve_signed_artifacts_and_respect_snapshot_lock(self):
        from logistics_build.build_retention import snapshot_intermediates
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            snapshot = root / 'mobile_build/.tools/build-manager/snapshots' / ('c' * 64)
            archive = snapshot / 'mobile_build/build/testflight/123'
            (archive / 'derived').mkdir(parents=True)
            (archive / 'Logistics.xcarchive').mkdir()
            (archive / 'app.ipa').write_bytes(b'signed package')
            (snapshot / '.manager-source.json').write_text('{}')
            durable_hold(snapshot, 'paused-fixture')
            groups = list(snapshot_intermediates(root))
            spec = next(spec for _, spec in groups if spec['root'] == archive)
            with workspace_lock(snapshot.with_suffix('.lock')):
                self.assertEqual(prune(**spec, keep=0, age_days=0), [])
            self.assertEqual(prune(**spec, keep=0, age_days=0, apply=True), [str(archive / 'derived')])
            self.assertEqual((archive / 'app.ipa').read_bytes(), b'signed package')
            self.assertTrue((archive / 'Logistics.xcarchive').is_dir())
            self.assertTrue(pinned(snapshot))

    def test_xcode_caches_do_not_inherit_workflow_holds_but_keep_user_pins_and_locks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            snapshot = root / 'mobile_build/.tools/build-manager/snapshots' / ('a' * 64)
            snapshot.mkdir(parents=True)
            durable_hold(snapshot, 'paused-fixture')
            cache_root = root / 'caches'; cache = cache_root / 'one'; cache.mkdir(parents=True)
            (cache / 'info.plist').write_bytes(plistlib.dumps(dict(WorkspacePath=str(snapshot / 'mobile_build/build/App.xcodeproj'))))
            os.utime(cache, (1, 1))
            spec = storage_group(root, cache_root=cache_root, processes='', now=100000)
            self.assertTrue(spec['eligible'](cache))
            with workspace_lock(snapshot.with_suffix('.lock')):
                self.assertEqual(prune(**spec, keep=0, age_days=0), [])
            (snapshot / '.keep').touch()
            self.assertFalse(spec['eligible'](cache))
            (snapshot / '.keep').unlink()
            self.assertEqual(prune(**spec, keep=0, age_days=0, apply=True), [str(cache)])
            self.assertTrue(snapshot.exists())

    def test_device_cache_removal_preserves_package_and_held_recipe_and_honors_active_lock(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / 'mobile_build/.tools/build-manager/workspaces/devices/ios' / ('b' * 32)
            (workspace / 'build/derived').mkdir(parents=True)
            (workspace / 'build/derived/object').write_text('rebuildable')
            package = workspace / 'app.zip'; package.write_bytes(b'reviewed-package')
            data = dict(schema=1, workspace=str(workspace), platform='ios', package=str(package), package_sha256='a' * 64)
            (workspace / 'recipe.json').write_text(json.dumps(data))
            (workspace / 'prepared.json').write_text(json.dumps(data))
            os.utime(workspace / 'prepared.json', (1, 1))
            durable_hold(workspace, 'paused-fixture')
            group, spec = next(device_intermediates(root))
            with workspace_lock(workspace / 'operation.lock'):
                self.assertEqual(prune(**spec, keep=0, age_days=0), [])
            (workspace / '.keep').touch()
            self.assertFalse(spec['eligible'](workspace / 'build'))
            (workspace / '.keep').unlink()
            result = delete_storage(root, {group: ['build']})
            self.assertEqual(result['removed'], [str(workspace / 'build')])
            self.assertEqual(package.read_bytes(), b'reviewed-package')
            self.assertTrue((workspace / 'prepared.json').exists())
            self.assertTrue(pinned(workspace))
            data['package'] = str(root / 'foreign.zip')
            (workspace / 'prepared.json').write_text(json.dumps(data))
            (workspace / 'build').mkdir()
            self.assertFalse(spec['eligible'](workspace / 'build'))

    def test_external_probe_requires_adoption_and_marker_identity_and_idle_process_inventory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            probe = root / 'test-results/probe'; probe.mkdir(parents=True)
            (probe / 'result.log').write_text('evidence')
            self.assertEqual(list(extras.directory_groups(root)), [])
            extras.enroll(root, 'directory', str(probe))
            _, spec = next(extras.directory_groups(root))
            with patch.object(extras.subprocess, 'check_output', return_value=''):
                self.assertEqual(prune(**spec, keep=0, age_days=7), [])
                self.assertEqual(prune(**spec, keep=0, age_days=0), [str(probe)])
            with patch.object(extras.subprocess, 'check_output', return_value='xcodebuild ' + str(probe)):
                self.assertFalse(spec['eligible'](probe))
            with patch.object(extras.subprocess, 'check_output', side_effect=PermissionError):
                self.assertFalse(spec['eligible'](probe))
            (probe / extras.MARKER).write_text('{}')
            self.assertFalse(spec['eligible'](probe))
            with self.assertRaises(ValueError):
                extras.enroll(root, 'directory', str(root))

    def test_recovery_only_removes_owned_lease_and_keeps_personal_simulator(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); home = root / 'home'
            workspace = extras.private(root) / 'workspaces/ios'
            lease = workspace / ('simulators-' + uuid4().hex) / 'iphone-lease.json'
            lease.parent.mkdir(parents=True)
            device, personal = str(uuid4()), str(uuid4())
            name = 'Build Manager iphone ' + uuid4().hex
            lease.write_text(json.dumps(dict(device=device, name=name)))
            owned = home / 'Library/Developer/CoreSimulator/Devices' / device
            foreign = owned.parent / personal
            owned.mkdir(parents=True); foreign.mkdir()
            (foreign / 'personal-data').write_text('preserve')
            with patch.object(Path, 'home', return_value=home), patch('build_manager.apple_simulators.AppleSimulators') as clients:
                rows = extras.simulator_inventory(root)
                self.assertEqual([row['name'] for row in rows], [device])
                with workspace_lock(workspace / 'operation.lock'):
                    result = extras.delete_simulators(root, [device])
                    self.assertTrue(result['skipped'])
                    clients.return_value.remove.assert_not_called()
                result = extras.delete_simulators(root, [personal])
                self.assertTrue(result['skipped'])
                clients.return_value.remove.side_effect = lambda device, name: shutil.rmtree(owned)
                result = extras.delete_simulators(root, [device])
                clients.return_value.remove.assert_called_once_with(device, name)
                self.assertFalse(lease.exists())
                self.assertEqual((foreign / 'personal-data').read_text(), 'preserve')
