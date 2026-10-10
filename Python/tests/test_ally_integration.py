"""Public regression coverage uses fake sibling checkouts, never private source."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.ally_integration import activate, is_active


class AllyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.logistics = self.root / 'logistics'
        self.ally = self.root / 'ally-tools'
        (self.logistics / 'Python/features').mkdir(parents=True)
        self.source = self.ally / 'Python/ally_feature'
        self.source.mkdir(parents=True)
        (self.source / '__init__.py').write_text('')
        self.link = self.logistics / 'Python/features/emulation'
        env = patch.dict(os.environ, {}, clear=False)
        env.start(); self.addCleanup(env.stop)
        os.environ.pop('LOGISTICS_ALLY_ROOT', None)

    @unittest.skipIf(os.name == 'nt', 'Unix symlink behavior')
    def test_link_created_reused_and_updated(self):
        activate(self.logistics, self.ally)
        self.assertEqual(self.link.resolve(), self.source)
        self.assertTrue(is_active(self.link))
        activate(self.logistics, self.ally)
        self.link.unlink()
        self.link.symlink_to(self.root / 'missing')
        activate(self.logistics, self.ally)
        self.assertEqual(self.link.resolve(), self.source)

    def test_real_directory_and_missing_source_are_not_overwritten(self):
        self.link.mkdir(); marker = self.link / 'keep'; marker.write_text('keep')
        with self.assertRaisesRegex(RuntimeError, 'Refusing'):
            activate(self.logistics, self.ally)
        self.assertEqual(marker.read_text(), 'keep')
        (self.source / '__init__.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            activate(self.logistics, self.ally)

    def test_discovery_requires_active_matching_sibling(self):
        from features import registry
        (self.logistics / 'Python/features/public').mkdir()
        (self.logistics / 'Python/features/public/__init__.py').write_text('')
        with patch.object(registry, '__file__', str(self.logistics / 'Python/features/registry.py')):
            activate(self.logistics, self.ally)
            self.assertEqual(registry.get_feature_names(), ['emulation', 'public'])
            os.environ.pop('LOGISTICS_ALLY_ROOT')
            self.assertEqual(registry.get_feature_names(), ['public'])
            os.environ['LOGISTICS_ALLY_ROOT'] = str(self.root / 'other')
            self.assertEqual(registry.get_feature_names(), ['public'])

    @unittest.skipIf(os.name == 'nt', 'Mock Windows command on a Unix host')
    def test_windows_uses_quoted_non_admin_junction_command(self):
        with patch('services.ally_integration.os.name', 'nt'), patch('services.ally_integration.subprocess.run') as run:
            # Path construction chooses a platform class from os.name; retain host paths.
            from pathlib import PosixPath
            if os.name == 'nt':
                with patch('services.ally_integration.Path', PosixPath):
                    activate(self.logistics, self.ally)
            else:
                activate(self.logistics, self.ally)
        self.assertEqual(run.call_args.args[0][-1], f'mklink /J "{self.link}" "{self.source}"')
        self.assertTrue(run.call_args.kwargs['check'])

    @unittest.skipIf(os.name == 'nt', 'Bash launchers')
    def test_root_launchers_select_environment_and_propagate_exit_status(self):
        actual = Path(__file__).resolve().parents[2]
        # This test must run from Logistics/Python/tests.
        for name, shared in [('LaunchLogistics_MAC.command', 'LaunchPythonProject_MAC.command'),
                             ('LaunchLogistics_LINUX_UV.sh', 'LaunchPythonProject_LINUX_UV.sh')]:
            with self.subTest(launcher=name):
                sandbox = self.root / name
                logistics = sandbox / 'logistics'; logistics.mkdir(parents=True)
                launcher = logistics / name
                shutil.copy2(actual / name, launcher)
                (logistics / 'launch_config.ini').write_text('[Launch]\ncommonutils_root = Python/commonUtils\npause_after_completed = false\n')
                shared_dir = logistics / 'Python/commonUtils/launchers'; shared_dir.mkdir(parents=True)
                (shared_dir / shared).write_text('#!/bin/bash\nprintf "%s\\n" "$1" "$2" "$LOGISTICS_ROOT" "${LOGISTICS_ALLY_ROOT-unset}"\nexit 7\n')
                env = dict(os.environ, LOGISTICS_ALLY_ROOT='stale')
                result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 7)
                self.assertEqual(result.stdout.splitlines(), [str(logistics), str(logistics / 'launch_config.ini'), str(logistics), 'unset'])
                ally = sandbox / 'ally-tools'; (ally / 'Python/ally_feature').mkdir(parents=True)
                (ally / 'Python/ally_feature/__init__.py').write_text('')
                (ally / 'Python/pyproject.toml').write_text('[project]')
                (ally / 'logistics_launch.ini').write_text('[Launch]')
                lock = ally / 'Python/uv.lock'; lock.write_text('preserve')
                result = subprocess.run(['bash', str(launcher)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 7)
                self.assertEqual(result.stdout.splitlines()[1:], [str(ally), str(ally / 'logistics_launch.ini'), str(logistics), 'unset'])
                self.assertEqual(lock.read_text(), 'preserve')
                (ally / 'logistics_launch.ini').unlink()
                result = subprocess.run(['bash', str(launcher)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
