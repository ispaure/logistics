"""Native WebView probes require real text after provisional navigation settles."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from Mobile.native_tests.tests.logisticsmobile.web_checks import wait_for_text


class NativeWebCheckTests(unittest.IsolatedAsyncioTestCase):
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
