"""Isolated GUI checks must run every module and preserve all failure statuses."""
from pathlib import Path
import importlib.util
import json
import os
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


RUNNER = Path(__file__).parents[1] / 'run_regressions.py'


class RegressionRunnerTests(unittest.TestCase):
    def test_file_timeout_retains_elapsed_time_and_failure_without_child_report(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('timing_runner_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_stuck.py').write_text('')
            report = runner.TimingReport(root / 'report.json', root, 'test*.py', True)
            with patch.object(runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 300)):
                self.assertEqual(runner.run_isolated(root, 'test*.py', 60, report=report), 1)
            data = json.loads(report.path.read_text())
            self.assertEqual(data['modules'][0]['outcome'], 'timeout')
            self.assertEqual(data['modules'][0]['exit_code'], 124)
            self.assertGreater(data['modules'][0]['duration_seconds'], 0)
            self.assertFalse(data['modules'][0]['test_report_available'])
            self.assertFalse(data['complete'])

    def test_selected_suite_takes_precedence_over_runner_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_pdf_reader.py').write_text(
                'import unittest\nclass SelectedSuite(unittest.TestCase):\n'
                ' def test_selected_suite(self): pass\n')
            env = dict(os.environ, PYTHONPATH=str(root) + os.pathsep + os.environ.get('PYTHONPATH', ''))
            result = subprocess.run([sys.executable, str(RUNNER), str(root), '--isolate-modules'],
                                    capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('test_selected_suite', result.stderr)

    def run_modules(self, directory, *extra):
        return subprocess.run([sys.executable, str(RUNNER), str(directory), '--isolate-modules', *extra],
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
            self.assertIn('Failed isolated test files: test_first.py', result.stderr)
            self.assertTrue(marker.exists())

    def test_abnormal_child_exit_fails_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_crash.py').write_text('import os\nos._exit(23)\n')
            report = root / 'report.json'
            result = self.run_modules(root, '--report', str(report))
            self.assertEqual(result.returncode, 1)
            self.assertIn('test_crash.py: FAIL (23)', result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data['exit_code'], 1)
            self.assertTrue(data['complete'])
            self.assertEqual(data['modules'][0]['exit_code'], 23)
            self.assertFalse(data['modules'][0]['test_report_complete'])

    def test_timing_includes_cleanup_and_preserves_outcomes_across_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_outcomes.py').write_text(
                'import time, unittest\n'
                'class Cases(unittest.TestCase):\n'
                ' def setUp(self): time.sleep(0.02)\n'
                ' def tearDown(self): time.sleep(0.02)\n'
                ' def test_pass(self): self.addCleanup(time.sleep, 0.02)\n'
                ' @unittest.skip("fixture skip")\n'
                ' def test_skip(self): pass\n'
                ' @unittest.expectedFailure\n'
                ' def test_expected(self): self.fail()\n'
                ' @unittest.expectedFailure\n'
                ' def test_unexpected(self): pass\n'
                ' def test_error(self): raise RuntimeError("fixture error")\n'
                ' def test_subtests(self):\n'
                '  with self.subTest(value=1): self.fail("subtest failure")\n'
                '  with self.subTest(value=2): pass\n')
            (root / 'test_fixture.py').write_text(
                'import unittest\n'
                'class Broken(unittest.TestCase):\n'
                ' @classmethod\n'
                ' def setUpClass(cls): raise RuntimeError("class fixture error")\n'
                ' def test_never_runs(self): pass\n')
            report = root / 'report.json'
            result = self.run_modules(root, '--report', str(report))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            data = json.loads(report.read_text())
            self.assertTrue(data['complete'])
            self.assertEqual(len(data['modules']), 2)
            records = {row['id'].split('.')[-1]: row for row in data['tests']}
            for name, outcome in [('pass', 'passed'), ('skip', 'skipped'),
                                  ('expected', 'expected_failure'), ('unexpected', 'unexpected_success'),
                                  ('error', 'error'), ('subtests', 'failed')]:
                self.assertEqual(records['test_' + name]['outcome'], outcome)
            self.assertGreaterEqual(records['test_pass']['duration_seconds'], 0.06)
            self.assertTrue(any(row.get('fixture_event') for row in data['tests']))
            self.assertTrue(all(row['started_at'].endswith('+00:00') for row in data['tests']))
            self.assertGreater(data['duration_seconds'], sum(
                row['duration_seconds'] for row in data['tests']))
            self.assertIn('Slowest tests', result.stdout)
            self.assertIn('Slowest files', result.stdout)
