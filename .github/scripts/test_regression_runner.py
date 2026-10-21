"""The periodic diagnostic preserves successful and failed test-suite outcomes."""
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

RUNNER = Path(__file__).resolve().parents[2] / 'Python/tests/run_regressions.py'


class RegressionRunnerTests(unittest.TestCase):
    def run_fixture(self, fails):
        with TemporaryDirectory() as temporary:
            fixture = Path(temporary) / 'test_slow.py'
            fixture.write_text('import time, unittest\n'
                'class SlowTest(unittest.TestCase):\n'
                '    def test_slow(self):\n'
                '        time.sleep(.15)\n'
                f'        self.assertFalse({fails!r})\n')
            return subprocess.run([sys.executable, str(RUNNER), temporary,
                '--traceback-after', '.025'], capture_output=True, text=True, timeout=10)

    def test_success_reports_running_test_without_interrupting_it(self):
        result = self.run_fixture(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Regression progress', result.stderr)
        self.assertIn('test_slow.SlowTest.test_slow', result.stderr)
        self.assertIn('OK', result.stderr)

    def test_failure_remains_a_failure_with_diagnostics_enabled(self):
        result = self.run_fixture(True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Regression progress', result.stderr)
        self.assertIn('FAILED (failures=1)', result.stderr)


class NestedRegressionRunnerTests(unittest.TestCase):
    def test_same_named_nested_modules_run_independently_and_keep_failures(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, fails in [('first', False), ('second', True)]:
                folder = root / name
                folder.mkdir()
                (folder / 'test_duplicate.py').write_text(
                    'import unittest\nclass Test(unittest.TestCase):\n'
                    f'    def test_value(self): self.assertFalse({fails!r})\n')
            result = subprocess.run([sys.executable, str(RUNNER), str(root), '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('first/test_duplicate.py', result.stdout.replace('\\', '/'))
            self.assertIn('second/test_duplicate.py', result.stdout.replace('\\', '/'))
            self.assertIn('failures: 1', result.stdout)

    def test_empty_test_module_is_an_error(self):
        with TemporaryDirectory() as temporary:
            (Path(temporary) / 'test_empty.py').write_text('')
            result = subprocess.run([sys.executable, str(RUNNER), temporary, '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No tests discovered', result.stderr)
