"""Native WebView probes require real text after provisional navigation settles."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from mobile_build.native_tests.tests.logisticsmobile.web_checks import wait_for_text
from mobile_build.native_tests.tests.logisticsmobile.navigation_trace import native_event


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
