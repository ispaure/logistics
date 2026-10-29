"""Native bootstrap navigation must not bypass the offline reader boundary."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from features.books.mobile.presentation import ChapterBridge


class EpubLoadPolicyTests(unittest.TestCase):
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
