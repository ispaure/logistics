"""The native pointer QA fixture must respect the real palm grace contract."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import AsyncMock

from commonUtils.testing.stages import TestStage
from logistics_build.build_retention import scratch

TEST_STAGE = TestStage.REGRESSION
ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / 'mobile_build/native_tests/tests/logisticsmobile/notebook_pointer_checks.py'
spec = importlib.util.spec_from_file_location('native_notebook_pointer_fixture', PATH)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class NativePointerReportTests(unittest.TestCase):
    def test_original_javascript_failure_and_stack_survive(self):
        with self.assertRaisesRegex(AssertionError, 'Explicit finger drawing failed') as caught:
            fixture.pointer_report(json.dumps(dict(error='Error: Explicit finger drawing failed', stack='pointer.js:42')))
        self.assertIn('pointer.js:42', str(caught.exception))

    def test_missing_or_invalid_report_is_a_named_fixture_failure(self):
        for value in (None, 'null', '[]'):
            with self.subTest(value=value), self.assertRaisesRegex(AssertionError, 'Notebook pointer JavaScript'):
                fixture.pointer_report(value)

    def test_js_cleanup_detail_does_not_replace_the_original_error(self):
        with self.assertRaisesRegex(AssertionError, 'primary failure') as caught:
            fixture.pointer_report(json.dumps(dict(error='primary failure', stack='primary.js:1',
                                                   cleanup_error='draw failed', cleanup_stack='restore.js:2')))
        self.assertIn('draw failed', caught.exception.__notes__[0])

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the pure V8 pointer fixture driver')
    def test_actual_input_guard_and_fixture_phases_in_v8(self):
        bundle = dict(begin=fixture.POINTER_CHECKS, ready=fixture.POINTER_READY,
                      complete=fixture.POINTER_FINGER_CHECKS, cleanup=fixture.POINTER_CLEANUP)
        for name in ('palm', 'input', 'zoom'):
            bundle[name] = (ROOT / f'Python/features/notebooks/assets/{name}.js').read_text()
        with scratch(ROOT) as work:
            path = work / 'pointer-contract.json'
            path.write_text(json.dumps(bundle))
            result = subprocess.run(['node', str(ROOT / 'Python/tests/notebooks/native_pointer_contract_logic.js'), str(path)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report['passed'])
            self.assertEqual(report['release_grace_ms'], 250)


class NativePointerPhaseTests(unittest.IsolatedAsyncioTestCase):
    def panel(self, evaluate):
        from types import SimpleNamespace
        return SimpleNamespace(web=SimpleNamespace(evaluate_javascript=evaluate, _impl=object()))

    async def test_second_phase_waits_for_actual_guard_and_always_cleans_up(self):
        values = {
            fixture.POINTER_CHECKS: dict(release_grace_blocked=True),
            fixture.POINTER_FINGER_CHECKS: dict(finger_drawing=True, release_grace_recovered=True),
        }
        gates = iter((True, False))
        async def evaluate(script):
            if script == fixture.POINTER_CLEANUP:
                return True
            if script == fixture.POINTER_READY:
                return json.dumps(dict(blocked=next(gates)))
            return json.dumps(values[script])
        callback = AsyncMock(side_effect=evaluate)
        report = await fixture.exercise_pointer_input(self.panel(callback))
        self.assertTrue(report['finger_drawing'])
        self.assertEqual([call.args[0] for call in callback.await_args_list], [fixture.POINTER_CHECKS,
                         fixture.POINTER_READY, fixture.POINTER_READY, fixture.POINTER_FINGER_CHECKS, fixture.POINTER_CLEANUP])

    async def test_js_failure_keeps_original_error_even_when_cleanup_fails(self):
        async def evaluate(script):
            if script == fixture.POINTER_CLEANUP:
                raise RuntimeError('retired test view')
            return json.dumps(dict(error='Error: Explicit finger drawing failed', stack='pointer.js:42'))
        callback = AsyncMock(side_effect=evaluate)
        with self.assertRaisesRegex(AssertionError, 'Explicit finger drawing failed') as caught:
            await fixture.exercise_pointer_input(self.panel(callback))
        self.assertIn('retired test view', caught.exception.__notes__[0])
        self.assertEqual(callback.await_args_list[-1].args[0], fixture.POINTER_CLEANUP)

    async def test_no_second_phase_after_missing_json_and_cleanup_still_runs(self):
        callback = AsyncMock(return_value=None)
        with self.assertRaisesRegex(AssertionError, 'returned no JSON report'):
            await fixture.exercise_pointer_input(self.panel(callback))
        self.assertEqual([call.args[0] for call in callback.await_args_list], [fixture.POINTER_CHECKS, fixture.POINTER_CLEANUP])

    async def test_existing_fixture_is_not_cleaned_up_by_a_rejected_start(self):
        callback = AsyncMock(return_value=json.dumps(dict(error='Pointer fixture is already active',
                                                          stack='fixture.js:1', fixture_owned=False)))
        with self.assertRaisesRegex(AssertionError, 'already active'):
            await fixture.exercise_pointer_input(self.panel(callback))
        self.assertEqual(callback.await_count, 1)
