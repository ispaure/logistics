"""Fixture-only startup diagnostics preserve decisions and fail closed."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import base64
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mobile_build.native_tests.tests.logisticsmobile import startup_trace as trace


class Timer:
    def __init__(self, seconds, callback):
        self.seconds, self.callback, self.cancelled = seconds, callback, False
    def start(self):
        pass
    def cancel(self):
        self.cancelled = True


class StartupTraceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = SimpleNamespace(paths=SimpleNamespace(cache=Path(self.temp.name)),
            loop=asyncio.get_running_loop(), _impl=SimpleNamespace())
        self.previous = trace._current
        self.addCleanup(setattr, trace, '_current', self.previous)
        self.hooks = patch.object(trace, 'install_hooks')
        self.hooks.start()
        self.addCleanup(self.hooks.stop)
        self.output = patch('builtins.print')
        self.output.start()
        self.addCleanup(self.output.stop)

    async def test_watchdog_is_120_seconds_and_recreation_retires_old_deadline(self):
        old_failure, new_failure = Mock(), Mock()
        old = trace.install(self.app, timer_factory=Timer, failure=old_failure)
        other = SimpleNamespace(**vars(self.app))
        new = trace.install(other, timer_factory=Timer, failure=new_failure)
        self.assertEqual([t.seconds for t in new.timers], [15, 30, 60, 120])
        self.assertTrue(all(t.cancelled for t in old.timers))
        old.deadline()
        old_failure.assert_not_called()
        new.deadline()
        new_failure.assert_called_once()
        new.deadline()
        new_failure.assert_called_once()

    async def test_exercise_disarm_prevents_even_already_queued_timer_from_failing(self):
        failure = Mock()
        current = trace.install(self.app, timer_factory=Timer, failure=failure)
        current.disarm()
        for timer in current.timers:
            timer.callback()
        failure.assert_not_called()
        self.assertTrue(all(t.cancelled for t in current.timers))

    async def test_check_and_both_holds_disarm_only_when_coroutine_actually_enters(self):
        from mobile_build.native_tests.tests.logisticsmobile import __main__ as main
        package = main.__package__
        for name in ('exercise', 'hold_workspace', 'hold_navigation'):
            with self.subTest(operation=name):
                failure = Mock()
                current = trace.install(self.app, timer_factory=Timer, failure=failure)
                entered, release = asyncio.Event(), asyncio.Event()
                async def operation(owner):
                    self.assertIs(owner, self.app)
                    self.assertTrue(current.disarmed)
                    entered.set()
                    await release.wait()
                self.app._native_check_task = None
                self.app.workspace_hold = name == 'hold_workspace'
                self.app.navigation_hold = name == 'hold_navigation'
                self.app.show_documents = Mock()
                self.app.show_home = Mock()
                modules = {package + '.workspace_hold': SimpleNamespace(hold_workspace=operation),
                           package + '.navigation_hold': SimpleNamespace(hold_navigation=operation)}
                with patch.dict(sys.modules, modules), patch.object(main, 'exercise', operation):
                    main.NativeCheckApp.on_running(self.app)
                    task = self.app._native_check_task
                    self.assertFalse(current.disarmed)
                    main.NativeCheckApp.on_running(self.app)
                    self.assertIs(self.app._native_check_task, task)
                    await entered.wait()
                    current.deadline()
                    failure.assert_not_called()
                    self.assertFalse(task.done())  # Intentional holds remain alive.
                    self.assertTrue(all(timer.cancelled for timer in current.timers))
                    release.set()
                    await task

    async def test_evidence_is_bounded_and_contains_no_frame_locals(self):
        private_document = 'SECRET-DOCUMENT-NAME-DO-NOT-RECORD'
        current = trace.install(self.app, timer_factory=Timer, failure=Mock())
        for _ in range(1000):
            current.record('constant-event', phase=1)
        value = current.snapshot()
        self.assertLessEqual(len(value['records']), 80)
        self.assertLessEqual(current.emitted, 128)
        self.assertLessEqual(len(value['execution']['threads']), 16)
        self.assertLessEqual(len(value['execution']['tasks']), 24)
        for stack in value['execution']['threads']:
            self.assertLessEqual(len(stack), 12)
            for frame in stack:
                self.assertEqual(set(frame), {'file', 'function', 'line'})
                self.assertEqual(Path(frame['file']).name, frame['file'])
        self.assertNotIn(private_document, json.dumps(value))

    async def test_scheduler_flags_identify_stale_task_loop_without_task_repr(self):
        loop = asyncio.get_running_loop()
        stale_loop = object()
        self.app.startup_task = SimpleNamespace(done=lambda: False, cancelled=lambda: False,
                                               get_loop=lambda: loop)
        self.app._native_check_task = SimpleNamespace(done=lambda: False, cancelled=lambda: False,
                                                     get_loop=lambda: stale_loop)
        value = trace.scheduler_snapshot(self.app, loop)
        self.assertTrue(value['loop_running'])
        self.assertFalse(value['loop_closed'])
        self.assertTrue(value['current_loop_matches_captured'])
        self.assertTrue(value['startup_task']['loop_matches_captured'])
        self.assertFalse(value['_native_check_task']['loop_matches_captured'])
        self.assertFalse(value['_native_check_task']['loop_matches_current'])
        self.app.loop = stale_loop
        value = trace.scheduler_snapshot(self.app, loop)
        self.assertFalse(value['current_loop_matches_captured'])
        self.assertTrue(value['_native_check_task']['loop_matches_current'])
        self.assertFalse(value['startup_task']['loop_matches_current'])
        self.assertNotIn('0x', json.dumps(value))
        self.app.loop = loop

    async def test_failure_emits_standard_reassemblable_report_and_exit_one(self):
        output, exit_process = Mock(), Mock()
        report = dict(schema=1, suite='logistics-native-ui', success=False, cases=[],
            expected_cases=['required'], error='StartupWatchdogTimeout', source={'commit': 'fixture'})
        trace.emit_failure(Path(self.temp.name), report, output=output, pause=Mock(), exit_process=exit_process)
        rows = [call.args[0] for call in output.call_args_list]
        chunks = [json.loads(row.split('=', 1)[1]) for row in rows if row.startswith('LOGISTICS_NATIVE_UI_CHUNK=')]
        self.assertEqual([c['index'] for c in chunks], list(range(len(chunks))))
        self.assertTrue(all(c['count'] == len(chunks) and len(c['data']) <= 450 for c in chunks))
        self.assertEqual(json.loads(base64.b64decode(''.join(c['data'] for c in chunks))), report)
        self.assertEqual(json.loads((Path(self.temp.name) / 'logistics-native-ui-result.json').read_text()), report)
        self.assertEqual(rows[-1], '>>>>>>>>>> EXIT 1 <<<<<<<<<<')
        exit_process.assert_called_once_with(1)

    async def test_default_watchdog_failure_uses_exact_source_and_all_required_cases(self):
        import mobile
        from mobile_build.native_tests.tests.logisticsmobile import CASES
        folder = Path(self.temp.name) / 'mobile'
        folder.mkdir()
        source = {'logistics_commit': 'fixture', 'source_sha256': 'a' * 64}
        (folder / 'source.json').write_text(json.dumps(source))
        current = trace.install(self.app, timer_factory=Timer)
        with patch.object(mobile, '__file__', str(folder / '__init__.py')), \
                patch.object(trace, 'emit_failure') as emit:
            current.fail({'phase': 'fixture'})
        report = emit.call_args.args[1]
        self.assertFalse(report['success'])
        self.assertEqual(report['source'], source)
        self.assertEqual(report['cases'], [])
        self.assertEqual(report['expected_cases'], list(CASES))
        self.assertEqual(len(CASES), 35)
        self.assertEqual(report['target'], 'android')
        self.assertEqual(report['suite'], 'logistics-native-ui')
        self.assertIn('StartupWatchdogTimeout', report['error'])

    async def test_snapshot_write_failure_still_runs_deadline_failure_handler(self):
        failure = Mock()
        current = trace.install(self.app, timer_factory=Timer, failure=failure)
        with patch.object(current, 'sample', side_effect=OSError('fixture')):
            current.deadline()
        failure.assert_called_once()

    async def test_cover_hooks_sample_but_do_not_override_readiness_or_draw(self):
        from mobile.startup import AndroidStartupCover
        current = trace.install(self.app, timer_factory=Timer, failure=Mock())
        cover = SimpleNamespace(app=self.app, future=asyncio.get_running_loop().create_future())
        native = Mock()
        native.getWidth.return_value = 900
        native.getHeight.return_value = 800
        native.getVisibility.return_value = 0
        self.app.navigation = SimpleNamespace(_impl=SimpleNamespace(native=native, native_content=native))
        current.before_draw(cover)
        self.assertFalse(cover.future.done())
        self.assertTrue(current.last_geometry['root_layout_requested'])
        self.assertEqual(current.frames, 1)
        # Actual method wrappers must return the original result/exception.
        self.hooks.stop()
        with patch.object(trace, '_hooks_installed', False), \
                patch.object(AndroidStartupCover, 'before_draw', return_value='original') as draw, \
                patch.object(AndroidStartupCover, 'ready', side_effect=ValueError('original')):
            # Restore these explicitly: install_hooks assigns methods directly.
            old_draw, old_ready = AndroidStartupCover.before_draw, AndroidStartupCover.ready
            try:
                trace.install_hooks()
                self.assertEqual(AndroidStartupCover.before_draw(cover), 'original')
                draw.assert_called_once_with(cover)
                frames = current.frames
                current.disarm()
                # The original product listener still runs, but diagnostics
                # must stop all Java geometry reads once the check begins.
                AndroidStartupCover.before_draw(cover)
                self.assertEqual(current.frames, frames)
                self.assertEqual(draw.call_count, 2)
                with self.assertRaisesRegex(ValueError, 'original'):
                    await AndroidStartupCover.ready(cover)
            finally:
                AndroidStartupCover.before_draw, AndroidStartupCover.ready = old_draw, old_ready
