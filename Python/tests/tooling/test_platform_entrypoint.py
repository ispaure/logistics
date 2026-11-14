"""Direct CI entry point must bootstrap shared imports in its own interpreter."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class PlatformEntrypointTests(unittest.TestCase):
    def test_direct_entrypoint_runs_real_manager_without_inherited_pythonpath(self):
        root = Path(__file__).resolve().parents[3]
        # Keep the actual manager/Executor and one real child check. Only replace
        # the long inventory so this verifies bootstrap rather than rerunning CI.
        code = '''
import runpy, sys, types
assert sys.flags.isolated and sys.flags.utf8_mode
inventory = types.ModuleType('logistics_build.validation_plans')
child = (
    'import os; from commonUtils.runtime.streams import file_sha256; '
    'assert not any(k in os.environ for k in ("BUILD_MANAGER_TEST_PLATFORM", '
    '"BUILD_MANAGER_TEST_WORKERS", "BUILD_MANAGER_RESERVED_TEST_WORKERS")); '
    'print("shared import passed")'
)
inventory.desktop_checks = lambda system, results: [('shared-import', ['-c', child], 30)]
sys.modules['logistics_build.validation_plans'] = inventory
sys.argv = [sys.argv[1], '--results-dir', sys.argv[2]]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        with TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code,
                str(root / 'Python/tests/run_platform_checks.py'), directory],
                cwd=directory, capture_output=True, text=True, encoding='utf-8', timeout=60,
                env=dict(os.environ, BUILD_MANAGER_TEST_PLATFORM='ios', BUILD_MANAGER_TEST_WORKERS='1',
                         BUILD_MANAGER_RESERVED_TEST_WORKERS='1'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('shared-import: PASS', result.stdout)
            self.assertTrue((Path(directory) / 'summary.json').is_file())

    def test_desktop_entrypoint_keeps_smoke_gating_and_regression_diagnostics(self):
        root = Path(__file__).resolve().parents[3]
        code = '''
import runpy, sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path[:0] = [str(root), str(root / 'Python')]
from build_manager import resources, test_manifest, test_workers
from logistics_build import validation_plans
fixture = Path(sys.argv[2])
# This child tests stage order. It needs an independent pool because the
# enclosing Desktop test already holds the production macOS worker slots.
private = fixture / 'manager'
resources.config_directory = test_workers.config_directory = lambda: private
test_workers.configure(dict(per_platform=1, host=1))
test_manifest.discover = lambda *_: [dict(
    id='fixture', directory=str(fixture), timeout=30,
    smoke_args=['--profile', 'smoke', '--mode', 'fast'])]
actual_checks = validation_plans.desktop_checks
validation_plans.desktop_checks = lambda system, results: [
    check for check in actual_checks(system, results) if check[0] in ('fixture.smoke', 'fixture')]
sys.argv = [str(root / 'Python/tests/run_platform_checks.py'), '--results-dir', str(fixture / 'results')]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        cases = '''
from pathlib import Path
from commonUtils.testing.stages import TestStage, stage
from unittest import TestCase
TEST_STAGE = TestStage.REGRESSION
class Fixture(TestCase):
    def record(self, stage):
        with Path(__file__).with_name('observed').open('a') as output:
            output.write(stage + '\\n')
        self.assertNotEqual(stage, FAILURE)

    @stage(TestStage.SMOKE)
    def test_smoke(self):
        self.record('smoke')

    def test_regression(self):
        self.record('regression')

    @stage(TestStage.EXTENDED)
    def test_extended(self):
        self.record('extended')
'''
        for failure in ('', 'smoke', 'regression'):
            with self.subTest(failure=failure), TemporaryDirectory() as directory:
                fixture = Path(directory)
                (fixture / 'test_stage_fixture.py').write_text(f'FAILURE = {failure!r}\n' + cases)
                result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code, str(root), directory],
                                        cwd=directory, capture_output=True, text=True, encoding='utf-8', timeout=60,
                                        env=dict(os.environ, LOGISTICS_REUSE_TEST_RESULTS='off'))
                self.assertEqual(result.returncode, int(bool(failure)), result.stdout + result.stderr)
                observed_path = fixture / 'observed'
                self.assertTrue(observed_path.is_file(), result.stdout + result.stderr)
                observed = observed_path.read_text().splitlines()
                report = json.loads((fixture / 'results/summary.json').read_text())
                if failure == 'smoke':
                    self.assertEqual(observed, ['smoke'])
                    self.assertEqual(report['not_run'], [{'name': 'fixture', 'reason': 'Preflight/smoke gate failed'}])
                    self.assertEqual([row['status'] for row in report['checks']], ['failed'])
                else:
                    self.assertEqual(observed, ['smoke', 'regression', 'extended'])
                    self.assertEqual([row['status'] for row in report['checks']],
                                     ['passed', 'failed' if failure else 'passed'])
