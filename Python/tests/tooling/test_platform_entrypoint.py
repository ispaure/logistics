"""Direct CI entry point must bootstrap shared imports in its own interpreter."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
inventory.desktop_checks = lambda system, results: [('shared-import',
    ['-c', 'from commonUtils.runtime.streams import file_sha256; print("shared import passed")'], 30)]
sys.modules['logistics_build.validation_plans'] = inventory
sys.argv = [sys.argv[1], '--results-dir', sys.argv[2]]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        with TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-c', code,
                str(root / 'Python/tests/run_platform_checks.py'), directory],
                cwd=directory, capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('shared-import: PASS', result.stdout)
            self.assertTrue((Path(directory) / 'summary.json').is_file())
