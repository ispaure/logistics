"""Native bootstrap navigation must not bypass the offline reader boundary."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace
from contextlib import redirect_stderr
from io import StringIO
import unittest
from unittest.mock import Mock

import toga
from features.books.mobile.presentation import ChapterBridge, _bind_chapter_navigation


class EpubLoadPolicyTests(unittest.TestCase):
    def test_ios_native_decision_does_not_reload_bootstrap_through_http_setter(self):
        view = toga.WebView()
        bridge = ChapterBridge(view, root='https://logistics.invalid/current/')
        _bind_chapter_navigation(view, bridge.navigation, 'toga_iOS.widgets.webview')
        with redirect_stderr(StringIO()) as output:
            self.assertTrue(view.on_navigation_starting(url='about:blank'))
            self.assertFalse(view.on_navigation_starting(url='https://example.com/'))
            bridge.ready = True
            self.assertFalse(view.on_navigation_starting(url='about:blank'))
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(view.on_navigation_starting._raw, bridge.navigation)

    def test_native_blank_bootstrap_is_allowed_only_before_document_load(self):
        view = SimpleNamespace(evaluate_javascript=Mock())
        bridge = ChapterBridge(view, root='https://logistics.invalid/current/')
        self.assertTrue(bridge.navigation(view, 'about:blank'))
        bridge.loaded(view)
        self.assertFalse(bridge.navigation(view, 'about:blank'))
        bridge.dispose()
        self.assertFalse(bridge.navigation(view, 'about:blank'))

    def test_bootstrap_keeps_external_stale_and_event_navigation_blocked(self):
        view = SimpleNamespace(evaluate_javascript=Mock())
        event = Mock()
        bridge = ChapterBridge(view, root='https://logistics.invalid/current/', on_event=event)
        for url in ('https://example.com/', 'file:///etc/passwd',
                    'about:blank#other', 'about:srcdoc', 'javascript:alert(1)',
                    'https://logistics.invalid/previous/next?offset=0&end=1'):
            self.assertFalse(bridge.navigation(view, url))
        event.assert_not_called()
        self.assertFalse(bridge.navigation(
            view, bridge.root + 'next?offset=3&end=1'))
        event.assert_called_once_with('next', 3)
