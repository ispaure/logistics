"""Real harmless child processes prove the generic second-project boundary."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Event, Timer
import unittest

from build_manager import Executor, Phase, Plan
from build_manager.locking import workspace_lock
from build_manager.profiles import effective, load_profile, save_profile


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='second-project-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def phase(self, name, code, **options):
        return Phase(name, (sys.executable, '-c', code), str(self.root), **options)

    def plan(self, *phases, **options):
        return Plan('Different harmless project', 'contract', {'revision': 'synthetic-v1'},
                    phases, str(self.root / 'workspace'), **options)

    def run_plan(self, plan, **options):
        return Executor(**options).run(plan, self.root / 'result')

    def test_second_project_runs_without_importing_logistics_or_cloud_credentials(self):
        plan = self.plan(self.phase('hello', 'print("second project completed")'))
        plan.save(self.root / 'plan.json')
        result = self.run_plan(Plan.load(self.root / 'plan.json'))
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['source'], {'revision': 'synthetic-v1'})
        self.assertEqual((self.root / 'result/hello.log').read_text(), 'second project completed\n')
        self.assertNotIn('mobile.app', sys.modules)
        self.assertNotIn('features.application', sys.modules)

    def test_failure_blocks_dependents_but_runs_independent_and_cleanup_phases(self):
        result = self.run_plan(self.plan(self.phase('failed', 'raise SystemExit(4)'),
            self.phase('dependent', 'raise AssertionError("must not run")', dependencies=('failed',)),
            self.phase('independent', 'print("still useful")'),
            self.phase('cleanup', 'print("cleaned")', dependencies=('dependent',), always=True)))
        self.assertEqual([row['status'] for row in result['phases']], ['failed', 'skipped', 'passed', 'passed'])
        self.assertEqual(result['status'], 'failed')

    def test_timeout_terminates_real_child_and_still_writes_result(self):
        result = self.run_plan(self.plan(self.phase('stalled', 'import time; time.sleep(30)', timeout=.1)))
        self.assertEqual(result['phases'][0]['status'], 'timeout')
        self.assertEqual(json.loads((self.root / 'result/result.json').read_text())['status'], 'failed')
        self.assertLess(result['seconds'], 8)

    def test_cancellation_stops_current_work_and_never_starts_remaining_device(self):
        cancelled = Event()
        timer = Timer(.15, cancelled.set)
        timer.start()
        self.addCleanup(timer.cancel)
        result = self.run_plan(self.plan(self.phase('first-device', 'import time; time.sleep(30)'),
            self.phase('next-device', 'raise AssertionError("must not start")'),
            self.phase('cleanup', 'print("owned fixtures only")', always=True)), cancelled=cancelled)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual([row['status'] for row in result['phases']], ['cancelled', 'skipped', 'passed'])

    def test_unconfirmed_side_effect_does_not_launch_process(self):
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            self.run_plan(self.plan(self.phase('upload', 'raise AssertionError("never")'), effect='upload'))
        self.assertFalse((self.root / 'result').exists())

    def test_workspace_lock_prevents_concurrent_writer(self):
        with workspace_lock(self.root / 'lock'):
            with self.assertRaisesRegex(RuntimeError, 'Another operation'):
                with workspace_lock(self.root / 'lock'):
                    self.fail('two writers admitted')

    def test_secrets_and_multiline_keys_do_not_reach_logs_or_failure_summary(self):
        from unittest.mock import patch
        code = 'print("token=synthetic-secret"); print("-----BEGIN "+"PRIVATE KEY-----"); print("privatebytes"); print("-----END "+"PRIVATE KEY-----"); raise SystemExit(1)'
        with patch.dict(os.environ, {'GH_TOKEN': 'synthetic-secret'}):
            result = self.run_plan(self.plan(self.phase('provider', code)))
        outputs = ''.join(p.read_text() for p in (self.root / 'result').glob('*') if p.is_file())
        self.assertNotIn('synthetic-secret', outputs)
        self.assertNotIn('privatebytes', outputs)
        self.assertEqual(result['status'], 'failed')

    def test_invalid_dependency_and_unsafe_log_name_fail_before_execution(self):
        with self.assertRaises(ValueError):
            self.plan(self.phase('a', 'pass', dependencies=('missing',)))
        with self.assertRaises(ValueError):
            self.phase('../escape', 'pass')

    def test_expected_artifact_is_captured_and_missing_artifact_fails(self):
        artifact = self.root / 'prepared.json'
        code = f'from pathlib import Path; Path({str(artifact)!r}).write_text("verified version 7")'
        result = self.run_plan(self.plan(self.phase('prepare', code, artifacts=(str(artifact),))))
        recorded = result['phases'][0]['artifacts'][0]
        captured = Path(recorded['path'])
        self.assertEqual(captured.read_text(), 'verified version 7')
        artifact.write_text('new settings must not relabel old result')
        self.assertEqual(captured.read_text(), 'verified version 7')
        missing = Executor().run(self.plan(self.phase('prepare', 'pass', artifacts=(str(self.root / 'missing'),))),
                                 self.root / 'missing-result')
        self.assertEqual(missing['status'], 'failed')
        self.assertIn('Expected prepared artifact', missing['phases'][0]['error'])

    def test_workspace_conflict_is_a_structured_failure(self):
        plan = self.plan(self.phase('blocked', 'raise AssertionError("never")'))
        with workspace_lock(self.root / 'workspace/operation.lock'):
            result = self.run_plan(plan)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('Another operation', result['error'])

    @unittest.skipIf(os.name == 'nt', 'POSIX process-group orphan contract')
    def test_timeout_closes_pipe_held_by_descendant_after_parent_exits(self):
        code = 'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])'
        result = self.run_plan(self.plan(self.phase('orphan', code, timeout=.15)))
        self.assertEqual(result['phases'][0]['status'], 'timeout')
        self.assertLess(result['seconds'], 5)


class ProfileTests(unittest.TestCase):
    def test_precedence_preserves_effective_value_provenance(self):
        values, sources = effective({'group': 'default', 'tool': 'python'}, {'group': 'profile'},
            {'GROUP': 'environment'}, {'group': 'once'}, variables={'group': 'GROUP'})
        self.assertEqual(values, {'group': 'once', 'tool': 'python'})
        self.assertEqual(sources, {'group': 'run override', 'tool': 'repository default'})

    def test_profile_persists_references_and_rejects_secret_contents(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            save_profile(path, {'key_reference': 'protected/file.p8'}, allowed={'key_reference'})
            self.assertEqual(load_profile(path), {'key_reference': 'protected/file.p8'})
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                save_profile(path, {'private_key': 'secret'}, allowed={'private_key'})

    def test_build_reservation_handles_existing_explicit_and_duplicate_values(self):
        from build_manager.versions import next_number, reserve_number
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'numbers.json'
            self.assertEqual(next_number(path, existing=[4], minimum=3), 5)
            self.assertFalse(path.exists())
            self.assertEqual(reserve_number(path, existing=[4], minimum=3, maximum=20), 5)
            self.assertEqual(reserve_number(path, maximum=20, override='8'), 8)
            with self.assertRaises(ValueError):
                reserve_number(path, maximum=20, override='8')
            with self.assertRaises(ValueError):
                reserve_number(path, maximum=8)
