"""Isolated GUI checks must run every module and preserve all failure statuses."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
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
    def test_current_test_events_stream_from_the_isolated_child(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_live.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nclass Live(unittest.TestCase):\n'
                ' def test_current(self): pass\n')
            with patch.dict(os.environ, BUILD_MANAGER_TEST_PROGRESS='1'):
                result = self.run_modules(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            prefix = '@@BUILD_MANAGER_TEST@@'
            events = [json.loads(line[len(prefix):]) for line in result.stdout.splitlines() if line.startswith(prefix)]
            self.assertEqual([event['kind'] for event in events],
                             ['file_started', 'test_started', 'test_finished', 'file_finished'])
            self.assertEqual(events[1]['name'], 'test_current')
            self.assertEqual(events[1]['file'], 'test_live.py')
            self.assertEqual(events[2]['status'], 'passed')
            self.assertGreaterEqual(events[2]['seconds'], 0)

    def test_file_timeout_retains_elapsed_time_and_failure_without_child_report(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('timing_runner_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_stuck.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            report = runner.TimingReport(root / 'report.json', root, 'test*.py', True)
            with patch.object(runner.subprocess, 'run', side_effect=subprocess.TimeoutExpired('probe', 300)), \
                    patch.object(runner, 'monotonic', side_effect=[10.0, 10.25]):
                self.assertEqual(runner.run_isolated(root, 'test*.py', 60, report=report), 1)
            data = json.loads(report.path.read_text())
            self.assertEqual(data['modules'][0]['outcome'], 'timeout')
            self.assertEqual(data['modules'][0]['exit_code'], 124)
            self.assertEqual(data['modules'][0]['duration_seconds'], 0.25)
            self.assertFalse(data['modules'][0]['test_report_available'])
            self.assertFalse(data['complete'])
            self.assertFalse(data['coverage_complete'])
            self.assertEqual(data['not_run'][0]['file'], 'test_stuck.py')

    def test_file_timeout_preserves_already_completed_case_evidence(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('partial_timing_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_partial.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport time, unittest\n'
                'class Cases(unittest.TestCase):\n'
                ' def test_a_finished(self): pass\n'
                ' def test_b_stalled(self): time.sleep(30)\n')
            report = runner.TimingReport(root / 'result.json', root, 'test*.py', True)
            with patch.object(runner, 'ISOLATED_FILE_TIMEOUT', 2):
                self.assertEqual(runner.run_isolated(root, 'test*.py', 60, report=report), 1)
            self.assertEqual([row['id'].split('.')[-1] for row in report.data['tests']], ['test_a_finished'])
            self.assertEqual(report.data['tests'][0]['outcome'], 'passed')
            self.assertEqual(report.data['modules'][0]['outcome'], 'timeout')
            self.assertFalse(report.data['coverage_complete'])
            self.assertTrue(any('test_b_stalled' in str(row) for row in report.data['not_run']))

    def test_later_timeout_preserves_fixture_failure_and_diagnostics(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('fixture_timing_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_partial.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport time, unittest\n'
                'def tearDownModule(): time.sleep(30)\n'
                'class Cases(unittest.TestCase):\n'
                ' @classmethod\n'
                ' def setUpClass(cls): raise RuntimeError("fixture setup failed")\n'
                ' def test_never_started(self): pass\n')
            report = runner.TimingReport(root / 'result.json', root, 'test*.py', True)
            with patch.object(runner, 'ISOLATED_FILE_TIMEOUT', 2):
                self.assertEqual(runner.run_isolated(root, 'test*.py', 60, report=report), 1)
            self.assertEqual(len(report.data['tests']), 1)
            failure = report.data['tests'][0]
            self.assertTrue(failure['fixture_event'])
            self.assertEqual(failure['outcome'], 'error')
            self.assertIn('fixture setup failed', failure['message'])
            self.assertEqual(report.data['modules'][0]['outcome'], 'timeout')
            self.assertFalse(report.data['coverage_complete'])

    def test_selected_suite_takes_precedence_over_runner_directory(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_pdf_reader.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\nclass SelectedSuite(unittest.TestCase):\n'
                ' def test_selected_suite(self): pass\n')
            env = dict(os.environ, PYTHONPATH=str(root) + os.pathsep + os.environ.get('PYTHONPATH', ''))
            result = subprocess.run([sys.executable, str(RUNNER), str(root), '--isolate-modules'],
                                    capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('test_selected_suite', result.stderr)

    def run_modules(self, directory, *extra):
        return subprocess.run([sys.executable, str(RUNNER), str(directory), '--isolate-modules', *extra],
                              capture_output=True, text=True, timeout=30)

    def test_inventory_matches_filtered_execution_without_importing_sources(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_keep_mixed.py').write_text('''from pathlib import Path
import unittest
from commonUtils.testing.stages import TestStage, stage

TEST_STAGE = TestStage.EXTENDED
Path(__file__).with_suffix('.imported').touch()

class Cases(unittest.TestCase):
    @stage(TestStage.SMOKE)
    def test_smoke(self): pass

    @stage(TestStage.REGRESSION)
    def test_regression(self): pass

    def test_extended(self): pass
''')
            (root / 'test_keep_extended.py').write_text(
                '# TEST_STAGE = TestStage.EXTENDED\nraise RuntimeError("excluded stage imported")\n')
            (root / 'test_keep_invalid_source.py').write_text('raise RuntimeError("excluded file imported")\n')
            (root / 'test_other_mixed.py').write_text('raise RuntimeError("excluded file imported")\n')
            filters = ('--include-pattern', 'test_keep_*', '--include-pattern', '*d.py')
            inventories = []
            for selection in (('--profile', 'daily'), ('--stage', 'regression', '--stage', 'smoke')):
                inventory = self.run_modules(root, *filters, *selection, '--inventory')
                self.assertEqual(inventory.returncode, 0, inventory.stderr)
                self.assertFalse(list(root.glob('*.imported')))
                inventories.append(json.loads(inventory.stdout))
            rows, explicit_stages = inventories
            self.assertEqual(rows, explicit_stages)
            self.assertEqual([row['file'] for row in rows], ['test_keep_mixed.py'])
            self.assertEqual(rows[0]['stage'], 'extended')
            self.assertEqual(rows[0]['stages'], ['smoke', 'regression'])
            self.assertEqual({(case['case'], case['stage']) for case in rows[0]['cases']},
                             {('Cases.test_smoke', 'smoke'), ('Cases.test_regression', 'regression')})

            report = root / 'report.json'
            execution = self.run_modules(root, *filters, '--profile', 'daily', '--report', str(report))
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            self.assertTrue((root / 'test_keep_mixed.imported').is_file())
            data = json.loads(report.read_text())
            self.assertEqual(data['classified_files'], [dict(path=rows[0]['file'], stage=rows[0]['stage'],
                                                            stages=rows[0]['stages'], cases=rows[0]['cases'])])
            self.assertEqual([(module['path'], module['stage']) for module in data['modules']],
                             [(rows[0]['file'], level) for level in rows[0]['stages']])
            self.assertEqual({(case['id'].split('.', 1)[1], case['stage']) for case in data['tests']},
                             {(case['case'], case['stage']) for case in rows[0]['cases']})
            self.assertIn('test_keep_mixed.py [stage=smoke]', execution.stdout.split('Slowest files')[1])

    def test_exact_file_inventory_and_execution_do_not_broaden_same_basename(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder, content in (('first', ' def test_first(self): pass'),
                                    ('second', ' raise RuntimeError("wrong source imported")'),
                                    ('third', ' def test_third(self): pass')):
                source = root / folder / 'test_same.py'
                source.parent.mkdir()
                source.write_text('# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                                  'class Cases(unittest.TestCase):\n' + content + '\n')
            selection = ('--exact-file', 'third/test_same.py', '--exact-file', 'first/test_same.py')
            inventory = self.run_modules(root, *selection, '--inventory')
            self.assertEqual(inventory.returncode, 0, inventory.stderr)
            rows = json.loads(inventory.stdout)
            report = root / 'report.json'
            execution = self.run_modules(root, *selection, '--report', str(report))
            self.assertEqual(execution.returncode, 0, execution.stdout + execution.stderr)
            data = json.loads(report.read_text())
            files = [str(Path(folder) / 'test_same.py') for folder in ('first', 'third')]
            self.assertEqual([row['file'] for row in rows], files)
            self.assertEqual(data['classified_files'],
                             [dict(path=row['file'], **{k: v for k, v in row.items() if k != 'file'}) for row in rows])
            self.assertEqual([(row['path'], row['stage']) for row in data['modules']],
                             [(row['file'], 'regression') for row in rows])
            self.assertEqual([(row['file'], row['id']) for row in data['tests']],
                             [(files[0], 'test_same.Cases.test_first'),
                              (files[1], 'test_same.Cases.test_third')])

    def test_exact_file_ignores_unselected_descendant_metadata(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'test_same.py').write_text('# TEST_STAGE = TestStage.INVALID\n')
            (root / 'test_same.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                'class Selected(unittest.TestCase):\n def test_runs(self): pass\n')
            report = root / 'report.json'
            result = self.run_modules(root, '--exact-file', 'test_same.py', '--report', str(report))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual([row['id'] for row in json.loads(report.read_text())['tests']],
                             ['test_same.Selected.test_runs'])

    def test_exact_file_rejects_shadowing_package_before_import(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            shadow = root / 'test_same'
            shadow.mkdir()
            marker = root / 'shadow-imported'
            (shadow / '__init__.py').write_text(
                f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
            (root / 'test_same.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                'class Selected(unittest.TestCase):\n def test_runs(self): pass\n')
            result = self.run_modules(root, '--exact-file', 'test_same.py', '--report', str(root / 'report.json'))
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Selected test module 'test_same' did not resolve to", result.stderr)
            self.assertFalse(marker.exists())

    def test_exact_file_rejects_missing_duplicate_and_escaping_paths(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_present.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n')
            for options in (('--exact-file', 'test_missing.py'),
                            ('--exact-file', '../test_present.py'),
                            ('--exact-file', str(root / 'test_present.py')),
                            ('--exact-file', 'test_present.py', '--exact-file', 'test_present.py')):
                for mode in (('--inventory',), ('--report', str(root / 'report.json'))):
                    with self.subTest(options=options, mode=mode):
                        result = self.run_modules(root, *options, *mode)
                        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                        self.assertIn('exact', result.stderr)
                        self.assertNotIn('Running isolated test file', result.stdout)

    def test_inventory_and_execution_reject_empty_stage_selection(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_extended.py').write_text(
                '# TEST_STAGE = TestStage.EXTENDED\nraise RuntimeError("must not import")\n'
                'import unittest\nclass Cases(unittest.TestCase):\n def test_extended(self): pass\n')
            report = root / 'report.json'
            for options in (('--inventory',), ('--report', str(report))):
                with self.subTest(options=options):
                    result = self.run_modules(root, '--stage', 'smoke', *options)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('No tests selected for the requested execution stages.', result.stderr)
                    self.assertNotIn('must not import', result.stderr)
            self.assertEqual(json.loads(report.read_text())['modules'], [])

    def test_modules_have_independent_process_state(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_first.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' "import os, unittest\n"
                "class First(unittest.TestCase):\n"
                " def test_state(self): os.environ['LOGISTICS_TEST_PROCESS_STATE'] = 'changed'\n")
            (root / 'test_second.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' "import os, unittest\n"
                "class Second(unittest.TestCase):\n"
                " def test_state(self): self.assertNotIn('LOGISTICS_TEST_PROCESS_STATE', os.environ)\n")
            result = self.run_modules(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('Isolated test files: 2; failures: 0', result.stdout)

    def test_manager_profile_and_account_inputs_do_not_escape_into_fixtures(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            protected = root / 'operator-profile.json'
            protected.write_text('operator profile remains unchanged')
            suite = root / 'suite'
            suite.mkdir()
            (suite / 'test_profile.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' "import os, sys, unittest\nfrom pathlib import Path\n"
                f"sys.path.insert(0, {str(RUNNER.parents[2])!r})\n"
                "from mobile_build.deployment.manager_settings import profile_path\n"
                "class Profile(unittest.TestCase):\n"
                " def test_fixture_owns_profile(self):\n"
                "  root=Path(__file__).parent\n"
                "  self.assertEqual(os.environ.get('LOGISTICS_MANAGER_ACCOUNT_DEFAULTS'), '{}')\n"
                "  self.assertEqual(profile_path(root), root/'.tools/build-manager/profile.json')\n"
                "  profile_path(root).parent.mkdir(parents=True)\n"
                "  profile_path(root).write_text('fixture only')\n")
            with patch.dict(os.environ, LOGISTICS_MANAGER_PROFILE=str(protected),
                            LOGISTICS_MANAGER_ACCOUNT_DEFAULTS='{"auth.fixture": "operator"}'):
                result = self.run_modules(suite)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(protected.read_text(), 'operator profile remains unchanged')
            self.assertEqual((suite / '.tools/build-manager/profile.json').read_text(), 'fixture only')

    def test_assertion_failure_does_not_skip_later_modules(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / 'later-ran'
            (root / 'test_first.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' "import unittest\nclass First(unittest.TestCase):\n"
                " def test_failure(self): self.fail('expected assertion failure')\n")
            (root / 'test_second.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' "from pathlib import Path\nimport unittest\nclass Second(unittest.TestCase):\n"
                f" def test_later(self): Path({str(marker)!r}).write_text('ran')\n")
            result = self.run_modules(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn('expected assertion failure', result.stderr)
            self.assertIn('Failed isolated test files: test_first.py', result.stderr)
            self.assertTrue(marker.exists())

    def test_invalid_child_evidence_preserves_prefix_and_obeys_stop_policy(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('child_evidence_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('test_first.py', 'test_second.py'):
                (root / name).write_text(
                    '# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                    'class Cases(unittest.TestCase):\n def test_case(self): pass\n')
            prefix = dict(id='test_first.Cases.test_case', stage='regression', outcome='failed',
                          started_at='start', finished_at='finish', duration_seconds=0.25,
                          message='original failure')
            schema = dict(runner.child_context(root / 'test_first.py', 'regression', 'default', None),
                          schema_version=1, complete=True, exit_code=0)
            passed = dict(prefix, outcome='passed')
            unexplained = dict(id='test_first.Cases.test_unreported', stage='regression')
            wrong_fixture = dict(prefix, id='setUpClass (test_first.Other)', outcome='skipped',
                                 fixture_event=True, message='fixture unavailable')
            defects = (
                ('{broken', 'Cannot read child timing report', []),
                ('[]', 'Invalid child timing report schema', []),
                (json.dumps(schema), 'must contain a tests list', []),
                (json.dumps(dict(schema, tests=[prefix, {'id': 'missing'}])), 'position 2', [prefix]),
                (json.dumps(dict(schema, tests=[])), 'no complete case evidence', []),
                (json.dumps(dict(schema, tests=[dict(prefix, outcome='passed')], planned_tests=[
                    dict(id='test_first.Cases.test_case', stage='regression'),
                    dict(id='test_first.Cases.test_unreported', stage='regression'),
                ])), 'does not account for all planned cases', [dict(prefix, outcome='passed')]),
                (json.dumps(dict(schema, tests=[passed, wrong_fixture], planned_tests=[
                    dict(id=passed['id'], stage='regression'), unexplained,
                ], not_run=[dict(unexplained, reason='Fixture skipped: fixture unavailable')])),
                 'without matching setup fixture skip', [passed, wrong_fixture]),
            )
            real_run = subprocess.run
            for payload, reason, kept in defects:
                for mode, fail_fast, expected in (('diagnostic', False, 2), ('fast', False, 1),
                                                  ('diagnostic', True, 1)):
                    with self.subTest(reason=reason, mode=mode, fail_fast=fail_fast):
                        def run_child(command, **kwargs):
                            if command[command.index('--pattern') + 1] == 'test_first.py':
                                Path(command[command.index('--report') + 1]).write_text(payload)
                                return subprocess.CompletedProcess(command, 0)
                            return real_run(command, **kwargs)

                        report = runner.TimingReport(root / 'result.json', root, 'test*.py', True)
                        with patch.object(runner.subprocess, 'run', side_effect=run_child) as run:
                            code = runner.run_isolated(root, 'test*.py', 60, report=report,
                                                       mode=mode, fail_fast=fail_fast)
                        self.assertEqual(code, 1)
                        self.assertEqual(run.call_count, expected)
                        first = report.data['modules'][0]
                        self.assertEqual((first['path'], first['stage']), ('test_first.py', 'regression'))
                        self.assertEqual(first['outcome'], 'preflight_error')
                        self.assertTrue(first['test_report_available'])
                        self.assertFalse(first['test_report_complete'])
                        self.assertIn(reason, first['evidence_error'])
                        self.assertFalse(report.data['coverage_complete'])
                        self.assertEqual([r for r in report.data['tests'] if r['file'] == 'test_first.py'],
                                         [dict(row, file='test_first.py') for row in kept])
                        if expected == 2:
                            self.assertEqual(report.data['modules'][1]['outcome'], 'passed')

    def test_abnormal_child_exit_fails_validation(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_crash.py').write_text('# TEST_STAGE = TestStage.REGRESSION\n' 'import os\nos._exit(23)\n')
            report = root / 'report.json'
            result = self.run_modules(root, '--report', str(report))
            self.assertEqual(result.returncode, 1)
            self.assertIn('test_crash.py: FAIL (23)', result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data['exit_code'], 1)
            self.assertTrue(data['complete'])
            self.assertEqual(data['modules'][0]['exit_code'], 23)
            self.assertFalse(data['modules'][0]['test_report_complete'])
            self.assertFalse(data['coverage_complete'])
            self.assertTrue(data['not_run'])

    def test_child_acceptance_matches_launch_and_independent_runtime_discovery(self):
        with patch.object(sys, 'path', [str(RUNNER.parent), *sys.path]):
            spec = importlib.util.spec_from_file_location('child_context_probe', RUNNER)
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_selected.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                'class Cases(unittest.TestCase):\n def test_first(self): pass\n def test_second(self): pass\n')
            real_run = subprocess.run
            defects = {'directory': str(root / 'other'), 'pattern': 'test_other.py', 'isolated': True,
                       'stages': ['smoke'], 'source': {'path': 'foreign', 'sha256': '0' * 64},
                       'lost-case': None, 'missing-plan': None, 'foreign-plan': None}
            for defect, value in defects.items():
                with self.subTest(defect=defect):
                    def run_child(command, **kwargs):
                        result = real_run(command, capture_output=True, text=True, **kwargs)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        path = Path(command[command.index('--report') + 1])
                        data = json.loads(path.read_text())
                        if defect == 'lost-case':
                            data['tests'].pop()
                            data['planned_tests'].pop()
                        elif defect == 'missing-plan':
                            path.with_suffix('.plan.json').unlink(missing_ok=True)
                        elif defect == 'foreign-plan':
                            path.with_suffix('.plan.json').write_text('{}')
                        else:
                            data[defect] = value
                        path.write_text(json.dumps(data))
                        return result
                    report = runner.TimingReport(root / 'result.json', root, 'test*.py', True)
                    with patch.object(runner.subprocess, 'run', side_effect=run_child):
                        self.assertEqual(runner.run_isolated(root, 'test*.py', 60, report=report), 1)
                    self.assertFalse(report.data['coverage_complete'])
                    self.assertFalse(report.data['modules'][0]['test_report_complete'])
                    if defect in ('lost-case', 'missing-plan', 'foreign-plan'):
                        self.assertIn('discovery plan', report.data['modules'][0]['evidence_error'])
                        self.assertTrue(report.data['tests'], 'Retain results belonging to this launch')
                    else:
                        self.assertIn('launched', report.data['modules'][0]['evidence_error'])
                        self.assertEqual(report.data['tests'], [], 'Do not attribute foreign evidence to this file')

    def test_runtime_discovery_plan_preserves_custom_load_tests_selection(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_custom.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\nimport unittest\n'
                'class Cases(unittest.TestCase):\n def test_selected(self): pass\n'
                ' def test_helper(self): self.fail("not in runtime suite")\n'
                'def load_tests(loader, tests, pattern):\n'
                ' return unittest.TestSuite([Cases("test_selected")])\n')
            report = root / 'report.json'
            result = self.run_modules(root, '--report', str(report))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual([row['id'] for row in data['tests']], ['test_custom.Cases.test_selected'])
            self.assertTrue(data['coverage_complete'])

    def test_timing_includes_cleanup_and_preserves_outcomes_across_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test_outcomes.py').write_text(
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import time, unittest\n'
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
                '# TEST_STAGE = TestStage.REGRESSION\n' 'import unittest\n'
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
