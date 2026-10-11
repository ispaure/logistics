"""Isolated GUI checks must run every module and preserve all failure statuses."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


RUNNER = Path(__file__).with_name('run_regressions.py')


class RegressionRunnerTests(unittest.TestCase):
    def run_modules(self, directory):
        return subprocess.run([sys.executable, str(RUNNER), str(directory), '--isolate-modules'],
                              capture_output=True, text=True, timeout=30)

    def test_modules_have_independent_process_state(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_first.py').write_text(
                "import os, unittest\n"
                "class First(unittest.TestCase):\n"
                " def test_state(self): os.environ['LOGISTICS_TEST_PROCESS_STATE'] = 'changed'\n")
            (root / 'test_second.py').write_text(
                "import os, unittest\n"
                "class Second(unittest.TestCase):\n"
                " def test_state(self): self.assertNotIn('LOGISTICS_TEST_PROCESS_STATE', os.environ)\n")
            result = self.run_modules(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Isolated test files: 2; failures: 0', result.stdout)

    def test_assertion_failure_does_not_skip_later_modules(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / 'later-ran'
            (root / 'test_first.py').write_text(
                "import unittest\nclass First(unittest.TestCase):\n"
                " def test_failure(self): self.fail('expected assertion failure')\n")
            (root / 'test_second.py').write_text(
                "from pathlib import Path\nimport unittest\nclass Second(unittest.TestCase):\n"
                f" def test_later(self): Path({str(marker)!r}).write_text('ran')\n")
            result = self.run_modules(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn('expected assertion failure', result.stderr)
            self.assertTrue(marker.exists())

    def test_abnormal_child_exit_fails_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_crash.py').write_text('import os\nos._exit(23)\n')
            result = self.run_modules(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn('test_crash.py: FAIL (23)', result.stderr)
