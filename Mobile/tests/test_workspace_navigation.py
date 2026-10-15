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

    def test_documents_menu_recent_reopens_closed_file_and_browse_uses_main_area(self):
        app = self.app
        app.name.value = 'Recent.md'
        app.editor.value = '# Keep this draft'
        key = app.editor_view.session.id
        resource = app.current.id
        app.save_workspace()
        app.close_session(key, choice='keep')
        drawer = self.navigation.browser('documents')
        drawer.refresh_menu()
        recent = next(button for button in drawer.recent_buttons if button.text == 'Recent.md')
        app.loop.run_until_complete(recent.on_press())
        self.assertEqual(app.current.id, resource)
        self.assertEqual(app.editor.value, '# Keep this draft')
        local = app.private_root / 'LocalFiles'
        local.mkdir(exist_ok=True)
        (local / 'note.md').write_text('# Note')
        (local / 'other.txt').write_text('Other')
        app.loop.run_until_complete(app.open_document_category('Markdown Editor'))
        self.assertEqual(app.routes.screens['documents'][-1][0], 'workspace-browser')
        self.assertEqual([row.label for row in drawer.browser.entries], ['note.md'])
        self.assertFalse(self.navigation.menu_open['documents'])
        self.assertIs(drawer.browser_widget.parent, app.body.children[0])
        self.assertEqual(app.editor.value, '# Keep this draft')

    def test_folder_actions_pair_tree_at_center_and_collapse_on_phone(self):
        app = self.app
        app.show_locations()
        with patch.object(self.navigation, 'width', return_value=669):
            app.choose_folder('All files')
            frame = app.body.children[0]._workspace_frame
            self.assertEqual(list(frame.row.children), [frame.folder_master, frame.main])
            self.assertLessEqual(abs(frame.folder_master.style.width - frame.main.style.width), 1)
            self.assertFalse(any(button.text == 'Remove mapping (keep files)'
                                 for button, _ in app.folder_action_controls))
            with patch.object(self.navigation, 'width', return_value=390):
                self.navigation.render()
                self.assertEqual(list(frame.row.children), [frame.main])
            self.navigation.render()
            self.assertEqual(list(frame.row.children), [frame.folder_master, frame.main])

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
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
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
        # The wider Duo portrait display is narrower than a regular iPad.
        with patch.object(self.navigation, 'width', return_value=669):
            self.navigation.render()
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')
            self.assertEqual(list(frame.row.children), [first.document_view._workspace_frame.main, frame.main])
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
            self.assertEqual(list(frame.row.children), [self.navigation.browser('files').widget, frame.main])
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertIs(app.file_browser, original)
            self.assertTrue(app.routes.back())
            self.assertEqual(app.native_host.state.destination, 'files')

    def test_overview_drawer_keeps_overview_and_editor_draft(self):
        app = self.app
        owner = app.editor_view
        owner.editor.value = 'Draft before opening the overview'
        app.show_documents_hub()
        overview = app.body.children[0]
        frame = overview._workspace_frame
        with patch.object(self.navigation, 'width', return_value=390):
            frame.menu.on_press()
            self.assertIs(app.body.children[0], overview)
            self.assertEqual(list(frame.row.children),
                             [self.navigation.browser('documents').widget, frame.main])
            self.assertLess(self.navigation.browser('documents').widget.style.width, 390)
            self.assertTrue(frame.compact_open)
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])
            self.assertEqual(owner.editor.value, 'Draft before opening the overview')

    def test_files_hamburger_works_on_first_tab_selection_without_refresh(self):
        app = self.app
        app.show_home()
        with patch.object(self.navigation, 'width', return_value=390):
            # Match native selection ordering: the callback precedes state.select.
            self.assertTrue(app.select_destination('files'))
            app.native_host.state.select('files')
            frame = app.routes.body('files').children[0]._workspace_frame
            self.assertEqual(self.navigation.last_layout[0], id(frame))
            frame.menu.on_press()
            drawer = self.navigation.browser('files')
            app.loop.run_until_complete(drawer.task)
            self.assertTrue(self.navigation.menu_open['files'])
            self.assertIsNotNone(drawer.provider)
            self.assertEqual(list(frame.row.children), [drawer.widget, frame.main])
            self.assertEqual(len(app.routes.screens['files']), 0)
            frame.menu.on_press()
            self.assertEqual(list(frame.row.children), [frame.main])

    def test_split_picker_can_open_a_retained_session_without_an_existing_editor(self):
        app = self.app
        first = app.editor_view
        stored = app.store.create('Retained second.txt')
        second = app.workspace.open('managed-text', stored.id, 'text', stored.name)
        app.workspace.activate(first.session.id)
        self.assertNotIn(second.id, app.text_views)
        with patch.object(self.navigation, 'width', return_value=669):
            first.document_view._workspace_frame.pair.on_press()
            content = app.body.children[0].content
            next(button for button in content.children if getattr(button, 'text', '') == stored.name).on_press()
            self.assertEqual(app.workspace.active, second.id)
            self.assertEqual(self.navigation.pinned, first.session.id)
            self.assertIn(second.id, app.text_views)
            self.assertEqual(self.navigation.diagnostics()['layout'], 'two-documents')

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
