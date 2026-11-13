"""Bounded file scheduling keeps gates, evidence and command ownership intact."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event, Lock
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import patch
import json
import os
import signal
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import parallel_regressions as parallel
from regression_timing import TimingReport


class SchedulingTests(unittest.TestCase):
    def exercise(self, levels, *, fail=(), fail_fast=False, mode='diagnostic', exclusive=()):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = [(stage, SimpleNamespace(path=root / f'test_{i}.py',
                     inventory=lambda stage=stage: [dict(case='Case.test_case', stage=stage.value)]))
                    for i, stage in enumerate(levels)]
            report = TimingReport(root / 'report.json', root, 'test*.py', True)
            intervals, active, maximum = {}, set(), [0]
            lock = Lock()
            barrier = Barrier(2)
            def execute(index, cancelled):
                with lock:
                    active.add(index)
                    maximum[0] = max(maximum[0], len(active))
                    intervals[index] = [monotonic()]
                if index < 2:
                    barrier.wait(timeout=2)
                sleep(.06 if index == 0 else .02)
                with lock:
                    active.remove(index)
                    intervals[index].append(monotonic())
                stage = levels[index].value
                outcome = 'failed' if index in fail else 'passed'
                return int(index in fail), dict(coverage_complete=True, not_run=[],
                    modules=[dict(path=f'test_{index}.py', stage=stage, outcome=outcome, exit_code=int(index in fail))],
                    tests=[dict(id=f'test_{index}.Case.test_case', stage=stage, outcome=outcome, file=f'test_{index}.py')])
            with patch.object(parallel, 'eligible', side_effect=lambda path: int(path.stem[5:]) not in exclusive):
                code = parallel.schedule(plan, execute, report, root, workers=2, mode=mode,
                                         fail_fast=fail_fast, cancelled=Event())
            return code, report.data, intervals, maximum[0]

    def test_bounded_overlap_exclusive_barrier_and_deterministic_results(self):
        code, data, intervals, maximum = self.exercise([TestStage.REGRESSION] * 5, exclusive=(2,))
        self.assertEqual((code, maximum), (0, 2))
        self.assertEqual([r['path'] for r in data['modules']], [f'test_{i}.py' for i in range(5)])
        self.assertGreater(intervals[2][0], max(intervals[i][1] for i in (0, 1)))
        self.assertLess(intervals[2][1], min(intervals[i][0] for i in (3, 4)))
        self.assertLess(intervals[1][1], intervals[0][1], 'Completion order really differs from report order')

    def test_failed_smoke_stops_later_stages_and_accounts_for_unstarted_files(self):
        code, data, intervals, _ = self.exercise([TestStage.SMOKE] * 2 + [TestStage.REGRESSION, TestStage.EXTENDED],
                                               fail=(0,), mode='fast')
        self.assertEqual(code, 1)
        self.assertEqual(set(intervals), {0, 1})
        self.assertEqual([r['file'] for r in data['not_run']], ['test_2.py', 'test_3.py'])
        self.assertTrue(all(r['reason'] == 'Smoke gate failed' for r in data['not_run']))
        self.assertFalse(data['coverage_complete'])

    def test_fail_fast_drains_inflight_work_without_starting_another_file(self):
        code, data, intervals, _ = self.exercise([TestStage.REGRESSION] * 4, fail=(1,), fail_fast=True)
        self.assertEqual(code, 1)
        self.assertEqual(set(intervals), {0, 1})
        self.assertEqual(len(data['tests']), 2)
        self.assertEqual(len(data['not_run']), 2)

    def test_new_files_are_exclusive_and_managed_or_native_hosts_cannot_overcommit(self):
        with patch.dict(os.environ, QT_QPA_PLATFORM='offscreen', TOGA_BACKEND='', BUILD_MANAGER_TEST_PROGRESS='0', BUILD_MANAGER_RESERVED_TEST_WORKERS=''):
            self.assertTrue(parallel.eligible(parallel.ROOT / next(iter(parallel.QT_FILES))))
            self.assertFalse(parallel.eligible(parallel.ROOT / 'Python/tests/version_control/test_new.py'))
            for group in parallel.QT_GROUPS:
                self.assertFalse(parallel.eligible(parallel.ROOT / group / 'test_new.py'))
                self.assertTrue(all((parallel.ROOT / group / name).is_file() for name in parallel.QT_GROUPS[group]))
            for excluded in ('Python/tests/editing/test_notes_library_integration.py',
                             'Python/tests/editing/test_text_editor_dataview.py',
                             'Python/commonUtils/tests/browser/test_entry_browser.py',
                             'Python/commonUtils/tests/markdown/test_markdown_presentation.py'):
                self.assertFalse(parallel.eligible(parallel.ROOT / excluded))
            with patch.object(sys, 'platform', 'darwin'):
                parallel.require_parallel_environment()
                with patch.dict(os.environ, BUILD_MANAGER_TEST_PROGRESS="1", BUILD_MANAGER_RESERVED_TEST_WORKERS="4"):
                    parallel.require_parallel_environment(4)
                    with self.assertRaises(ValueError):
                        parallel.require_parallel_environment(8)
                for environment in ({'QT_QPA_PLATFORM': 'cocoa'}, {'TOGA_BACKEND': 'toga_dummy'},
                                    {'BUILD_MANAGER_TEST_PROGRESS': '1'}):
                    with patch.dict(os.environ, environment), self.assertRaises(ValueError):
                        parallel.require_parallel_environment()
            with patch.object(sys, 'platform', 'linux'), self.assertRaises(ValueError):
                parallel.require_parallel_environment()


@unittest.skipUnless(sys.platform == 'darwin', 'The opt-in is validated only on macOS')
class ProcessEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.runtime = self.root / 'tmp'
        self.runtime.mkdir()
        self.report = self.root / 'report.json'
        self.junit = self.root / 'report.xml'
        self.wrapper = self.root / 'invoke.py'
        self.wrapper.write_text(f'''import sys
sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
import run_regressions as runner
import parallel_regressions as parallel
parallel.eligible = lambda path: True
if '--short-timeout' in sys.argv:
    sys.argv.remove('--short-timeout')
    runner.ISOLATED_FILE_TIMEOUT = 1
raise SystemExit(runner.main())
''')
        self.environment = dict(os.environ, QT_QPA_PLATFORM='offscreen', TOGA_BACKEND='',
            BUILD_MANAGER_TEST_PROGRESS='0', TMPDIR=str(self.runtime), TMP=str(self.runtime), TEMP=str(self.runtime))

    def fixture(self, name, body, stage='REGRESSION'):
        (self.root / name).write_text(f'# TEST_STAGE = TestStage.{stage}\n' + body)

    def command(self, workers=2, extra=()):
        return [sys.executable, str(self.wrapper), str(self.root), '--isolate-modules', '--workers', str(workers),
                '--report', str(self.report), '--junit', str(self.junit), *extra]

    def run_fixture(self, workers=2, extra=()):
        result = subprocess.run(self.command(workers, extra), env=self.environment,
                                capture_output=True, text=True, timeout=15)
        data = json.loads(self.report.read_text())
        return result, data

    def test_assertion_failure_keeps_matched_case_and_junit_file_identity(self):
        self.fixture('test_a.py', 'import unittest\nclass A(unittest.TestCase):\n def test_failure(self): self.fail("deliberate")\n')
        self.fixture('test_b.py', 'import unittest\nclass B(unittest.TestCase):\n def test_pass(self): pass\n')
        before, serial = self.run_fixture(1)
        after, concurrent = self.run_fixture(2)
        self.assertEqual((before.returncode, after.returncode), (1, 1), after.stderr)
        identity = lambda data: [(r['file'], r['stage'], r['id'], r['outcome']) for r in data['tests']]
        self.assertEqual(identity(serial), identity(concurrent))
        self.assertEqual([r['outcome'] for r in concurrent['tests']], ['failed', 'passed'])
        nodes = ET.parse(self.junit).getroot().findall('testcase')
        self.assertEqual({n.get('file') for n in nodes if n.get('classname') != 'Logistics.runner'}, {'test_a.py', 'test_b.py'})

    def slow_fixture(self, name, marker):
        program = ('import json,os,subprocess,sys,time; from pathlib import Path; '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
            f'Path({str(marker)!r}).write_text(json.dumps([os.getpid(),child.pid])); time.sleep(30)')
        self.fixture(name, 'import unittest,sys\nfrom features.git.runner import GitRunner\n'
            'class Cases(unittest.TestCase):\n def test_a_completed(self): pass\n'
            f' def test_b_waiting(self): GitRunner().run(["-c", {program!r}], external=sys.executable)\n')

    def assert_retired(self, markers):
        groups = [json.loads(path.read_text()) for path in markers if path.exists()]
        pids = [pid for group in groups for pid in group]
        deadline = monotonic() + 3
        while pids:
            result = subprocess.run(['/bin/ps', '-p', ','.join(map(str, pids)), '-o', 'pid=,stat='],
                                    capture_output=True, text=True, timeout=3)
            live = [line for line in result.stdout.splitlines() if not line.split()[1].startswith('Z')]
            if not live:
                break
            if monotonic() >= deadline:
                # Explicit fixture cleanup also runs when the regression fails.
                for group in groups:
                    try:
                        os.killpg(group[0], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                self.fail(f'Owned command processes survived: {live}')
            sleep(.05)
        self.assertFalse(list(self.runtime.iterdir()), 'Parent-owned child temporary files survived')

    def test_timeout_preserves_completed_case_and_retires_nested_command_group(self):
        marker = self.root / 'nested.json'
        self.slow_fixture('test_a.py', marker)
        result, data = self.run_fixture(extra=('--short-timeout',))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(data['modules'][0]['outcome'], 'timeout')
        self.assertTrue(any(r['id'].endswith('test_a_completed') and r['outcome'] == 'passed' for r in data['tests']))
        self.assertTrue(marker.exists(), result.stderr)
        self.assert_retired([marker])

    def assert_cancelled_pool(self, workers):
        markers = [self.root / f'nested-{i}.json' for i in range(workers)]
        for name, marker in zip((f'test_{i}.py' for i in range(workers)), markers):
            self.slow_fixture(name, marker)
        self.fixture('test_z.py', 'import unittest\nclass C(unittest.TestCase):\n def test_unstarted(self): pass\n')
        with (self.root / 'output.log').open('w') as output:
            process = subprocess.Popen(self.command(workers), env=self.environment, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            try:
                deadline = monotonic() + 6
                while not all(p.exists() for p in markers) and monotonic() < deadline:
                    sleep(.02)
                self.assertTrue(all(p.exists() for p in markers), 'All workers must start before cancellation')
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=8), 130)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
        data = json.loads(self.report.read_text())
        self.assertTrue(data['complete'])
        self.assertTrue(data['cancelled'])
        self.assertFalse(data['coverage_complete'])
        self.assertTrue(any(r.get('file') == 'test_z.py' for r in data['not_run']))
        self.assertEqual(sum(r['id'].endswith('test_a_completed') for r in data['tests']), workers)
        omitted = [node for node in ET.parse(self.junit).getroot().findall('testcase')
                   if node.get('classname') == 'Logistics.not_run' and node.get('file') == 'test_z.py']
        self.assertEqual([node.get('name') for node in omitted], ['C.test_unstarted'])
        self.assertIsNotNone(omitted[0].find('skipped'))
        self.assert_retired(markers)

    def test_sigterm_cancels_both_workers_accounts_for_unstarted_and_cleans_nested_helpers(self):
        self.assert_cancelled_pool(2)

    def test_sigterm_retires_eight_workers_and_all_nested_command_helpers(self):
        self.assert_cancelled_pool(8)


if __name__ == '__main__':
    unittest.main()
