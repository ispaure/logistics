"""Document destination visibility stays independent of fullscreen and keyboards."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import Mock, patch

import toga

from mobile.reader_chrome import sync_document_tabs


class DocumentChromeTests(TestCase):
    def setUp(self):
        self.bar = Mock()
        self.bar.getVisibility.return_value = 0
        self.adapter = NS(bottom=self.bar, keyboard_chrome=None,
                          impl=NS(native_navigationview=self.bar))
        self.app = NS(native_host=NS(adapter=self.adapter, state=NS(destination='files')),
                      routes=NS(screens={'files': []}), adaptive=NS(detail_routes=[]))
        self.view = toga.Box()

    def test_document_and_secondary_routes_hide_destinations_until_back_to_browser(self):
        for route in ('editor', 'reader:book', 'private:pdf', 'file-loading:remote', 'notes-library:vault'):
            with self.subTest(route=route):
                self.app.routes.screens['files'] = [(route, None, None), ('appearance', None, None)]
                sync_document_tabs(self.app, self.view)
                self.bar.setVisibility.assert_called_with(8)
                self.assertTrue(self.app._document_tabs_hidden)
        self.app.routes.screens['files'] = [('browser', None, None)]
        self.bar.getVisibility.return_value = 8
        sync_document_tabs(self.app, self.view)
        self.bar.setVisibility.assert_called_with(0)
        self.assertFalse(self.app._document_tabs_hidden)

    def test_fullscreen_exit_keeps_document_tabs_hidden_and_does_not_hide_top_bar(self):
        self.view._reader_session_id = 'text'
        for immersive in (True, False):
            sync_document_tabs(self.app, self.view, fullscreen=immersive)
            self.bar.setVisibility.assert_called_with(8)
        self.assertFalse(hasattr(self.adapter, '_reader_action_bar_active'))

    def test_android_keyboard_restores_current_route_visibility(self):
        title = Mock()
        self.adapter.keyboard_chrome = (self.bar, 0, title, True)
        self.view._reader_session_id = 'text'
        sync_document_tabs(self.app, self.view)
        self.assertEqual(self.adapter.keyboard_chrome, (self.bar, 8, title, True))
        del self.view._reader_session_id
        self.bar.getVisibility.return_value = 8
        sync_document_tabs(self.app, self.view)
        self.assertEqual(self.adapter.keyboard_chrome, (self.bar, 0, title, True))
        self.assertFalse(self.app._document_tabs_hidden)
        self.adapter.keyboard_chrome = None
        sync_document_tabs(self.app, self.view)
        self.bar.setVisibility.assert_called_with(0)

    def test_apple_keyboard_snapshot_tracks_document_exit_without_revealing_tabs(self):
        adapter = self.app.native_host.adapter = NS(navigation=[], controller=Mock(),
            keyboard_tab_visibility=(True, False), tabs_hidden=Mock(return_value=True),
            set_keyboard_tabs_hidden=Mock())
        adapter.controller.respondsToSelector.return_value = True
        self.view._reader_session_id = 'text'
        with patch.dict('sys.modules', {'rubicon.objc': NS(SEL=lambda name: name)}):
            sync_document_tabs(self.app, self.view)
            self.assertEqual(adapter.keyboard_tab_visibility, (True, True))
            del self.view._reader_session_id
            sync_document_tabs(self.app, self.view)
            self.assertEqual(adapter.keyboard_tab_visibility, (True, False))
            adapter.set_keyboard_tabs_hidden.assert_not_called()
            adapter.keyboard_tab_visibility = None
            sync_document_tabs(self.app, self.view)
            adapter.set_keyboard_tabs_hidden.assert_called_once_with(True, False)

    def test_paired_document_and_rail_use_same_visibility_policy(self):
        self.app.native_host.state.destination = 'documents'
        self.app.routes.screens['documents'] = []
        self.app.adaptive.detail_routes = [('editor', None, None)]
        sync_document_tabs(self.app, self.view)
        self.bar.setVisibility.assert_called_with(8)

    def test_apple_documents_list_ignores_retained_invisible_detail(self):
        self.app.native_host.state.destination = 'documents'
        self.app.routes.screens['documents'] = []
        self.app.adaptive.split = Mock()
        self.app.adaptive.in_detail = False
        self.app.adaptive.detail_routes = [('reader:book', None, None)]
        sync_document_tabs(self.app, self.view)
        self.assertFalse(self.app._document_tabs_hidden)
        # Returning to that detail must still hide destinations.
        self.app.adaptive.in_detail = True
        sync_document_tabs(self.app, self.view)
        self.assertTrue(self.app._document_tabs_hidden)
