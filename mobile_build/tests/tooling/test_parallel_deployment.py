"""Verify actual process overlap, output isolation and the batch workspace lock."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mobile_build.deployment import test_devices as devices
from mobile_build.deployment.deployment_paths import WORKSPACE_ENV, prepare_workspace


class ParallelDeploymentTests(unittest.TestCase):
    def targets(self):
        return [dict(platform=p, id=p, name=p, online=True) for p in ('Android', 'iOS')]

    def test_actual_workers_overlap_and_use_separate_workspaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'mobile_build'
            (root / 'deployment').mkdir(parents=True)
            (root / '__init__.py').touch()
            (root / 'deployment/__init__.py').touch()
            (root / 'deployment/test_devices.py').write_text(
                'import json, os, pathlib, sys, time\n'
                'platform = sys.argv[sys.argv.index("--worker-platform") + 1]\n'
                f'workspace = pathlib.Path(os.environ[{WORKSPACE_ENV!r}])\n'
                'other = workspace.parent / ("ios" if platform == "Android" else "android")\n'
                '(workspace / "ready").touch()\n'
                'deadline = time.monotonic() + 5\n'
                'while not (other / "ready").exists():\n'
                '    if time.monotonic() > deadline: raise RuntimeError("Workers did not overlap")\n'
                '    time.sleep(0.01)\n'
                '(workspace / "payload").mkdir()\n'
                '(workspace / "payload/platform").write_text(platform)\n'
                'print(platform + " finished", flush=True)\n')
            with patch.object(devices, 'ROOT', root), patch.object(devices, 'WORKSPACES', root / 'workspaces'):
                devices.deploy_devices(self.targets())
            for platform in ('Android', 'iOS'):
                workspace = root / 'workspaces' / platform.lower()
                self.assertEqual((workspace / 'payload/platform').read_text(), platform)
                self.assertIn(platform + ' finished', (workspace / 'logs/deployment.log').read_text())
                self.assertEqual(json.loads((workspace / 'targets.json').read_text())[0]['platform'], platform)
            self.assertFalse((root / 'payload').exists())

    def test_platform_failure_waits_for_other_worker_and_reports_failure(self):
        completed = []
        def run(platform, targets):
            completed.append(platform)
            if platform == 'Android':
                raise RuntimeError('Android build failed')
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(devices, 'WORKSPACES', Path(directory)), patch.object(devices, 'run_platform', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'Deployment failed for: Android'):
                devices.deploy_devices(self.targets())
        self.assertCountEqual(completed, ['Android', 'iOS'])

    def test_second_batch_cannot_modify_active_workspaces(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root / 'deploy.lock').open('a') as lock, \
                    patch.object(devices, 'WORKSPACES', root), patch.object(devices, 'run_platform') as run:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, 'already running'):
                    devices.deploy_devices(self.targets())
                run.assert_not_called()

    def test_workspace_copies_build_inputs_but_not_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'mobile_build'
            (root / 'native_tests').mkdir(parents=True)
            (root / 'native_tests/probe.py').write_text('pass\n')
            (root / 'pyproject.toml').write_text('[tool.briefcase]\n')
            (root / '.device.json').write_text('private')
            (root / '.testflight-auth.json').write_text('private')
            workspace = root / '.deploy-workspaces/android'
            with patch.dict(os.environ, {WORKSPACE_ENV: str(workspace)}):
                self.assertEqual(prepare_workspace(root), workspace.resolve())
            self.assertTrue((workspace / 'build').is_dir())
            self.assertEqual((workspace / 'pyproject.toml').read_text(), (root / 'pyproject.toml').read_text())
            self.assertTrue((workspace / 'native_tests/probe.py').is_file())
            self.assertFalse((workspace / '.device.json').exists())
            self.assertFalse((workspace / '.testflight-auth.json').exists())

    def test_child_modules_route_build_paths_but_keep_canonical_signing_config(self):
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'isolated'
            code = ('import json; from mobile_build.deployment import android_deploy as a, device_tools as i; from mobile_build import cloud_build as c; '
                    'print(json.dumps([str(a.PROJECT), str(i.PROJECT), str(i.DERIVED), str(i.CONFIG), '
                    'str(c.output_root(c.ROOT))]))')
            result = subprocess.run([sys.executable, '-c', code], cwd=repo,
                                    env=dict(os.environ, **{WORKSPACE_ENV: str(workspace)}),
                                    capture_output=True, text=True, check=True, timeout=20)
            android, ios, derived, config, cloud = json.loads(result.stdout)
            for path in (android, ios, derived, cloud):
                self.assertTrue(Path(path).is_relative_to(workspace.resolve()))
            self.assertEqual(Path(config), repo / 'mobile_build/.device.json')


if __name__ == '__main__':
    unittest.main()
