"""Developer commands preserve suite isolation, environment selection and failures."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
    def setUp(self):
        # These cases exercise routing; real inventory validation has its own fixtures.
        self.enterContext(patch('logistics_build.test_structure.inventory', return_value=[]))

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

    def test_bridge_inventory_matches_execution_profile_without_starting_go(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import json
        from logistics_build import test_structure
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for name, stage in (('Smoke', 'smoke'), ('Daily', 'regression'), ('Extended', 'extended')):
                path = root / 'mobile_build/rclone_bridge' / (name.lower() + '_test.go')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'func Test{name}(t *testing.T) {{}}\n')
                rows.append(dict(owner='bridge', path=path.relative_to(root).as_posix(), stage=stage, cases=[]))
            rows.append(dict(owner='other', path='other_test.go', stage='smoke', cases=[]))
            for profile, names in (('smoke', ['Smoke']), ('daily', ['Smoke', 'Daily']),
                                   ('full', ['Smoke', 'Daily', 'Extended'])):
                with self.subTest(profile=profile), patch.object(test_structure, 'ROOT', root), \
                        patch.object(test_structure, 'inventory', return_value=rows), \
                        patch.object(test_structure.subprocess, 'run') as run:
                    output = StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(dev.main(['test', 'bridge', '--profile', profile, '--inventory']), 0)
                    selected = json.loads(output.getvalue())
                    self.assertEqual([row['path'] for row in selected], [
                        'mobile_build/rclone_bridge/' + name.lower() + '_test.go' for name in names])
                    run.assert_not_called()
                    run.return_value.returncode = 0
                    self.assertEqual(test_structure.run_bridge(rows, profile, 'diagnostic', False), 0)
                    self.assertEqual([call.args[0][call.args[0].index('-run') + 1] for call in run.call_args_list],
                                     ['^(Test' + name + ')$' for name in names])

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

    def test_exact_files_route_to_their_owning_environment(self):
        for suite, folder in (('desktop', 'Python'), ('mobile', 'mobile_build')):
            first = f'{folder}/tests/first/test_same.py'
            second = f'{folder}/tests/second/test_same.py'
            with self.subTest(suite=suite), patch.object(development.subprocess, 'run') as run, \
                    patch.object(Path, 'is_file', return_value=True), \
                    patch('logistics_build.test_structure.inventory', return_value=[{'path': first}, {'path': second}]):
                run.return_value.returncode = 0
                self.assertEqual(dev.main(['test', suite, '--exact-file', first, '--exact-file', second]), 0)
                command = run.call_args.args[0]
                self.assertEqual(command[0], str(dev.environment_python(suite == 'mobile')))
                self.assertEqual(command[command.index('--exact-file'):][:4],
                                 ['--exact-file', 'first/test_same.py', '--exact-file', 'second/test_same.py'])
                self.assertNotIn('--pattern', command)

    def test_invalid_exact_file_selection_starts_nothing(self):
        path = 'Python/tests/tooling/test_dev_commands.py'
        with patch.object(development.subprocess, 'run') as run, \
                patch('logistics_build.test_structure.inventory', return_value=[{'path': path}]):
            for options in (['desktop', '--exact-file', path, '--exact-file', path],
                            ['desktop', '--exact-file', 'Python/tests/../test_missing.py'],
                            ['desktop', 'test*.py', '--exact-file', path],
                            ['mobile', '--exact-file', path], ['bridge', '--exact-file', path],
                            ['shared', '--exact-file', path]):
                with self.subTest(options=options), self.assertRaises(SystemExit) as error:
                    dev.main(['test', *options])
                self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_owner_batches_overlapping_patterns_and_preserves_failure_policy(self):
        from Scripts import ownership
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ('Python/tests/a/test_same.py', 'Python/tests/b/test_same.py',
                     'mobile_build/tests/c/test_same.py')
            for path in paths:
                source = root / path
                source.parent.mkdir(parents=True)
                source.write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            declaration = {'fixture': {'tests': {'desktop': ['test*.py', 'test_same.py'],
                                                 'mobile': ['test_same.py']}}}
            for options, count in (({}, 2), ({'mode': 'fast'}, 1), ({'fail_fast': True}, 1)):
                with self.subTest(options=options), patch.object(ownership, 'owners', return_value=declaration), \
                        patch.object(ownership.subprocess, 'run', return_value=SimpleNamespace(returncode=7)) as run:
                    self.assertEqual(ownership.test_owner(root, 'fixture', sys.executable, profile='daily', **options), 1)
                    self.assertEqual(run.call_count, count)
                    for call, suite, expected in zip(run.call_args_list, ('desktop', 'mobile'),
                                                     (paths[:2], paths[2:])):
                        command = call.args[0]
                        self.assertEqual(command[2:4], ['test', suite])
                        self.assertEqual(command[4:8], ['--profile', 'daily', '--mode', options.get('mode', 'diagnostic')])
                        self.assertEqual([command[i + 1] for i, arg in enumerate(command) if arg == '--exact-file'],
                                         list(expected))
                        self.assertEqual('--fail-fast' in command, bool(options.get('fail_fast')))
                        self.assertEqual(call.kwargs['cwd'], root)

    def test_owner_profile_omits_empty_environments_and_rejects_an_empty_owner(self):
        from Scripts import ownership
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = ('Python/tests/test_smoke.py', 'mobile_build/tests/test_regular.py')
            for path, stage in zip(paths, ('SMOKE', 'REGRESSION')):
                source = root / path
                source.parent.mkdir(parents=True)
                source.write_text(f'# TEST_STAGE = TestStage.{stage}\n')
            declaration = {'fixture': {'tests': {'desktop': ['test_smoke.py'],
                                                 'mobile': ['test_regular.py']}}}
            with patch.object(ownership, 'owners', return_value=declaration), \
                    patch.object(ownership.subprocess, 'run') as run:
                run.return_value.returncode = 0
                self.assertEqual(ownership.test_owner(root, 'fixture', sys.executable, profile='smoke'), 0)
                self.assertEqual(run.call_count, 1)
                command = run.call_args.args[0]
                self.assertEqual(command[3], 'desktop')
                self.assertIn(paths[0], command)
                run.reset_mock()
                (root / paths[0]).write_text('# TEST_STAGE = TestStage.REGRESSION\n')
                self.assertEqual(ownership.test_owner(root, 'fixture', sys.executable, profile='smoke'), 2)
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
            self.assertEqual(command[-6:], ['dev.py', 'Python', 'mobile_build', 'Scripts', 'logistics_build', '.github/scripts'])


class SetupCommandTests(unittest.TestCase):
    def test_setup_dry_run_never_installs(self):
        from Scripts import development
        with patch.object(development, 'find_uv', return_value='/tools/uv'), patch.object(development.subprocess, 'run') as run:
            for suite in ('desktop', 'mobile'):
                self.assertEqual(dev.main(['setup', suite, '--dry-run']), 0)
            run.assert_not_called()

    def test_mobile_setup_stops_when_environment_creation_fails(self):
        from Scripts import development
        from logistics_build import tooling_bootstrap as tooling
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(development, 'find_uv', return_value='/tools/uv'), \
                patch.object(tooling, 'boot_identity', return_value='11111111-1111-4111-8111-111111111111'), \
                patch.object(tooling, 'run_command') as run, \
                patch.object(tooling, '_repair_locked') as repair:
            run.return_value.returncode = 4
            root = Path(directory).resolve()
            self.assertEqual(development.setup(root, 'mobile', lambda _: root / 'missing/python'), 4)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][1], 'venv')
            repair.assert_not_called()
            self.assertFalse(tooling.enrolled(root))
            if os.name == 'posix':
                pending = tooling.read_intent(root)
                self.assertEqual(pending['cleanup'], tooling.cleanup_proof(pending))
            with tooling.file_lock(tooling.lock_path(root)):
                pass

    def test_mobile_install_requires_hashes_and_preserves_other_packages(self):
        from Scripts import development
        from logistics_build import tooling_bootstrap as tooling
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(development, 'find_uv', return_value='/tools/uv'), \
                patch.object(tooling, 'boot_identity', return_value='11111111-1111-4111-8111-111111111111'), \
                patch.object(tooling, 'run_command') as run, \
                patch.object(tooling, '_repair_locked') as repair:
            root = Path(directory).resolve()
            python = tooling.environments(root)[1][2]
            python.parent.mkdir(parents=True)
            python.touch()
            run.return_value.returncode = 0
            self.assertEqual(development.setup(root, 'mobile', lambda _: python), 0)
            self.assertEqual(run.call_count, 1)
            command = run.call_args.args[0]
            self.assertEqual(command[1:3], ['pip', 'install'])
            self.assertIn('--require-hashes', command)
            self.assertEqual(command[command.index('--python') + 1], str(python))
            self.assertEqual(run.call_args.kwargs['cwd'], root)
            repair.assert_not_called()
            self.assertFalse(tooling.enrolled(root))
            self.assertFalse(tooling.intent_path(root).exists())


class DoctorCommandTests(unittest.TestCase):
    def test_mobile_doctor_names_missing_build_tools_and_the_setup_remedy(self):
        import io
        from contextlib import redirect_stdout
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python = root / 'python'; python.touch()
            output = io.StringIO()
            results = [SimpleNamespace(returncode=0, stdout='{"python":"3.12.2","missing":[]}'),
                       SimpleNamespace(returncode=0, stdout='{"python":"3.12.2","missing":["briefcase","pip"]}')]
            with patch.object(development, 'find_uv', return_value='uv'), \
                    patch.object(development.subprocess, 'run', side_effect=results) as run, redirect_stdout(output):
                self.assertEqual(development.doctor(root, lambda _: python), 1)
            mobile_probe = run.call_args_list[1].args[0][-1]
            self.assertIn('briefcase', mobile_probe)
            self.assertIn('pip', mobile_probe)
            mobile_line = next(line for line in output.getvalue().splitlines() if line.startswith('MISSING mobile:'))
            self.assertIn('briefcase', mobile_line)
            self.assertIn('pip', mobile_line)
            self.assertIn('run python3 dev.py setup mobile', mobile_line)

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
    def setUp(self):
        self.enterContext(patch('logistics_build.test_structure.inventory', return_value=[]))

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


class PreflightCommandTests(unittest.TestCase):
    def test_real_preflight_accepts_valid_sources_and_blocks_invalid_sources_before_execution(self):
        from contextlib import redirect_stderr
        from io import StringIO
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / 'Python/tests'
            tests.mkdir(parents=True)
            source = tests / 'test_fixture.py'
            source.write_text('# TEST_STAGE = TestStage.SMOKE\nraise RuntimeError("must not import")\n')
            (root / 'test-structure.json').write_text(json.dumps(dict(schema=1, roots=[
                dict(owner='fixture', directory='Python/tests', patterns=['test*.py'])])))
            with patch.object(dev, 'ROOT', root), patch.object(sys, 'path', list(sys.path)), \
                    patch.object(development.subprocess, 'run') as run:
                self.assertEqual(dev.main(['test', 'desktop', 'test_fixture.py',
                                           '--python', '/missing/python', '--dry-run']), 0)
                source.write_text('# TEST_STAGE = TestStage.INVALID\n')
                for suite in ('desktop', 'mobile', 'shared', 'bridge'):
                    with self.subTest(suite=suite):
                        diagnostic = StringIO()
                        with redirect_stderr(diagnostic), self.assertRaises(SystemExit) as error:
                            dev.main(['test', suite, '--python', str(Path(sys.executable).absolute())])
                        self.assertEqual(error.exception.code, 2)
                        self.assertIn('invalid TestStage member INVALID', diagnostic.getvalue())
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
                     'mobile_build/native_tests/tests/probe.py', 'Scripts/check.py', 'logistics_build/check.py', '.github/scripts/check.py')
            for name in owned:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('VALUE = 1\n')
            config = root / 'Python/pyproject.toml'
            shutil.copyfile(ROOT / 'Python/pyproject.toml', config)
            command = [sys.executable, '-m', 'ruff', 'check', '--config', str(config),
                       'dev.py', 'Python', 'mobile_build', 'Scripts', 'logistics_build', '.github/scripts']

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
