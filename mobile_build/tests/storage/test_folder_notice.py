"""Incoming status messages fit the allocated Workspaces pane as it changes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from mobile.folder_hub_ui import fit_folder_credential, reflow_folder_notice
from commonUtils.ui.native.forms import FittedLabel
from toga.style import Pack


class FolderNoticeTests(unittest.TestCase):
    def test_compact_notice_refits_changed_messages_and_rotation(self):
        notice = FittedLabel('Some incoming files could not be saved; reopen the app to retry.', style=Pack(font_size=12))
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

    def test_narrow_header_keeps_credential_picker_within_its_row(self):
        import toga
        from toga.style.pack import ROW
        from travertino.size import at_least

        caption = toga.Label('Credential', style=Pack(margin_right=6))
        caption.intrinsic.width = at_least(61)
        picker = toga.Selection(items=['All', 'Long credential name'], value='Long credential name')
        picker.intrinsic.width = at_least(300)
        row = toga.Box(children=[caption, picker], style=Pack(direction=ROW, flex=1))
        toggle = toga.Button('View', style=Pack(width=48, margin_left=6))
        header = toga.Box(children=[row, toggle], style=Pack(direction=ROW))
        app = NS(folder_credential=picker, folder_credential_label=caption,
                 folder_credential_row=row, folder_view_toggle=toggle)

        fit_folder_credential(app, 122)
        self.assertIsNone(caption.parent)
        self.assertEqual(picker.style.width, 68)
        self.assertEqual(picker.value, 'Long credential name')
        header.style.layout(NS(width=122, height=48))
        self.assertEqual(row.layout.content_left + picker.layout.content_width, 68)
        self.assertEqual(toggle.layout.content_left + toggle.layout.content_width, 122)

        fit_folder_credential(app, 320)
        self.assertEqual(list(row.children), [caption, picker])
        self.assertEqual(picker.style.width, 199)
