"""Native WebView probes require real text after provisional navigation settles."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import unittest
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from mobile_build.native_tests.tests.logisticsmobile.web_checks import wait_for_text, wait_for_transfer_surface, verify_native_transfer_fallback
from mobile_build.native_tests.tests.logisticsmobile.navigation_trace import native_event
from mobile_build.validation import ios_startup_recovery as recovery


class NativeStartupRecoveryTests(unittest.TestCase):
    device = 'A89B23F3-EEE5-4640-BE63-14C71AF0364A'
    cases = ('first', 'second')

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.logs = self.root / 'logs'
        self.logs.mkdir()
        self.source = dict(logistics_commit='a' * 40, commonUtils_commit='b' * 40, dirty=False)
        self.source_path = self.root / 'source.json'
        self.source_path.write_text(json.dumps(self.source))
        self.report = dict(schema=1, suite='logistics-native-ui', target='ios',
            backend='toga_iOS.app', success=False, source=self.source,
            cases=['first'], expected_cases=list(self.cases))
        self.tools = SimpleNamespace(contract=SimpleNamespace(CASES=self.cases),
            simulator_report=Mock(return_value=self.report), verify_native_diagnostics=Mock(),
            verify_prebuilt_ios=Mock())
        self.write_evidence()

    def write_evidence(self):
        started = time.time_ns()
        (self.logs / 'ios-native-ui-device.json').write_text(json.dumps(dict(
            device=self.device, started_ns=started)))
        state = dict(platform_backend='toga_iOS.widgets.webview', parent=True, window=True,
                     loading=True, progress=.1, web_process_pid=0, provisional_process_pid=0)
        self.error = "RuntimeError: WebView did not render 'Transfer details'; last value=None, url='app-document://logistics.invalid/transfer/', native=" + repr(state)
        (self.logs / 'ios-native-ui-error.txt').write_text(self.error)
        (self.logs / 'ios-native-ui-fault.log').write_text('')
        (self.logs / 'ios-native-ui.log').write_text('original failed native attempt\n')
        (self.logs / 'ios-native-ui-owned.json').write_text(json.dumps(dict(
            device=self.device, name='Logistics Native Gate ' + 'a' * 32)))
        (self.logs / 'ios-webview-stall-900.json').write_text(json.dumps(dict(
            pid=900, status='sampled', sample_exit_code=0, thread_stacks_present=True,
            sent_ns=started, received_ns=time.time_ns(),
            executable='/CoreSimulator/Devices/' + self.device + '/data/Logistics Mobile.app/Logistics Mobile')))
        self.sample_path = self.logs / 'ios-webview-stall-900.sample.txt'
        self.sample_path.write_text('Analysis of sampling Logistics Mobile (pid 900)\n' + ''.join(
            f'    645 Thread_{number}   DispatchQueue_1: com.apple.ScreenTimeSettingsServices.ScreenTimeWebBrowserSettings.XPCClient (serial)\n'
            '    + completeTaskWithClosure(swift::AsyncContext*, swift::SwiftError*)\n'
            '    + ScreenTimeSettingsServices\n'
            '    + xpc_connection_send_message_with_reply_sync\n'
            '    + mach_msg2_trap\n' for number in (11, 12, 13)))
        return started

    def qualify(self):
        return recovery.qualification(self.logs, self.device, 0, self.source,
            self.tools.simulator_report, cpus=3, expected_cases=self.cases)

    def test_attempt_archive_keeps_both_rpc_receipt_and_service_stack(self):
        with TemporaryDirectory() as directory:
            logs = Path(directory) / 'logs'
            logs.mkdir()
            receipt = logs / 'ios-screen-time-rpc-123.json'
            sample = logs / 'ios-screen-time-rpc-123.sample.txt'
            receipt.write_text('{"pid": 456, "status": "sampled"}')
            sample.write_text('Thread_789 DispatchQueue_1')
            saved = recovery.preserve(logs, Path(directory) / 'attempt-1')
            self.assertEqual(set(saved), {receipt.name, sample.name})
            self.assertEqual((Path(directory) / 'attempt-1' / sample.name).read_text(), sample.read_text())

    def test_current_zero_process_and_all_blocked_swift_workers_qualify(self):
        proof = self.qualify()
        self.assertEqual(proof['blocked_workers'], [11, 12, 13])
        self.assertEqual(proof['cpus'], 3)

    def test_a_spare_worker_or_repeated_stack_never_proves_starvation(self):
        sample = self.sample_path.read_text()
        self.sample_path.write_text(sample.replace('Thread_13', 'Thread_12'))
        self.assertIsNone(self.qualify())
        self.sample_path.write_text(sample.replace('completeTaskWithClosure', 'ordinary_callback'))
        self.assertIsNone(self.qualify())

    def test_native_fault_or_foreign_source_cannot_recover(self):
        (self.logs / 'ios-native-ui-fault.log').write_text('Fatal Python error: Bus error')
        self.assertIsNone(self.qualify())
        (self.logs / 'ios-native-ui-fault.log').write_text('')
        self.report['source'] = dict(self.source, logistics_commit='c' * 40)
        self.assertIsNone(self.qualify())

    def test_stale_receipt_or_another_device_cannot_recover(self):
        path = self.logs / 'ios-webview-stall-900.json'
        row = json.loads(path.read_text())
        path.write_text(json.dumps(dict(row, sent_ns=0)))
        self.assertIsNone(self.qualify())
        path.write_text(json.dumps(dict(row, executable='/another/device/Logistics Mobile.app/Logistics Mobile')))
        self.assertIsNone(self.qualify())

    def test_render_assertions_live_processes_and_detached_views_are_not_infrastructure(self):
        self.assertFalse(recovery.stalled_view('AssertionError: wrong contents'))
        for before, after in [("'web_process_pid': 0", "'web_process_pid': 42"),
                              ("'provisional_process_pid': 0", "'provisional_process_pid': 42"),
                              ("'parent': True", "'parent': False"),
                              ("'window': True", "'window': False"),
                              ("'progress': 0.1", "'progress': 1.0"),
                              ('app-document://', 'https://')]:
            with self.subTest(change=after):
                self.assertFalse(recovery.stalled_view(self.error.replace(before, after)))

    def test_complete_suite_is_repeated_once_and_both_attempts_are_retained(self):
        first = RuntimeError('Native app UI run failed (232): WebView did not render')
        calls = []
        result = dict(success=True, source=self.source, cases=list(self.cases))
        def operation():
            calls.append(True)
            if len(calls) == 1:
                self.write_evidence()
                raise first
            self.assertTrue(list(self.logs.glob('ios-startup-recovery/*/*/attempt-1/ios-native-ui.log')))
            (self.logs / 'ios-native-ui.log').write_text('complete second native suite passed\n')
            return result
        with patch.object(recovery.os, 'cpu_count', return_value=3), \
                patch('build_manager.apple_simulators.AppleSimulators') as client, \
                patch.object(recovery, 'process_absent', return_value=True), patch('builtins.print'):
            client.return_value.matching.return_value = dict(udid=self.device, state='Booted')
            actual = recovery.run(operation, self.device, tools=self.tools,
                logs=self.logs, source_path=self.source_path)
        self.assertIs(actual, result)
        self.assertEqual(len(calls), 2)
        journal = json.loads(next(self.logs.glob('ios-startup-recovery/*/*/recovery.json')).read_text())
        self.assertEqual(journal['status'], 'passed')
        self.assertIn('ios-native-ui.log', journal['first_attempt'])
        self.assertIn('ios-native-ui.log', journal['second_attempt'])

    def test_a_failed_recovery_is_not_repeated_after_controller_restart(self):
        calls = []
        def operation():
            calls.append(True)
            self.write_evidence()
            raise RuntimeError('Native app UI run failed (232): original failure')
        with patch.object(recovery.os, 'cpu_count', return_value=3), \
                patch('build_manager.apple_simulators.AppleSimulators') as client, \
                patch.object(recovery, 'process_absent', return_value=True), patch('builtins.print'):
            client.return_value.matching.return_value = dict(udid=self.device, state='Booted')
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                recovery.run(operation, self.device, tools=self.tools,
                    logs=self.logs, source_path=self.source_path)
            with self.assertRaisesRegex(RuntimeError, 'already admitted'):
                recovery.run(operation, self.device, tools=self.tools,
                    logs=self.logs, source_path=self.source_path)
        self.assertEqual(len(calls), 2)  # a restarted controller admits no third execution

    def test_personal_simulator_never_retries(self):
        calls = []
        def operation():
            calls.append(True)
            self.write_evidence()
            (self.logs / 'ios-native-ui-owned.json').write_text(json.dumps(dict(
                device=self.device, name='My personal iPad')))
            raise RuntimeError('Native app UI run failed (232): original failure')
        with patch.object(recovery.os, 'cpu_count', return_value=3):
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                recovery.run(operation, self.device, tools=self.tools,
                    logs=self.logs, source_path=self.source_path)
        self.assertEqual(len(calls), 1)

    def test_live_or_unknown_first_process_is_not_replayed(self):
        calls = []
        def operation():
            calls.append(True)
            self.write_evidence()
            raise RuntimeError('Native app UI run failed (232): original failure')
        with patch.object(recovery.os, 'cpu_count', return_value=3), \
                patch('build_manager.apple_simulators.AppleSimulators') as client, \
                patch.object(recovery, 'process_absent', return_value=False):
            client.return_value.matching.return_value = dict(udid=self.device, state='Booted')
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                recovery.run(operation, self.device, tools=self.tools,
                    logs=self.logs, source_path=self.source_path)
        self.assertEqual(len(calls), 1)

    def test_only_proven_process_absence_permits_replay(self):
        for code, stdout, stderr, absent in [(1, '', '', True), (0, 'Logistics Mobile', '', False),
                                            (1, '', 'permission denied', False), (2, '', '', False)]:
            with self.subTest(code=code, stderr=stderr), patch.object(recovery.subprocess, 'run',
                    return_value=SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)):
                self.assertEqual(recovery.process_absent(900), absent)

    def test_missing_recovery_evidence_does_not_change_ordinary_run_outcomes(self):
        missing = self.root / 'not-prepared.json'
        operation = Mock(return_value={'success': True})
        self.assertEqual(recovery.run(operation, self.device, tools=self.tools,
            logs=self.logs, source_path=missing), {'success': True})
        operation.assert_called_once_with()
        error = RuntimeError('Native app UI run failed (232): original failure')
        operation = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as raised:
            recovery.run(operation, self.device, tools=self.tools,
                logs=self.logs, source_path=missing)
        self.assertIs(raised.exception, error)
        operation.assert_called_once_with()

    def test_changed_prepared_source_never_retries(self):
        calls = []
        def operation():
            calls.append(True)
            self.write_evidence()
            self.source_path.write_text(json.dumps(dict(self.source, dirty=True)))
            raise RuntimeError('Native app UI run failed (232): original failure')
        with self.assertRaisesRegex(RuntimeError, 'original failure'):
            recovery.run(operation, self.device, tools=self.tools,
                logs=self.logs, source_path=self.source_path)
        self.assertEqual(len(calls), 1)

    def test_only_hosted_ios_prebuilt_acceptance_uses_startup_recovery(self):
        from mobile_build.validation import ui_tools
        with patch.object(ui_tools, '_run_once') as single, patch.object(recovery, 'run') as recover:
            with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
                ui_tools.run('ios', self.device, no_update=True)
                recover.assert_called_once()
                single.assert_not_called()
                recover.reset_mock()
                ui_tools.run('ios', self.device, local=True, no_update=True)
                ui_tools.run('ios', self.device, no_update=False)
                ui_tools.run('android', self.device, no_update=True)
                self.assertEqual(single.call_count, 3)
                recover.assert_not_called()
            with patch.dict('os.environ', {'GITHUB_ACTIONS': 'false'}):
                ui_tools.run('ios', self.device, no_update=True)
                self.assertEqual(single.call_count, 4)
                recover.assert_not_called()


class NativeWebCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_stall_signal_survives_briefcase_line_limit_without_accepting_a_stall(self):
        import json
        from mobile_build.native_tests.tests.logisticsmobile import web_checks
        view = SimpleNamespace(url='app-document://test/', evaluate_javascript=AsyncMock())
        state = dict(platform_backend='toga_iOS.widgets.webview', ancestors=['large state'] * 1000)
        with patch.object(web_checks, 'native_state', return_value=state), \
                patch.object(web_checks.asyncio, 'wait', new=AsyncMock(return_value=(set(), set()))), \
                patch.object(web_checks.sys, 'platform', 'ios'), \
                patch.object(web_checks.asyncio, 'sleep', new=AsyncMock()) as pause, \
                patch('builtins.print') as output:
            with self.assertRaisesRegex(RuntimeError, 'did not render'):
                await wait_for_text(view, '\U0001f600' * 1000)
            pause.assert_awaited_once_with(60)
        signal = next(call.args[0] for call in output.call_args_list
                      if call.args[0].startswith('LOGISTICS_NATIVE_WEBVIEW_STALL='))
        self.assertLess(len(signal.encode()), 1000)
        value = json.loads(signal.split('=', 1)[1])
        self.assertGreater(value['pid'], 1)
        self.assertEqual(value['expected'], '\U0001f600' * 40)

    def test_native_load_events_are_bounded_and_capture_preapproved_navigation(self):
        view = SimpleNamespace(_impl=SimpleNamespace(_allowed_url='https://logistics.invalid/test/'))
        native = SimpleNamespace(interface=view, URL='https://logistics.invalid/test/',
            isLoading=lambda: True, estimatedProgress=.1)
        with patch('builtins.print'):
            for _ in range(40):
                native_event(native, 'start')
            native_event(native, 'provisional-error', 'synthetic load failure')
        self.assertEqual(len(view._native_load_trace), 32)
        event = view._native_load_trace[-1]
        self.assertEqual(event['allowed_url'], view._impl._allowed_url)
        self.assertEqual(event['error'], 'synthetic load failure')
        self.assertEqual(event['phase'], 'provisional-error')
        self.assertTrue(event['loading'])
        self.assertEqual(event['progress'], .1)

    async def test_transient_webkit_error_and_stale_content_do_not_count_as_cleared(self):
        view = SimpleNamespace(url='https://logistics.invalid/closed/', evaluate_javascript=AsyncMock(side_effect=[
            RuntimeError('WKErrorDomain Code=5 unsupported type'), 'Nested Markdown note', 'Document closed.']))
        await wait_for_text(view, 'Document closed.', absent='Nested Markdown note', timeout=2)
        self.assertEqual(view.evaluate_javascript.await_count, 3)

    async def test_persistent_webkit_failure_times_out_and_other_errors_propagate(self):
        view = SimpleNamespace(url='https://logistics.invalid/closed/', evaluate_javascript=AsyncMock(
            side_effect=RuntimeError('WKErrorDomain Code=5 unsupported type')))
        with self.assertRaisesRegex(RuntimeError, 'did not render'):
            await wait_for_text(view, 'Document closed.', timeout=.02)
        view.evaluate_javascript.side_effect = RuntimeError('WKErrorDomain Code=2 process terminated')
        with self.assertRaisesRegex(RuntimeError, 'Code=2'):
            await wait_for_text(view, 'Document closed.', timeout=1)

    async def test_nontext_results_and_retained_private_text_cannot_pass(self):
        view = SimpleNamespace(url='https://logistics.invalid/closed/', evaluate_javascript=AsyncMock(return_value=None))
        with self.assertRaisesRegex(RuntimeError, 'did not return a string'):
            await wait_for_text(view, '', absent='Nested Markdown note', timeout=1)
        view.evaluate_javascript.return_value = 'Document closed. Nested Markdown note'
        with self.assertRaisesRegex(RuntimeError, 'did not render'):
            await wait_for_text(view, 'Document closed.', absent='Nested Markdown note', timeout=.02)


class WebViewLifecycleCounterTests(unittest.TestCase):
    def test_counts_creations_and_retired_views_without_retaining_them(self):
        import gc
        from mobile_build.native_tests.tests.logisticsmobile.navigation_trace import WebViewLifecycle
        class View:
            private_closed = False
        counts = WebViewLifecycle()
        view = View()
        self.assertEqual(counts.create(view), 1)
        view.private_closed = True
        self.assertEqual(counts.snapshot()['live_retired_views'], 1)
        del view
        gc.collect()
        self.assertEqual(counts.snapshot()['views_created'], 1)
        self.assertEqual(counts.snapshot()['live_python_views'], 0)

    def test_counts_continue_past_sixty_five_in_one_lifetime(self):
        from mobile_build.native_tests.tests.logisticsmobile.navigation_trace import WebViewLifecycle
        class View:
            pass
        with TemporaryDirectory() as directory:
            counts = WebViewLifecycle(directory)
            retained = [View() for _ in range(130)]
            for number, view in enumerate(retained, 1):
                self.assertEqual(counts.create(view), number)
            saved = json.loads((Path(directory) / 'logistics-native-ui-webview-counts.json').read_text())
            self.assertEqual(saved['views_created'], 130)
            self.assertEqual(saved['live_python_views'], 130)


class TransferSurfaceAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def surface(self):
        state = SimpleNamespace
        implementation = type('NativeFixture', (), {'__module__': 'toga_iOS.widgets.box'})
        def widget(native, **values):
            impl = implementation()
            impl.native = native
            return state(_impl=impl, **values)
        def label(text):
            return widget(state(text=text), text=text)
        surface = state(closed=False, ready=True, pending=None, revision=3,
            delivered_revision=3, recovery_count=2, web=None,
            model=dict(mode='progress', workspace='Current transfer', source='Local/current',
                destination='Remote:', phase='transfer', status='Copying files…',
                files=2, total_files=4, done=500000, total=1000000, percentage=50,
                checks=1, listed=4, busy=True))
        native = state(window=object(), bounds=state(size=state(width=320, height=480)),
            isHidden=lambda: False, alpha=1, superview=None)
        fallback = widget(native, parent=surface, surface=surface,
            title=label('Current transfer'), paths=label('Source: Local/current\nDestination: Remote:'),
            status=label('Transfer\nCopying files…'),
            metrics=label('50%\nFiles: 2 / 4\nData: 0.50 / 1.00 MB\nChecked: 1 · Listed: 4'),
            buttons=state(children=[state(text='Stop transfer', enabled=True),
                state(text='Continue browsing', enabled=True)]))
        surface.native_fallback = fallback
        return surface

    def test_native_fallback_requires_real_attachment_and_current_native_label_values(self):
        surface = self.surface()
        proof = verify_native_transfer_fallback(surface)
        self.assertEqual(proof, dict(renderer='native', mode='progress', revision=3, recoveries=2))
        surface.native_fallback.paths._impl.native.text = 'Source: stale\nDestination: old'
        with self.assertRaisesRegex(AssertionError, 'endpoints are stale'):
            verify_native_transfer_fallback(surface)
        # A matching cached Python property cannot conceal a stale native label.
        self.assertEqual(surface.native_fallback.paths.text, 'Source: Local/current\nDestination: Remote:')

    def test_detached_hidden_unlaid_out_or_unacknowledged_fallback_cannot_pass(self):
        mutations = [lambda s: setattr(s.native_fallback._impl.native, 'window', None),
            lambda s: setattr(s.native_fallback._impl.native, 'superview', SimpleNamespace(
                isHidden=lambda: True, alpha=1, superview=None)),
            lambda s: setattr(s.native_fallback._impl.native.bounds.size, 'height', 0),
            lambda s: setattr(s, 'pending', s.model),
            lambda s: setattr(s, 'delivered_revision', 2),
            lambda s: setattr(s.native_fallback.buttons.children[0], 'enabled', False)]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                surface = self.surface()
                mutate(surface)
                with self.assertRaises(AssertionError):
                    verify_native_transfer_fallback(surface)

    def test_android_native_attachment_and_text_values_are_required(self):
        for representation in ('python-string', 'java-charsequence'):
            with self.subTest(representation=representation):
                surface = self.surface()
                fallback = surface.native_fallback
                implementation = type('AndroidFixture', (), {'__module__': 'toga_android.widgets.box'})
                impl = implementation()
                impl.native = SimpleNamespace(isAttachedToWindow=lambda: True, getVisibility=lambda: 0,
                    isShown=lambda: True, getWidth=lambda: 320, getHeight=lambda: 480)
                fallback._impl = impl
                def text_result(value):
                    return (value if representation == 'python-string'
                            else SimpleNamespace(toString=lambda: value))
                for widget in (fallback.title, fallback.paths, fallback.status, fallback.metrics):
                    value = widget.text
                    widget._impl.native = SimpleNamespace(getText=lambda value=value: text_result(value))
                # Read actual native text, including characters that must never
                # be stripped or normalized, rather than cached widget.text.
                surface.model['workspace'] = 'Current Δ\u200btransfer '
                fallback.title._impl.native.getText = lambda: text_result(surface.model['workspace'])
                self.assertEqual(verify_native_transfer_fallback(surface)['renderer'], 'native')
                fallback.paths._impl.native.getText = lambda: text_result('Source: stale\nDestination: old')
                with self.assertRaisesRegex(AssertionError, 'endpoints are stale'):
                    verify_native_transfer_fallback(surface)
                self.assertEqual(fallback.paths.text, 'Source: Local/current\nDestination: Remote:')
                impl.native.isAttachedToWindow = lambda: False
                with self.assertRaisesRegex(AssertionError, 'detached'):
                    verify_native_transfer_fallback(surface)

    def test_native_review_requires_current_rows_and_paging_controls(self):
        surface = self.surface()
        fallback = surface.native_fallback
        surface.model.update(mode='review', operation='Push', notice='Ready', can_confirm=True,
            counts=dict(add=1, delete=1), rows=(('delete', 'current/file'),), page=0, page_size=30, total=31)
        fallback.status._impl.native.text = 'Ready'
        fallback.metrics._impl.native.text = 'Add: 1 · Replace: 0 · Delete: 1 · Cleanup: 0\nno undo\nPage 1 · 31 matching changes'
        row_impl = type(fallback.title._impl)()
        row_impl.native = SimpleNamespace(text='Delete: current/file')
        fallback.rows = SimpleNamespace(children=[SimpleNamespace(_impl=row_impl)])
        fallback.buttons.children = [SimpleNamespace(text='Previous changes', enabled=False),
            SimpleNamespace(text='Next changes', enabled=True), SimpleNamespace(text='Approve Push', enabled=True),
            SimpleNamespace(text='Cancel review', enabled=True)]
        self.assertEqual(verify_native_transfer_fallback(surface)['mode'], 'review')
        row_impl.native.text = 'Delete: stale/file'
        with self.assertRaisesRegex(AssertionError, 'rows are stale'):
            verify_native_transfer_fallback(surface)

    def test_ios_empty_notice_sentinel_is_decoded_without_accepting_stale_visible_notice(self):
        surface = self.surface()
        fallback = surface.native_fallback
        surface.model.update(mode='review', operation='Push', notice='', can_confirm=True,
            counts={}, rows=(), page=0, page_size=30, total=0)
        fallback.metrics._impl.native.text = 'Add: 0 · Replace: 0 · Delete: 0 · Cleanup: 0\nno undo\nPage 1 · 0 matching changes'
        fallback.rows = SimpleNamespace(children=[])
        fallback.buttons.children = [SimpleNamespace(text='Previous changes', enabled=False),
            SimpleNamespace(text='Next changes', enabled=False), SimpleNamespace(text='Approve Push', enabled=True),
            SimpleNamespace(text='Cancel review', enabled=True)]
        fallback.status._impl.native.text = '\u200b'
        self.assertEqual(verify_native_transfer_fallback(surface)['mode'], 'review')
        fallback.status._impl.native.text = 'Old visible notice'
        with self.assertRaisesRegex(AssertionError, 'notice is stale'):
            verify_native_transfer_fallback(surface)
        surface.model['notice'] = 'Files changed'
        fallback.status._impl.native.text = '\u200b'
        with self.assertRaisesRegex(AssertionError, 'notice is stale'):
            verify_native_transfer_fallback(surface)
        # Ordinary whitespace and zero-width characters inside nonempty text
        # are not normalized, so stale content cannot hide behind stripping.
        for expected, actual in ((' ', ' '), ('A\u200bB', 'A\u200bB')):
            surface.model['notice'] = expected
            fallback.status._impl.native.text = actual
            self.assertEqual(verify_native_transfer_fallback(surface)['mode'], 'review')
        fallback.status._impl.native.text = 'AB'
        with self.assertRaisesRegex(AssertionError, 'notice is stale'):
            verify_native_transfer_fallback(surface)

    async def test_transfer_check_follows_current_webview_and_ignores_retired_result(self):
        surface = self.surface()
        surface.native_fallback = None
        surface.recovery_count = 1
        replacement = SimpleNamespace(evaluate_javascript=AsyncMock(return_value='Transfer details replacement'))
        async def old_page(script):
            surface.web = replacement
            return 'Transfer details retired page'
        retired = surface.web = SimpleNamespace(evaluate_javascript=AsyncMock(side_effect=old_page))
        result = await wait_for_transfer_surface(surface, timeout=1)
        self.assertEqual(result['renderer'], 'web')
        retired.evaluate_javascript.assert_awaited_once()
        replacement.evaluate_javascript.assert_awaited_once()

    async def test_native_recovery_retains_stall_signal_and_requires_visible_proof(self):
        from mobile_build.native_tests.tests.logisticsmobile import web_checks
        surface = self.surface()
        fallback, surface.native_fallback = surface.native_fallback, None
        surface.ready = False
        def recovered():
            surface.native_fallback, surface.ready = fallback, True
        asyncio.get_running_loop().call_later(.01, recovered)
        with patch.object(web_checks, 'TRANSFER_DIAGNOSTIC_DELAY', 0), patch.object(
                web_checks.sys, 'platform', 'ios'), patch('builtins.print') as output:
            result = await wait_for_transfer_surface(surface, timeout=1)
        self.assertEqual(result['renderer'], 'native')
        lines = [call.args[0] for call in output.call_args_list]
        self.assertTrue(lines[0].startswith('LOGISTICS_NATIVE_WEBVIEW_STALL='))
        self.assertTrue(lines[-1].startswith('LOGISTICS_NATIVE_TRANSFER_SURFACE='))

    async def test_wrong_native_model_does_not_pass_after_recovery(self):
        surface = self.surface()
        surface.native_fallback.metrics._impl.native.text = 'Files: 99'
        with self.assertRaisesRegex(RuntimeError, 'bounded recovery'):
            await wait_for_transfer_surface(surface, timeout=.01)
