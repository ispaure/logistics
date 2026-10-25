"""Developer commands preserve suite isolation, environment selection and failures."""
import importlib.util
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from Scripts import development

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('logistics_dev_commands', ROOT / 'dev.py')
dev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dev)


class DeveloperCommandTests(unittest.TestCase):
    def test_host_suites_use_their_own_interpreters_and_isolate_files(self):
        for suite, folder in (('desktop', 'Python'), ('mobile', 'mobile_build')):
            with self.subTest(suite=suite), patch.object(development.subprocess, 'run') as run, \
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
            with patch.object(development.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(dev.main(['test', 'mobile', '--python', str(interpreter)]), 0)
                self.assertEqual(run.call_args.args[0][0], str(interpreter.absolute()))

    def test_bad_selection_fails_before_starting_a_process(self):
        with patch.object(development.subprocess, 'run') as run:
            for pattern in ('../test_x.py', 'test_missing_onboarding_fixture.py', '*.txt'):
                with self.subTest(pattern=pattern), self.assertRaises(SystemExit) as error:
                    dev.main(['test', 'desktop', pattern])
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_dry_run_accepts_custom_interpreter_without_executing(self):
        with patch.object(development.subprocess, 'run') as run:
            self.assertEqual(dev.main(['test', 'desktop', 'test_dev_commands.py',
                                       '--python', '/missing/python', '--dry-run']), 0)
            run.assert_not_called()

    def test_missing_environment_has_setup_hint(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(development.subprocess, 'run') as run:
            with self.assertRaises(SystemExit) as error:
                dev.main(['lint', '--python', str(Path(folder) / 'python')])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_lint_covers_the_ci_scope_and_developer_entry_point(self):
        with patch.object(development.subprocess, 'run') as run, patch.object(Path, 'is_file', return_value=True):
            run.return_value.returncode = 0
            self.assertEqual(dev.main(['lint']), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[1:5], ['-m', 'ruff', 'check', '--config'])
            self.assertEqual(command[-6:], ['dev.py', 'Python', 'mobile_build', 'Scripts', 'build_manager', '.github/scripts'])


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


class SharedMatrixTests(unittest.TestCase):
    def test_shared_matrix_keeps_both_failures_and_environment_ownership(self):
        from types import SimpleNamespace
        for codes, expected in (((7, 0), 7), ((0, 9), 9), ((7, 9), 7), ((0, 0), 0)):
            with self.subTest(codes=codes), patch.object(development.subprocess, 'run') as run, \
                    patch.object(Path, 'is_file', return_value=True):
                run.side_effect = [SimpleNamespace(returncode=code) for code in codes]
                with patch.dict(os.environ, {'TOGA_BACKEND': 'unrelated_backend'}):
                    self.assertEqual(dev.main(['test', 'shared', 'test_native_browser_lifecycle.py']), expected)
                self.assertEqual(run.call_count, 2)
                qt, native = run.call_args_list
                self.assertEqual(qt.args[0][0], str(dev.environment_python(False)))
                self.assertEqual(native.args[0][0], str(dev.environment_python(True)))
                self.assertNotIn('TOGA_BACKEND', qt.kwargs['env'])
                self.assertEqual(native.kwargs['env']['TOGA_BACKEND'], 'toga_dummy')
                self.assertIn('PySide6', qt.args[0])
                self.assertIn('toga_dummy', native.args[0])
                self.assertIn('--include-pattern', native.args[0])
                self.assertIn('test_native_browser_lifecycle.py', native.args[0])
                self.assertIn('--isolate-modules', qt.args[0])
                self.assertIn('--isolate-modules', native.args[0])

    def test_portable_selection_does_not_require_a_mobile_environment(self):
        with patch.object(development.subprocess, 'run') as run, patch.object(Path, 'is_file', return_value=True):
            run.return_value.returncode = 0
            self.assertEqual(dev.main(['test', 'shared', 'test_streams.py']), 0)
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][0], str(dev.environment_python(False)))

    def test_native_interpreter_is_checked_before_any_matrix_leg_runs(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(development.subprocess, 'run') as run, \
                patch.object(dev, 'environment_python', return_value=Path(sys.executable)):
            with self.assertRaises(SystemExit) as error:
                dev.main(['test', 'shared', '--native-python', str(Path(directory) / 'missing')])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_matrix_dry_run_preserves_both_explicit_interpreter_paths(self):
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            qt, native = Path(directory) / 'qt-python', Path(directory) / 'native-python'
            with patch.object(development.subprocess, 'run') as run, redirect_stdout(output):
                self.assertEqual(dev.main(['test', 'shared', '--python', str(qt),
                                           '--native-python', str(native), '--dry-run']), 0)
                run.assert_not_called()
            self.assertIn(str(qt.absolute()), output.getvalue())
            self.assertIn(str(native.absolute()), output.getvalue())

    def test_bad_shared_selection_and_inapplicable_override_start_nothing(self):
        with patch.object(development.subprocess, 'run') as run:
            for args in (['test', 'shared', 'test_missing_onboarding_fixture.py'],
                         ['test', 'shared', '../test_streams.py'],
                         ['test', 'mobile', '--native-python', '/missing/native-python']):
                with self.subTest(args=args), self.assertRaises(SystemExit) as error:
                    dev.main(args)
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()


class LintScopeTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('ruff'), 'Lint scope requires the pinned Ruff developer tool')
    def test_generated_output_never_hides_errors_in_new_owned_source(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            owned = ('dev.py', 'Python/new_module.py', 'mobile_build/tools.py',
                     'mobile_build/build_support/new_adapter.py',
                     'mobile_build/native_tests/tests/probe.py', 'Scripts/check.py', '.github/scripts/check.py')
            for name in owned:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('VALUE = 1\n')
            config = root / 'Python/pyproject.toml'
            shutil.copyfile(ROOT / 'Python/pyproject.toml', config)
            command = [sys.executable, '-m', 'ruff', 'check', '--config', str(config),
                       'dev.py', 'Python', 'mobile_build', 'Scripts', '.github/scripts']

            def selected():
                result = subprocess.run([*command, '--show-files'], cwd=root,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return {Path(line).relative_to(root).as_posix() for line in result.stdout.splitlines()
                        if line.endswith('.py')}

            self.assertEqual(selected(), set(owned))
            generated = ('mobile_build/build', 'mobile_build/payload', 'mobile_build/logs',
                         'mobile_build/.deploy-workspaces/android/payload', 'mobile_build/.tools/go',
                         'mobile_build/.briefcase', 'mobile_build/.android-beta',
                         'Python/features/emulation', '.venv', 'mobile_build/.venv')
            for folder in generated:
                path = root / folder / 'invalid.py'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('def invalid(\n')
            self.assertEqual(selected(), set(owned))
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            new = root / 'Python/untracked_workflow.py'
            new.write_text('def invalid(\n')
            self.assertEqual(selected(), {*owned, 'Python/untracked_workflow.py'})
            result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('untracked_workflow.py', result.stdout)
