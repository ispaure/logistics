"""Developer commands preserve suite isolation, environment selection and failures."""
import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('logistics_dev_commands', ROOT / 'dev.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


class DeveloperCommandTests(unittest.TestCase):
    def test_host_suites_use_their_own_interpreters_and_isolate_files(self):
        for suite, folder in (('desktop', 'Python'), ('mobile', 'mobile_build')):
            with self.subTest(suite=suite), patch.object(dev.subprocess, 'run') as run, \
                    patch.object(Path, 'is_file', return_value=True):
                run.return_value.returncode = 7
                with patch.dict(os.environ, {'PYTHONPATH': '/unrelated-checkout'}):
                    self.assertEqual(dev.main(['test', suite]), 7)
                command = run.call_args.args[0]
                self.assertEqual(command[0], str(dev.environment_python(suite == 'mobile')))
                self.assertIn(str(ROOT / folder / 'tests'), command)
                self.assertIn('--isolate-modules', command)
                environment = run.call_args.kwargs['env']
                self.assertEqual(environment['PYTHONPATH'], os.pathsep.join((str(ROOT / 'Python'), str(ROOT))))
                self.assertEqual(environment['QT_QPA_PLATFORM'], 'offscreen')
                if suite == 'mobile':
                    self.assertEqual(environment['TOGA_BACKEND'], 'toga_dummy')
                self.assertEqual(run.call_args.kwargs['cwd'], ROOT)

    def test_custom_environment_keeps_its_python_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            interpreter = Path(directory) / 'environment-python'
            try:
                interpreter.symlink_to(sys.executable)
            except OSError as error:
                self.skipTest(f'Creating interpreter symlinks is unavailable: {error}')
            with patch.object(dev.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(dev.main(['test', 'mobile', '--python', str(interpreter)]), 0)
                self.assertEqual(run.call_args.args[0][0], str(interpreter.absolute()))

    def test_bad_selection_fails_before_starting_a_process(self):
        with patch.object(dev.subprocess, 'run') as run:
            for pattern in ('../test_x.py', 'test_missing_onboarding_fixture.py', '*.txt'):
                with self.subTest(pattern=pattern), self.assertRaises(SystemExit) as error:
                    dev.main(['test', 'desktop', pattern])
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_dry_run_accepts_custom_interpreter_without_executing(self):
        with patch.object(dev.subprocess, 'run') as run:
            self.assertEqual(dev.main(['test', 'desktop', 'test_dev_commands.py',
                                       '--python', '/missing/python', '--dry-run']), 0)
            run.assert_not_called()

    def test_missing_environment_has_setup_hint(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(dev.subprocess, 'run') as run:
            with self.assertRaises(SystemExit) as error:
                dev.main(['lint', '--python', str(Path(folder) / 'python')])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_lint_covers_the_ci_scope_and_developer_entry_point(self):
        with patch.object(dev.subprocess, 'run') as run, patch.object(Path, 'is_file', return_value=True):
            run.return_value.returncode = 0
            self.assertEqual(dev.main(['lint']), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[1:5], ['-m', 'ruff', 'check', '--config'])
            self.assertEqual(command[-5:], ['dev.py', 'Python', 'mobile_build', 'Scripts', '.github/scripts'])


class SetupCommandTests(unittest.TestCase):
    def test_setup_dry_run_never_installs(self):
        from Scripts import development
        with patch.object(development, 'find_uv', return_value='/tools/uv'), patch.object(development.subprocess, 'run') as run:
            for suite in ('desktop', 'mobile'):
                self.assertEqual(dev.main(['setup', suite, '--dry-run']), 0)
            run.assert_not_called()

    def test_mobile_setup_stops_when_environment_creation_fails(self):
        from Scripts import development
        with tempfile.TemporaryDirectory() as directory, patch.object(development, 'find_uv', return_value='/tools/uv'), patch.object(development.subprocess, 'run') as run:
            run.return_value.returncode = 4
            root = Path(directory)
            self.assertEqual(development.setup(root, 'mobile', lambda _: root / 'missing/python'), 4)
            self.assertEqual(run.call_count, 1)

    def test_mobile_install_requires_hashes_and_preserves_other_packages(self):
        from Scripts import development
        with patch.object(development, 'find_uv', return_value='/tools/uv'), patch.object(development.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(development.setup(ROOT, 'mobile', lambda _: Path(__file__)), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[1:3], ['pip', 'install'])
            self.assertIn('--require-hashes', command)


class DoctorCommandTests(unittest.TestCase):
    def test_broken_interpreters_report_failure_without_aborting_other_checks(self):
        import io
        import subprocess
        from contextlib import redirect_stdout
        from Scripts import development
        for error in (OSError('not executable'), subprocess.TimeoutExpired('python', 30)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                python = root / 'python'
                python.touch()
                output = io.StringIO()
                with patch.object(development, 'find_uv', return_value='/tools/uv'), \
                        patch.object(development.subprocess, 'run', side_effect=error), redirect_stdout(output):
                    self.assertEqual(development.doctor(root, lambda _: python), 1)
                self.assertIn('MISSING desktop', output.getvalue())
                self.assertIn('MISSING mobile', output.getvalue())
                self.assertIn('native tool: git', output.getvalue())
