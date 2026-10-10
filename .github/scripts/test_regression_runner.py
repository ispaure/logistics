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
        self.assertIn('Periodic regression trace', result.stderr)
        self.assertIn('in test_slow', result.stderr)
        self.assertIn('OK', result.stderr)

    def test_failure_remains_a_failure_with_diagnostics_enabled(self):
        result = self.run_fixture(True)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('Periodic regression trace', result.stderr)
        self.assertIn('FAILED (failures=1)', result.stderr)
