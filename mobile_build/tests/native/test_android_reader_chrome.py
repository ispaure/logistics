"""Native toolbar ownership across document edits, routes and fullscreen."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from mobile.android_reader_chrome import sync


class Native:
    def __init__(self, *args):
        self.parent = None
        self.children = []
        self.resources = NS(getDisplayMetrics=lambda: NS(density=1),
                            getConfiguration=lambda: NS(uiMode=0))

    def getResources(self):
        return self.resources

    def getParent(self):
        return self.parent

    def addView(self, child, params):
        if child.parent is not None:
            raise AssertionError('Native view already has a parent')
        child.parent = self
        self.children.append(child)

    def removeView(self, child):
        self.children.remove(child)
        child.parent = None

    def __getattr__(self, name):
        result = Mock()
        setattr(self, name, result)
        return result


def widget():
    return NS(_impl=NS(native=Native()), parent=None)


class AndroidReaderChromeTests(unittest.TestCase):
    def test_startup_before_native_adapter_is_installed(self):
        self.app.native_host.adapter = None
        sync(self.app, self.view, 'documents')
        self.bar.setCustomView.assert_not_called()

    def setUp(self):
        self.bar = Mock()
        self.bar.getDisplayOptions.return_value = 11
        self.adapter = NS()
        self.app = NS(_impl=NS(native=NS(getSupportActionBar=lambda: self.bar,
            getResources=lambda: Native().resources)),
            native_host=NS(adapter=self.adapter, state=NS(destination='documents')),
            routes=NS(screens={'documents': [], 'files': []}), main_window=object())
        self.menu, self.action, self.save = widget(), widget(), widget()
        self.frame = NS(menu=self.menu, header=widget())
        self.buttons = [self.action]
        self.view = NS(_native_reader_buttons=lambda: self.buttons,
            _native_reader_title=lambda: 'Document.md', _native_reader_toolbar=widget(),
            _workspace_frame=self.frame)
        frame_class = Mock(side_effect=Native)
        frame_class.LayoutParams.side_effect = lambda *args: NS(setMarginStart=Mock(), setMarginEnd=Mock())
        linear_class = Mock(side_effect=Native)
        linear_class.LayoutParams.side_effect = lambda *args: NS()
        modules = {
            'android.view': NS(Gravity=NS(CENTER=1, CENTER_VERTICAL=2, START=3, END=4), View=NS(VISIBLE=0, GONE=8)),
            'android.widget': NS(FrameLayout=frame_class, LinearLayout=linear_class, TextView=Native),
            'android.text': NS(TextUtils=NS(TruncateAt=NS(MIDDLE=5))),
            'android.graphics': NS(Color=NS(parseColor=lambda value: value)),
            'java': NS(jclass=lambda name: lambda *args: NS()),
        }
        self.enterContext(patch.dict('sys.modules', modules))
        self.detach = self.enterContext(patch('mobile.workspace_navigation.detach'))

    def test_title_gutters_follow_layout_direction(self):
        from commonUtils.ui.native.bars import android_bar
        leading, trailing = [widget(), widget()], [widget()]
        # Inspect the native mounting parameters rather than emulating Android's
        # resolution of logical margins in left-to-right/right-to-left layouts.
        import sys
        frame = sys.modules['android.widget'].FrameLayout
        allocations = []
        frame.LayoutParams.side_effect = lambda *args: allocations.append(
            NS(setMarginStart=Mock(), setMarginEnd=Mock())) or allocations[-1]
        android_bar(self.app._impl.native, leading, trailing)
        allocations[0].setMarginStart.assert_called_once_with(96)
        allocations[0].setMarginEnd.assert_called_once_with(48)

    def test_notes_title_has_a_hold_target_and_all_actions_fit_or_scroll(self):
        from mobile.android_reader_chrome import fit_document_title
        from android.view import View
        from unittest.mock import MagicMock
        import sys
        java = sys.modules['java']
        widgets = sys.modules['android.widget']

        root, titles, actions, scroll = [MagicMock() for _ in range(4)]
        root.getResources.return_value = Native().resources
        root.indexOfChild.return_value = 0
        root.getChildCount.return_value = 3
        children = [titles, None, actions]
        root.getChildAt.side_effect = children.__getitem__
        root.addView.side_effect = lambda child, params: children.__setitem__(2, child)
        with patch.object(View, 'OnLayoutChangeListener', object, create=True), \
                patch.object(java, 'dynamic_proxy', lambda interface: interface, create=True), \
                patch.object(widgets, 'HorizontalScrollView', return_value=scroll, create=True):
            fit_document_title(root, NS(getParent=lambda: titles), 2, 5)
        layout = root.addOnLayoutChangeListener.call_args.args[0]
        for width, start, end in [(320, 96, 176), (390, 96, 240), (800, 96, 240)]:
            layout.onLayoutChange(root, 0, 0, width, 48, 0, 0, 0, 0)
            margins = titles.getLayoutParams.return_value
            margins.setMarginStart.assert_called_with(start)
            margins.setMarginEnd.assert_called_with(end)
            self.assertEqual(scroll.getLayoutParams.return_value.width, min(end, 240))
            self.assertGreaterEqual(width - start - end, 48)
        layout.onLayoutChange(root, 0, 0, 390, 48, 0, 0, 0, 0)
        scroll.addView.assert_called_once_with(actions, -2, -1)

    def test_dirty_clean_dirty_releases_retired_save_before_reuse(self):
        sync(self.app, self.view, 'documents')
        self.buttons = [self.save, self.action]
        sync(self.app, self.view, 'documents')
        self.assertIsNotNone(self.save._impl.native.parent)
        self.buttons = [self.action]
        sync(self.app, self.view, 'documents')
        self.assertIsNone(self.save._impl.native.parent)
        self.buttons = [self.save, self.action]
        sync(self.app, self.view, 'documents')
        self.assertIsNotNone(self.save._impl.native.parent)
        self.detach.assert_any_call(self.frame.header)
        self.detach.assert_any_call(self.view._native_reader_toolbar)

    def test_sync_never_adds_a_control_to_the_native_reader_bar(self):
        transfer = widget()
        self.view._reader_transfer_button = transfer
        for busy, percentage, fullscreen in ((True, 42, False), (True, 73, True),
                                              (True, None, False), (False, 100, False)):
            self.app.transfer_busy = self.app.transfer_notification = busy
            self.app.transfer_percentage = percentage
            self.view._reader_fullscreen = fullscreen
            sync(self.app, self.view, 'documents')
            self.assertNotIn(transfer, self.adapter._reader_action_bar_buttons)
            self.assertIsNone(transfer._impl.native.parent)

    def test_title_refresh_does_not_rebuild_buttons_and_fullscreen_hides_bar(self):
        sync(self.app, self.view, 'documents')
        self.view._native_reader_title = lambda: 'Renamed.md'
        sync(self.app, self.view, 'documents')
        self.bar.setCustomView.assert_called_once()
        self.adapter._reader_action_bar_title.setText.assert_called_with('Renamed.md')
        self.view._reader_fullscreen = True
        sync(self.app, self.view, 'documents')
        self.bar.hide.assert_called_once()
        self.view._reader_fullscreen = False
        sync(self.app, self.view, 'documents')
        self.bar.show.assert_called()

    def test_leaving_reader_releases_controls_and_clears_private_title(self):
        sync(self.app, self.view, 'documents')
        label = self.adapter._reader_action_bar_title
        sync(self.app, NS(), 'files')
        self.assertIsNone(self.action._impl.native.parent)
        self.assertIsNone(self.menu._impl.native.parent)
        self.assertFalse(self.adapter._reader_action_bar_active)
        label.setText.assert_called_with('')
        self.bar.setDisplayOptions.assert_called_with(11)
        self.bar.hide.assert_called()

    def test_back_button_is_preserved_with_drawer_and_document_actions(self):
        back = widget()
        self.app.routes.screens['documents'] = [('reader',)]
        with patch('mobile.control_icons.icon_button', return_value=back) as create:
            sync(self.app, self.view, 'documents')
        self.assertEqual(self.adapter._reader_action_bar_buttons, [back, self.menu, self.action])
        self.app.routes.back = Mock()
        create.call_args.kwargs['on_press'](back)
        self.app.routes.back.assert_called_once()

    def test_main_reader_uses_close_instead_of_back_with_drawer_and_actions(self):
        close = self.view._reader_close_button = widget()
        self.app.routes.screens['documents'] = [('reader',)]
        sync(self.app, self.view, 'documents')
        self.assertEqual(self.adapter._reader_action_bar_buttons, [close, self.menu, self.action])
        self.assertFalse(hasattr(self.adapter, '_reader_back'))

    def test_locked_window_cannot_republish_reader_title_or_controls(self):
        sync(self.app, self.view, 'documents')
        self.app.screen_privacy = NS(resume_locked=True)
        sync(self.app, self.view, 'documents')
        self.assertFalse(self.adapter._reader_action_bar_active)
        self.assertIsNone(self.action._impl.native.parent)
        self.adapter._reader_action_bar_title.setText.assert_called_with('')
        self.app.screen_privacy.resume_locked = False
        sync(self.app, self.view, 'documents')
        self.assertTrue(self.adapter._reader_action_bar_active)

    def test_header_errors_remain_visible_after_inline_status_is_detached(self):
        self.view._native_reader_status = NS(text='Save failed: source is read-only')
        sync(self.app, self.view, 'documents')
        status = self.adapter._reader_action_bar_status
        status.setText.assert_called_with('Save failed: source is read-only')
        status.setVisibility.assert_called_with(0)
        self.view._native_reader_status.text = 'Chapter 1'
        sync(self.app, self.view, 'documents')
        status.setVisibility.assert_called_with(8)

    def test_keyboard_keeps_reader_bar_hidden_until_dismissed(self):
        self.adapter.keyboard_chrome = (Mock(), 8, self.bar, False)
        sync(self.app, self.view, 'documents')
        self.bar.show.assert_not_called()
        self.bar.hide.assert_called()
        self.assertTrue(self.adapter.keyboard_chrome[3])
        self.adapter.keyboard_chrome = None
        sync(self.app, self.view, 'documents')
        self.bar.show.assert_called_once()

    def test_editing_actions_remain_reachable_while_keyboard_hides_application_bars(self):
        self.view._keyboard_actions_required = True
        self.adapter.keyboard_chrome = (Mock(), 8, self.bar, False)
        sync(self.app, self.view, 'documents')
        self.bar.show.assert_called_once()
        self.bar.hide.assert_not_called()
        self.assertTrue(self.adapter.keyboard_chrome[3])
        self.assertIsNotNone(self.action._impl.native.parent)
        sync(self.app, NS(), 'files')
        self.assertFalse(self.adapter._reader_action_bar_keep_keyboard)
        self.assertFalse(self.adapter.keyboard_chrome[3])

    def test_closing_with_keyboard_open_cannot_restore_retired_reader_bar(self):
        sync(self.app, self.view, 'documents')
        self.adapter.keyboard_chrome = (Mock(), 8, self.bar, True)
        sync(self.app, NS(), 'files')
        self.assertFalse(self.adapter.keyboard_chrome[3])
        self.assertFalse(self.adapter._reader_action_bar_active)
