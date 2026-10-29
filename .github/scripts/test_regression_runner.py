"""The periodic diagnostic preserves successful and failed test-suite outcomes."""

# TEST_STAGE = TestStage.REGRESSION
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
            fixture.write_text('# TEST_STAGE = TestStage.REGRESSION\n' 'import time, unittest\n'
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
                    '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nclass Test(unittest.TestCase):\n'
                    f'    def test_value(self): self.assertFalse({fails!r})\n')
            result = subprocess.run([sys.executable, str(RUNNER), str(root), '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn('first/test_duplicate.py', result.stdout.replace('\\', '/'))
            self.assertIn('second/test_duplicate.py', result.stdout.replace('\\', '/'))
            self.assertIn('failures: 1', result.stdout)

    def test_empty_test_module_is_an_error(self):
        with TemporaryDirectory() as temporary:
            (Path(temporary) / 'test_empty.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            result = subprocess.run([sys.executable, str(RUNNER), temporary, '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No tests discovered', result.stderr)

    def test_isolated_file_does_not_rediscover_same_named_child_package(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / 'child'
            child.mkdir()
            (child / '__init__.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            for folder in (root, child):
                (folder / 'test_duplicate.py').write_text(
                    '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nclass Test(unittest.TestCase):\n'
                    '    def test_value(self): self.assertTrue(True)\n')
            result = subprocess.run([sys.executable, str(RUNNER), temporary, '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr.count('Ran 1 test in'), 2, result.stderr)
            self.assertNotIn('Ran 2 tests', result.stderr)

    def test_nested_package_retains_relative_fixture_imports(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = root / 'child'
            child.mkdir()
            (child / '__init__.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            (child / 'helper.py').write_text('VALUE = 42\n')
            (child / 'test_relative.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nfrom .helper import VALUE\nclass Test(unittest.TestCase):\n'
                '    def test_value(self): self.assertEqual(VALUE, 42)\n')
            result = subprocess.run([sys.executable, str(RUNNER), temporary, '--isolate-modules'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Ran 1 test in', result.stderr)


class StorageIsolationTests(unittest.TestCase):
    def test_discovery_and_test_body_use_disposable_default_storage(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / 'test_storage.py'
            fixture.write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import os, unittest\nfrom pathlib import Path\n'
                'home = Path.home()\n'
                'storage = Path(os.environ["COMMONUTILS_STORAGE_ROOT"])\n'
                '(home / "discovered").write_text("fixture")\n'
                'class Test(unittest.TestCase):\n'
                '    def test_isolated(self):\n'
                '        self.assertTrue((home / "discovered").is_file())\n'
                '        self.assertEqual(home.parent, storage.parent)\n'
                '        print("PRIVATE_ROOT=" + str(home.parent))\n')
            for flags in ([], ['--isolate-modules']):
                with self.subTest(flags=flags):
                    result = subprocess.run([sys.executable, str(RUNNER), str(root), *flags],
                                            capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    private = next(line.split('=', 1)[1] for line in result.stdout.splitlines()
                                   if line.startswith('PRIVATE_ROOT='))
                    self.assertFalse(Path(private).exists(), 'Private storage was not cleaned')


class MatrixSelectionTests(unittest.TestCase):
    def test_intersection_filters_out_qt_only_and_unselected_native_modules(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('test_qt_mobile_host.py', 'test_native_other.py'):
                (root / name).write_text('raise AssertionError("Must not be imported")\n')
            (root / 'test_native_selected.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nclass Test(unittest.TestCase):\n'
                '    def test_value(self): self.assertTrue(True)\n')
            command = [sys.executable, str(RUNNER), temporary, '--isolate-modules',
                       '--pattern', 'test_native*.py', '--include-pattern', '*selected.py']
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Isolated test files: 1; failures: 0', result.stdout)
            self.assertNotIn('test_qt_mobile_host.py', result.stdout)
            self.assertNotIn('test_native_other.py', result.stdout)
            result = subprocess.run([*command[:-1], '*missing.py'], capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires at least one matching', result.stderr)

    def test_missing_toolkit_is_an_error_before_discovery(self):
        with TemporaryDirectory() as temporary:
            (Path(temporary) / 'test_import.py').write_text('raise AssertionError("Must not discover")\n')
            result = subprocess.run([sys.executable, str(RUNNER), temporary, '--isolate-modules',
                                     '--require-module', '_logistics_missing_test_dependency_'],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn('Required test dependency is unavailable', result.stderr)
            self.assertNotIn('Must not discover', result.stderr)
