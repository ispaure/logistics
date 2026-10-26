import json
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile_build.deployment import firebase_deploy as beta
from mobile_build.deployment import deploy_all as all_deploy


class FirebaseDeployTests(unittest.TestCase):
    def test_group_display_name_resolves_to_actual_alias_without_guessing(self):
        groups = [dict(name='projects/123/groups/friends-beta', displayName='Friends')]
        self.assertEqual(beta.resolve_group(groups, 'FRIENDS'), 'friends-beta')
        self.assertEqual(beta.resolve_group(groups, 'friends-beta'), 'friends-beta')
        with self.assertRaises(ValueError):
            beta.resolve_group(groups, 'Family')
        with self.assertRaises(ValueError):
            beta.resolve_group(groups * 2, 'Friends')

    def test_preflight_verifies_package_before_group_or_build(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'firebase-distribution.json').write_text(json.dumps(dict(
                app_id='1:123:android:abc', bundle_id=beta.android.BUNDLE, group='Friends')))
            answers = [[{}], [dict(projectId='project', projectNumber='123')],
                       [dict(appId='1:123:android:abc', packageName='wrong.package')]]
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'firebase_json', side_effect=answers) as query:
                with self.assertRaisesRegex(ValueError, 'package'):
                    beta.preflight('firebase')
            self.assertEqual(query.call_count, 3)

    def test_missing_signing_key_never_creates_replacement(self):
        with TemporaryDirectory() as directory:
            private = Path(directory)
            (private / 'signing.json').write_text('{"password":"test"}')
            with patch.object(beta, 'PRIVATE', private), patch.object(beta.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'Restore'):
                    beta.signing({})
            run.assert_not_called()

    def test_build_counter_never_reuses_reserved_or_existing_build(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'; private.mkdir()
            (private / 'build.json').write_text('{"last_build":2090000000}')
            (root / 'build/firebase/2090000005').mkdir(parents=True)
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private):
                self.assertEqual(beta.reserve_build(), 2090000006)
                self.assertEqual(beta.reserve_build(), 2090000007)

    def test_declining_upload_keeps_build_and_does_not_distribute(self):
        with TemporaryDirectory() as directory:
            with patch.object(beta, 'PRIVATE', Path(directory)), \
                    patch.object(beta, 'firebase_cli', return_value='firebase'), \
                    patch.object(beta, 'preflight', return_value=({'app_id': 'test'}, 'friends')), \
                    patch.object(beta, 'build', return_value=(Path('beta.apk'), Path('notes.txt'))), \
                    patch('builtins.input', return_value='n'), \
                    patch.object(beta.subprocess, 'run') as run, patch.object(beta.sys, 'argv', ['beta']):
                beta.main()
            run.assert_not_called()

    def test_preview_uses_utc_floor_without_creating_counter_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            with patch.object(beta, 'datetime') as clock, patch.dict(os.environ, {}, clear=True):
                clock.now.return_value = datetime(2026, 1, 2, tzinfo=timezone.utc)
                self.assertEqual(beta.next_build(root, private), 202601021)
                clock.now.assert_called_once_with(timezone.utc)
            self.assertFalse(private.exists())

    def test_all_android_histories_and_legacy_writers_remain_inputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'; private.mkdir()
            legacy = private / 'build.json'
            legacy.write_text('{"last_build":2090000000}')
            local = root / '.tools/android-deployment-build.json'
            history = root / 'history'
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private), \
                    patch.dict(os.environ, {'LOGISTICS_BUILD_HISTORY': str(history)}):
                self.assertEqual(beta.next_build(), 2090000001)
                (root / 'build/firebase/2090000001').mkdir(parents=True)
                self.assertEqual(beta.next_build(), 2090000002)
                local.parent.mkdir(); local.write_text('{"last_build":2090000002}')
                self.assertEqual(beta.next_build(), 2090000003)
                (history / 'firebase/2090000003').mkdir(parents=True)
                self.assertEqual(beta.next_build(), 2090000004)
                self.assertEqual(legacy.read_text(), '{"last_build":2090000000}')
                self.assertFalse((private / 'build-manager-counter.json').exists())
                self.assertEqual(beta.reserve_build(), 2090000004)
                self.assertEqual(json.loads(legacy.read_text()), {'last_build': 2090000004})
                # An older deployment machine can still advance the original record.
                legacy.write_text('{"last_build":2090000010}')
                self.assertEqual(beta.reserve_build(), 2090000011)
                legacy.unlink()
                self.assertEqual(beta.next_build(), 2090000012)
                self.assertEqual(beta.reserve_build(), 2090000012)
            self.assertEqual(json.loads(legacy.read_text()), {'last_build': 2090000012})
            if os.name != 'nt':
                for name in ('build.json', 'build-manager-counter.json'):
                    self.assertEqual((private / name).stat().st_mode & 0o777, 0o600)

    def test_overrides_limits_and_failed_reservations_preserve_counters(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'; private.mkdir()
            legacy = private / 'build.json'
            legacy.write_text('{"last_build":2090000000}')
            counter = private / 'build-manager-counter.json'
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private):
                for value in ('bad', '2090000000', '2100000001'):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        beta.reserve_build(value)
                    self.assertFalse(counter.exists())
                    self.assertEqual(json.loads(legacy.read_text())['last_build'], 2090000000)
                self.assertEqual(beta.reserve_build('2090000010'), 2090000010)
                self.assertEqual(beta.reserve_build('2100000000'), 2100000000)
                before = (legacy.read_bytes(), counter.read_bytes())
                with self.assertRaises(ValueError):
                    beta.reserve_build()
                self.assertEqual((legacy.read_bytes(), counter.read_bytes()), before)

    def test_interrupted_compatibility_write_cannot_reuse_reserved_number(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'; private.mkdir()
            legacy = private / 'build.json'
            legacy.write_text('{"last_build":2090000000}')
            with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private):
                original = Path.replace
                def replace(path, target):
                    if Path(target) == legacy:
                        raise OSError('interrupted mirror')
                    return original(path, target)
                with patch.object(Path, 'replace', replace), self.assertRaisesRegex(OSError, 'mirror'):
                    beta.reserve_build()
                self.assertEqual(legacy.read_text(), '{"last_build":2090000000}')
                self.assertFalse(list(private.glob('.build-counter-*')))
                self.assertEqual(beta.next_build(), 2090000002)
                self.assertEqual(beta.reserve_build(), 2090000002)

    def test_existing_lock_still_excludes_other_processes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            private = root / 'private'
            code = ('from build_manager.locking import workspace_lock; import sys\n'
                    'with workspace_lock(sys.argv[1]):\n'
                    ' print("locked", flush=True)\n'
                    ' sys.stdin.readline()\n')
            with subprocess.Popen([sys.executable, '-c', code, str(private / 'build-counter.lock')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as process:
                try:
                    self.assertEqual(process.stdout.readline().strip(), 'locked')
                    with patch.object(beta, 'ROOT', root), patch.object(beta, 'PRIVATE', private):
                        with self.assertRaisesRegex(RuntimeError, 'owns this workspace'):
                            beta.reserve_build()
                    self.assertFalse((private / 'build-manager-counter.json').exists())
                    self.assertFalse((private / 'build.json').exists())
                finally:
                    process.communicate('\n', timeout=10)
                self.assertEqual(process.returncode, 0)

    def test_all_deployments_stop_or_continue_after_failure(self):
        result = type('Result', (), {'returncode': 1})()
        with patch.object(all_deploy.subprocess, 'run', return_value=result) as run:
            self.assertEqual(all_deploy.deploy_all(ask=lambda _: 'n'), 1)
            self.assertEqual(run.call_count, 1)
        with patch.object(all_deploy.subprocess, 'run', return_value=result) as run:
            self.assertEqual(all_deploy.deploy_all(ask=lambda _: 'y'), 1)
            self.assertEqual(run.call_count, 4)
