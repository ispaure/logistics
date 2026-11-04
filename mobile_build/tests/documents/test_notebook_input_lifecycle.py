"""Canvas remounting retires the native Pencil observer with its WebView."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from unittest.mock import Mock, patch

import test_notebook_storage as fixture


class NotebookInputLifecycleTests(unittest.TestCase):
    setUp = fixture.NotebookStorageTests.setUp
    tearDown = fixture.NotebookStorageTests.tearDown
    run_async = fixture.NotebookStorageTests.run_async
    create = fixture.NotebookStorageTests.create

    def test_remount_and_dispose_close_each_owned_hover_observer_once(self):
        first, second = Mock(), Mock()
        with patch('features.notebooks.mobile.ios_input.attach', side_effect=[first, second]) as attach:
            panel = self.create(private=False)
            original = panel.web
            self.assertIs(panel.pencil_hover, first)
            panel.mount_canvas()
            first.close.assert_called_once_with()
            self.assertIsNot(panel.web, original)
            self.assertIs(panel.pencil_hover, second)
            self.assertEqual(attach.call_count, 2)
            panel.dispose()
            panel.retire_canvas()
            second.close.assert_called_once_with()
            self.assertIsNone(panel.pencil_hover)
