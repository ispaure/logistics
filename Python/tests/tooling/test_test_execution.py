"""Execution profiles preserve independent diagnostics and explicit unrun coverage."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

RUNNER = Path(__file__).parents[1] / 'run_regressions.py'


class TestExecutionPolicyTests(unittest.TestCase):
    def fixture(self, root, name, stage, fails=False):
        (root / name).write_text(
            '# TEST_STAGE = TestStage.' + stage + '\nimport unittest\n'
            'class Example(unittest.TestCase):\n'
            ' def test_first(self): self.assertFalse(' + repr(fails) + ')\n'
            ' def test_second(self): self.assertTrue(True)\n')

    def run_fixture(self, root, *args):
        report = root / 'result.json'
        result = subprocess.run([sys.executable, str(RUNNER), str(root), '--isolate-modules',
                                 '--report', str(report), *args], capture_output=True, text=True, timeout=30)
        return result, json.loads(report.read_text())

    def test_fast_mode_stops_after_smoke_and_diagnostic_mode_continues(self):
        for mode in ('fast', 'diagnostic'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, 'test_z_smoke.py', 'SMOKE', fails=True)
                self.fixture(root, 'test_a_regression.py', 'REGRESSION')
                result, report = self.run_fixture(root, '--mode', mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(report['modules'][0]['path'], 'test_z_smoke.py')
                self.assertEqual(len(report['modules']), 1 if mode == 'fast' else 2)
                self.assertEqual(bool(report['not_run']), mode == 'fast')
                self.assertEqual(report['coverage_complete'], mode != 'fast')

    def test_fail_fast_records_unrun_methods_and_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'test_a.py', 'REGRESSION', fails=True)
            self.fixture(root, 'test_b.py', 'REGRESSION')
            result, report = self.run_fixture(root, '--fail-fast')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(report['tests']), 1)
            self.assertTrue(any(r.get('id', '').endswith('test_second') for r in report['not_run']))
            self.assertTrue(any(r.get('file') == 'test_b.py' for r in report['not_run']))
            self.assertFalse(report['coverage_complete'])

    def test_daily_profile_excludes_extended_and_inventory_never_imports(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'test_smoke.py', 'SMOKE')
            self.fixture(root, 'test_extended.py', 'EXTENDED')
            result, report = self.run_fixture(root, '--profile', 'daily')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([r['path'] for r in report['modules']], ['test_smoke.py'])
            (root / 'test_extended.py').write_text('# TEST_STAGE = TestStage.EXTENDED\nraise RuntimeError("must not import")\n')
            result = subprocess.run([sys.executable, str(RUNNER), str(root), '--inventory'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)), 2)

    def test_unclassified_file_blocks_every_test_before_any_process_starts(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'test_a.py', 'SMOKE')
            (root / 'test_unclassified.py').write_text('raise RuntimeError("must not import")')
            result, report = self.run_fixture(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn('test_unclassified.py', result.stderr)
            self.assertEqual(report['modules'], [])

    def test_mixed_file_and_inherited_methods_run_in_their_stages(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test_mixed.py').write_text('''from commonUtils.testing.stages import TestStage, stage
import unittest
TEST_STAGE = TestStage.REGRESSION
class Base(unittest.TestCase):
 def test_regular(self): pass
 @stage(TestStage.SMOKE)
 def test_smoke(self): pass
@stage(TestStage.EXTENDED)
class Derived(Base): pass
''')
            result, report = self.run_fixture(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([row['stage'] for row in report['modules']], ['smoke', 'regression', 'extended'])
            self.assertEqual(len(report['tests']), 4)
            extended = [row['id'] for row in report['tests'] if row['stage'] == 'extended']
            self.assertEqual(extended, ['test_mixed.Derived.test_regular'])

    def test_fixture_failure_blocks_later_tests_and_runs_registered_cleanup(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'cleaned'
            (root / 'test_fixture.py').write_text(
                '# TEST_STAGE = TestStage.SMOKE\nimport unittest\nfrom pathlib import Path\n'
                'class Cases(unittest.TestCase):\n'
                ' def setUp(self):\n'
                '  self.addCleanup(lambda: Path(' + repr(str(marker)) + ').touch())\n'
                '  self.fail("fixture setup failed")\n'
                ' def test_body(self): pass\n')
            self.fixture(root, 'test_later.py', 'REGRESSION')
            result, report = self.run_fixture(root, '--mode', 'fast')
            self.assertEqual(result.returncode, 1)
            self.assertTrue(marker.exists())
            self.assertTrue(any(row.get('file') == 'test_later.py' for row in report['not_run']))

    def test_bridge_gates_later_stages_but_diagnostic_mode_continues(self):
        from logistics_build import test_structure
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rows = []
            for name, stage in [('Smoke', 'smoke'), ('Regular', 'regression')]:
                path = root / (name + '_test.go')
                path.write_text('func Test' + name + '(t *testing.T) {}')
                rows.append(dict(path=path.name, stage=stage))
            for mode, expected in [('fast', 1), ('diagnostic', 2)]:
                with self.subTest(mode=mode), patch.object(test_structure, 'ROOT', root), \
                        patch.object(test_structure.subprocess, 'run') as run:
                    run.return_value.returncode = 1
                    self.assertEqual(test_structure.run_bridge(rows, 'full', mode, False), 1)
                    self.assertEqual(run.call_count, expected)
                    self.assertIn('^(TestSmoke)$', run.call_args_list[0].args[0])

    def test_duration_order_is_optional_and_rejects_incompatible_reports(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'test_a.py', 'REGRESSION')
            self.fixture(root, 'test_b.py', 'REGRESSION')
            result, report = self.run_fixture(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report['modules'][0]['duration_seconds'] = 10
            report['modules'][1]['duration_seconds'] = 1
            history = root / 'history.json'
            history.write_text(json.dumps(report))
            result, reordered = self.run_fixture(root, '--timings', str(history))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([row['path'] for row in reordered['modules']], ['test_b.py', 'test_a.py'])
            report['platform'] = 'different host'
            history.write_text(json.dumps(report))
            result, rejected = self.run_fixture(root, '--timings', str(history))
            self.assertEqual(result.returncode, 2)
            self.assertEqual(rejected['modules'], [])

    def test_project_inventory_rejects_malformed_roots_and_never_imports_sources(self):
        from logistics_build.test_structure import inventory
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'tests').mkdir()
            (root / 'tests/test_source.py').write_text(
                '# TEST_STAGE = TestStage.SMOKE\nraise RuntimeError("inventory must not import")\n')
            manifest = root / 'test-structure.json'
            row = dict(owner='fixture', directory='tests', patterns=['test*.py'])
            manifest.write_text(json.dumps(dict(schema=1, roots=[row])))
            self.assertEqual(inventory(root)[0]['stage'], 'smoke')
            for field, value in [('directory', '/tmp'), ('patterns', 'test*.py'), ('owner', None)]:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    manifest.write_text(json.dumps(dict(schema=1, roots=[dict(row, **{field: value})])))
                    inventory(root)

    def test_successful_process_exit_without_case_evidence_is_a_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test_early_exit.py').write_text(
                '# TEST_STAGE = TestStage.SMOKE\nimport os\nos._exit(0)\n')
            self.fixture(root, 'test_later.py', 'REGRESSION')
            result, report = self.run_fixture(root, '--mode', 'fast')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(report['coverage_complete'])
            self.assertTrue(report['not_run'])
            self.assertEqual(len(report['modules']), 1)

    def test_junit_and_live_progress_preserve_each_cases_stage(self):
        from build_manager.test_results import read_junit
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, 'test_smoke.py', 'SMOKE')
            self.fixture(root, 'test_regular.py', 'REGRESSION')
            junit = root / 'result.xml'
            with patch.dict(os.environ, BUILD_MANAGER_TEST_PROGRESS='1'):
                result, _ = self.run_fixture(root, '--junit', str(junit))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([case['stage'] for case in read_junit(junit)],
                             ['smoke', 'smoke', 'regression', 'regression'])
            events = [json.loads(line.removeprefix('@@BUILD_MANAGER_TEST@@'))
                      for line in result.stdout.splitlines() if line.startswith('@@BUILD_MANAGER_TEST@@')]
            cases = [event for event in events if event['kind'] == 'test_finished']
            self.assertEqual([event['stage'] for event in cases],
                             ['smoke', 'smoke', 'regression', 'regression'])
