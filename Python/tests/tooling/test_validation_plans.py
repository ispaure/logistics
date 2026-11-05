"""Shared plans retain discovery, platform coverage and gate order."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build.validation_plans import desktop_checks, inventory


class ValidationPlanTests(unittest.TestCase):
    def test_desktop_plan_preserves_existing_commands_and_budgets(self):
        import json
        root = Path(__file__).resolve().parents[3]
        declared = json.loads((root / 'build-tests.json').read_text())['suites']
        suites = [dict(row, timeout=row.get('timeout', 1800),
                       directory=(row.get('owner', '') + '/' + row['directory']).lstrip('/'))
                  for row in declared if 'desktop' in row['groups']]
        # Pin verification belongs to the manager manifest contracts and preflight.
        # This case owns command construction, platform differences and budgets.
        with patch('build_manager.test_manifest.discover', return_value=suites):
            posix = desktop_checks('Darwin', Path('reports'))
            windows = desktop_checks('Windows', Path('reports'))
            linux = desktop_checks('Linux', Path('reports'))
        self.assertEqual([p[0] for p in posix], ['test-structure', 'commonutils.smoke', 'logistics.smoke',
                         'commonutils', 'logistics', 'compression-parity'])
        self.assertEqual([p[2] for p in posix], [120, 1800, 1800, 1800, 1800, 600])
        self.assertEqual(linux, posix)
        windows_full = [windows[0], *windows[2:]]
        self.assertEqual([(name, command) for name, command, _ in windows_full],
                         [(name, command) for name, command, _ in posix])
        self.assertEqual([timeout for _, _, timeout in windows_full],
                         [120, 1800, 1800, 1800, 2100, 600])
        self.assertEqual({name for (name, _, timeout), (_, _, previous) in zip(windows_full, posix)
                          if timeout != previous}, {'logistics'})
        from tests.runner_settings import ISOLATED_FILE_TIMEOUT
        self.assertEqual(ISOLATED_FILE_TIMEOUT, 300)
        self.assertEqual(windows[1], ('windows-native-ui', ['Python/tests/native_ui_smoke.py'], 60))
        for name, command, _ in posix[1:5]:
            self.assertIn('--isolate-modules', command)
            if name.endswith('.smoke'):
                self.assertEqual(command[-4:], ['--profile', 'smoke', '--mode', 'fast'])
            else:
                self.assertNotIn('--profile', command)  # Full coverage stays the default.

    def test_windows_full_suite_floor_never_shortens_larger_declared_budget(self):
        suites = [dict(id='logistics', directory='Python/tests', timeout=2400,
                       smoke_args=['--profile', 'smoke', '--mode', 'fast'])]
        with patch('build_manager.test_manifest.discover', return_value=suites):
            checks = desktop_checks('Windows', Path('reports'))
        budgets = {name: timeout for name, _, timeout in checks}
        self.assertEqual(budgets['logistics'], 2400)
        self.assertEqual(budgets['logistics.smoke'], 2400)
        self.assertNotIn('manager-contracts', budgets)

    def test_full_logistics_gates_keep_consumer_contracts_without_implicit_sdk_self_tests(self):
        root = Path(__file__).resolve().parents[3]
        manifest = __import__('json').loads((root / 'build-tests.json').read_text())
        rows = [dict(row, timeout=row.get('timeout', 1800),
                     directory=(row.get('owner', '') + '/' + row['directory']).lstrip('/'))
                for row in manifest['suites'] if 'desktop' in row['groups']]
        with patch('build_manager.test_manifest.discover', return_value=rows):
            for system in ('Darwin', 'Linux', 'Windows'):
                with self.subTest(system=system):
                    checks = desktop_checks(system, Path('reports'))
                    commands = {name: command for name, command, _ in checks}
                    self.assertEqual(commands['commonutils'],
                        ['Python/tests/run_regressions.py', 'Python/commonUtils/tests', '--isolate-modules'])
                    # Full Python/tests includes the project-owned tooling subtree:
                    # adapter/journey/Executor, retained artifacts and bootstrap tests.
                    self.assertEqual(commands['logistics'],
                        ['Python/tests/run_regressions.py', 'Python/tests', '--isolate-modules'])
                    self.assertIn('test-structure', commands)
                    self.assertIn('compression-parity', commands)
                    self.assertFalse(any('build_manager.contracts' in argv for argv in commands.values()))
                    if system == 'Windows':
                        self.assertIn('windows-native-ui', commands)
        suites = {row['name']: row for row in inventory(root)['suites']}
        self.assertFalse(suites['manager']['required'])
        self.assertEqual(suites['manager']['entry'], 'python -m build_manager.contracts')
        for name in ('shared-host', 'static', 'desktop', 'mobile-host', 'release-tooling',
                     'native-ios', 'native-android', 'runtime'):
            self.assertTrue(suites[name]['required'], name)

    def test_compression_retries_get_fresh_attempts_and_preserve_previous_evidence(self):
        import importlib.util
        from tempfile import TemporaryDirectory
        path = Path(__file__).parents[1] / 'parity_workspace.py'
        spec = importlib.util.spec_from_file_location('parity_workspace_fixture', path)
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = helper.comparison_workspace(root)
            (first / 'comparison.json').write_text('previous evidence')
            (first / 'before').mkdir()
            second = helper.comparison_workspace(root)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, root)
            self.assertEqual(second.parent, root)
            self.assertFalse(any(second.iterdir()))
            self.assertEqual((first / 'comparison.json').read_text(), 'previous evidence')

    def test_inventory_matches_actual_recursive_test_discovery(self):
        root = Path(__file__).resolve().parents[3]
        rows = {r['name']: r for r in inventory(root)['suites']}
        for suite, owner in [('desktop', 'Python/tests'), ('mobile-host', 'mobile_build/tests')]:
            expected = sorted(str(p.relative_to(root)).replace('\\', '/') for p in (root / owner).rglob('test*.py'))
            self.assertEqual(rows[suite]['test_files'], expected)
            self.assertEqual(rows[suite]['file_count'], len(expected))
        self.assertEqual(rows['native-ios']['devices'], ['iphone', 'duo', 'ipad'])
        self.assertTrue(rows['native-ios']['required'])
        self.assertEqual(rows['native-ios']['case_ids'], rows['native-android']['case_ids'])
        self.assertIn('native_rotation_safe_areas', rows['native-ios']['case_ids'])
        self.assertGreater(len(rows['runtime']['case_ids']), 40)
        self.assertFalse(rows['investigations']['required'])

    def test_package_manager_preparation_is_bounded_and_does_not_ignore_errors(self):
        root = Path(__file__).resolve().parents[3]
        for workflow in ('mobile-runtime.yml',):
            lines = (root / '.github/workflows' / workflow).read_text().splitlines()
            apt = [line.strip() for line in lines if 'sudo apt-get' in line]
            self.assertEqual(len(apt), 2)
            self.assertTrue(all(line.startswith('timeout --kill-after=10s ') for line in apt))
            self.assertTrue(all('|| true' not in line for line in apt))

    def test_fedora_is_the_only_declared_linux_distribution(self):
        root = Path(__file__).resolve().parents[3]
        rows = {row['name']: row for row in inventory(root)['suites']}
        for name in ('shared-host', 'static', 'desktop', 'mobile-host', 'release-tooling', 'manager', 'bridge'):
            self.assertIn('fedora', rows[name]['platforms'])
            self.assertNotIn('ubuntu', rows[name]['platforms'])
        workflow = (root / '.github/workflows/archive-platform-checks.yml').read_text()
        desktop = workflow.split('  desktop:\n', 1)[1].split('  fedora:\n', 1)[0]
        self.assertNotIn('ubuntu-latest', desktop)
        self.assertIn("inputs.target != 'linux'", desktop)
        self.assertIn("inputs.target == 'linux'", workflow.split('  fedora:\n', 1)[1])
        fedora = (root / 'Python/tests/platform/fedora.sh').read_text()
        self.assertIn('Python/tests/run_platform_checks.py --install --prepare-only', fedora)
        self.assertIn('unittest discover -s .github/scripts', fedora)


@unittest.skipUnless(os.name == 'posix', 'Fedora launcher requires a POSIX shell')
class FedoraLauncherTests(unittest.TestCase):
    def run_launcher(self, failure):
        script = Path(__file__).resolve().parents[1] / 'platform/fedora.sh'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / 'bin'
            tools.mkdir()
            interpreter = tools / 'fixture-python'
            interpreter.write_text("#!" + sys.executable + "\n" + r'''import os
from pathlib import Path
import sys
args = ' '.join(sys.argv[1:])
if sys.argv[1] == '-c':
    print('/fixture/certifi.pem')
else:
    with Path(os.environ['FIXTURE_LOG']).open('a') as stream:
        stream.write(args + '\n')
    if '--prepare-only' in args:
        step = 'dependencies'
    elif 'run_platform_checks.py' in args:
        step = 'platform'
        assert os.environ['LOGISTICS_REQUIRE_LOCALCRYPT_TESTS'] == '1'
        assert os.environ['SSL_CERT_FILE'] == '/fixture/certifi.pem'
    elif 'unittest' in args:
        step = 'release-tooling'
    else:
        step = 'manager'
    sys.exit(7 if os.environ['FIXTURE_FAILURE'] == step else 0)
''')
            uv = tools / 'uv'
            uv.write_text("#!" + sys.executable + "\n" + r'''import os
from pathlib import Path
import shutil
import sys
venv = Path(sys.argv[-1])
(venv / 'bin').mkdir(parents=True)
shutil.copyfile(os.environ['FIXTURE_PYTHON'], venv / 'bin/python')
(venv / 'bin/python').chmod(0o755)
''')
            (tools / 'timeout').write_text('#!/bin/sh\nshift 2\nexec "$@"\n')
            (tools / 'git').write_text('#!/bin/sh\nexit 0\n')
            for tool in tools.iterdir():
                tool.chmod(0o755)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ['PATH'],
                       TMPDIR=str(root), FIXTURE_LOG=str(root / 'calls'),
                       FIXTURE_PYTHON=str(interpreter), FIXTURE_FAILURE=failure)
            result = subprocess.run(['bash', str(script)], cwd=root, env=env,
                                    capture_output=True, text=True, timeout=15)
            calls = (root / 'calls').read_text()
            self.assertFalse(list(root.glob('logistics-platform.*')), 'Temporary environment leaked')
            timing = (root / 'test-results/fedora-setup.log').read_text()
            return result, calls, timing

    def test_platform_failure_still_runs_release_tooling_and_retains_failure(self):
        result, calls, timing = self.run_launcher('platform')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('unittest discover', calls)
        self.assertIn('platform finished', timing)
        self.assertIn('(exit 7)', timing)

    def test_release_tooling_failure_fails_launcher(self):
        result, calls, _ = self.run_launcher('release-tooling')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('run_platform_checks.py', calls)

    def test_setup_failure_stops_before_validation_and_cleans_environment(self):
        result, calls, _ = self.run_launcher('dependencies')
        self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
        self.assertNotIn('unittest discover', calls)
        self.assertEqual(calls.count('run_platform_checks.py'), 1)

    def test_successful_preparation_and_both_suites_pass(self):
        result, _, timing = self.run_launcher('')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('release-tooling finished', timing)
