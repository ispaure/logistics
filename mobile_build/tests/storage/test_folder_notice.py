"""Incoming status messages fit the allocated Workspaces pane as it changes."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from mobile.folder_hub_ui import reflow_folder_notice
from commonUtils.ui.native.forms import FittedLabel
from toga.style import Pack


class FolderNoticeTests(unittest.TestCase):
    def test_compact_notice_refits_changed_messages_and_rotation(self):
        notice = FittedLabel('Files shared from other apps appear in Received Files.', style=Pack(font_size=12))
        app = NS(incoming_notice=notice, adaptive=NS(content_width=Mock(return_value=280)))
        reflow_folder_notice(app)
        self.assertIn('\n', notice.text)
        app.adaptive.content_width.assert_called_once_with('files', margin=32)
        notice.text = 'Incoming files are waiting. Check available storage and reopen the app.'
        self.assertIn('\n', notice.text)
        source = notice._settings_source_text
        app.adaptive.content_width.return_value = 800
        reflow_folder_notice(app)
        self.assertEqual(notice.text, source)

    def test_sidebar_uses_its_allocation_and_safe_insets(self):
        native = NS(bounds=NS(size=NS(width=330)), safeAreaInsets=NS(left=8, right=6))
        notice = object()
        app = NS(incoming_notice=notice, adaptive=NS(file_columns=NS(sidebar=NS(native=native))))
        with patch('mobile.folder_hub_ui.fit_text') as fit:
            reflow_folder_notice(app)
        fit.assert_called_once_with(notice, 292)

    def test_native_layout_can_supply_sidebar_width_before_children_reflow(self):
        notice = object()
        with patch('mobile.folder_hub_ui.fit_text') as fit:
            reflow_folder_notice(NS(incoming_notice=notice), 240)
        fit.assert_called_once_with(notice, 240)
