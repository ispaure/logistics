"""Phone drawers and Duo panes retain the actual document/chat owners."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile


class WorkspaceNavigationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents()
        self.navigation = self.app.adaptive

    def tearDown(self):
        for drawer in self.navigation.browsers.values():
            if drawer.task is not None and not drawer.task.done():
                drawer.task.cancel()
            self.app.loop.run_until_complete(drawer.browser.close())
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_phone_file_drawer_opens_a_nested_file_without_losing_editor_draft(self):
        app = self.app
        app.editor.value = 'Keep the original draft'
        first = app.editor_view
        with patch.object(self.navigation, 'width', return_value=390):
            first.document_view._workspace_frame.menu.on_press()
            drawer = self.navigation.browser('documents')
            (app.private_root / 'LocalFiles' / 'Notes').mkdir(parents=True, exist_ok=True)
            (app.private_root / 'LocalFiles' / 'Notes' / 'Another.md').write_text('# Other file')
            app.loop.run_until_complete(drawer.task)
            frame = first.document_view._workspace_frame
            self.assertEqual(list(frame.row.children), [drawer.widget])
            app.loop.run_until_complete(drawer.open_folder({'path': 'Notes'}))
            entry = next(item for item in drawer.browser.entries if item.label == 'Another.md')
            app.loop.run_until_complete(drawer.browser._select_pressed(entry, drawer.browser.buttons[entry.identity]))
            self.assertEqual(app.native_host.state.destination, 'documents')
            self.assertFalse(self.navigation.menu_open['documents'])
            self.assertEqual(first.document.text, 'Keep the original draft')
            self.assertEqual(app.private_sessions.active.crypt_text.value, '# Other file')
            self.assertTrue(app.routes.back())
            self.assertIs(app.body.children[0], first.document_view)

    def test_duo_switches_browser_and_two_editors_and_collapses_without_copying_widgets(self):
        app = self.app
        first = app.editor_view
        first.editor.value = 'A draft'
        app.new_document()
        second = app.editor_view
        second.editor.value = 'B draft'
        self.navigation.pinned = first.session.id
        with patch.object(self.navigation, 'width', return_value=1100):
            self.navigation.render()
            frame = second.document_view._workspace_frame
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')
            frame.menu.on_press()
            drawer = self.navigation.browser('documents')
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
            first.editor.value = 'Edited on left'
            self.assertEqual(second.document.text, 'B draft')
            self.assertEqual(app.store.open(first.document.id).text, 'Edited on left')
        with patch.object(self.navigation, 'width', return_value=390):
            self.navigation.render()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertEqual(first.document.text, 'Edited on left')
        app.close_session(first.session.id)
        self.assertIsNone(self.navigation.pinned)
        self.assertEqual(second.document.text, 'B draft')

    def test_files_drawer_retains_current_folder_and_native_back_route(self):
        app = self.app
        app.show_cloud(present=False)
        with patch.object(self.navigation, 'width', return_value=390):
            app.loop.run_until_complete(app.show_files())
            frame = app.files_view._workspace_frame
            original = app.file_browser
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [self.navigation.browser('files').widget])
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertIs(app.file_browser, original)
            self.assertTrue(app.routes.back())
            self.assertEqual(app.native_host.state.destination, 'files')

    def test_overview_hamburger_keeps_current_editor_beside_wide_browser(self):
        app = self.app
        owner = app.editor_view
        owner.editor.value = 'Draft before opening the overview'
        app.show_documents_hub()
        with patch.object(self.navigation, 'width', return_value=1100):
            menu = app.body.children[0].content.children[0]
            menu.on_press()
            self.assertIs(app.body.children[0], owner.document_view)
            self.assertEqual(list(owner.document_view._workspace_frame.row.children),
                             [self.navigation.browser('documents').widget, owner.document_view._workspace_frame.main])
            self.assertEqual(owner.editor.value, 'Draft before opening the overview')

    def test_chat_conversation_drawer_is_full_height_on_phone_and_half_on_duo(self):
        app = self.app
        with patch.object(self.navigation, 'width', return_value=390):
            app.show_chat()
            first = app.chat_current['id']
            app.chat_prompt.value = 'Unsent first conversation'
            app.new_chat()
            second = app.chat_current['id']
            app.chat_prompt.value = 'Unsent second conversation'
            app.toggle_chat_conversations()
            self.assertEqual(list(app.chat_workspace.children), [app.chat_sidebar])
            app.open_chat(first)
            self.assertEqual(app.chat_prompt.value, 'Unsent first conversation')
            self.assertEqual(list(app.chat_workspace.children), [app.chat_messages])
            self.assertEqual(app.chat_store.load(second)['draft'], 'Unsent second conversation')
        with patch.object(self.navigation, 'width', return_value=1100):
            app.toggle_chat_conversations()
            self.assertEqual(list(app.chat_workspace.children), [app.chat_sidebar, app.chat_messages])
            app.show_chat_configuration()
            self.assertIs(app.body.children[0], app.chat_config_view)
            self.assertTrue(app.routes.back())
            self.assertIs(app.body.children[0], app.chat_view)
        app.show_settings()
        self.assertEqual(app.native_host.state.destination, 'settings')
        self.assertIs(app.body, app.routes.roots['settings'])
