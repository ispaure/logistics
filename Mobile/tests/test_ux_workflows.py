"""Task-oriented regressions for the mobile UX passes; no external services."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import toga
from logisticsmobile.app import LogisticsMobile


def widgets(root):
    yield root
    for child in root.children:
        yield from widgets(child)
    if isinstance(root, toga.ScrollContainer) and root.content is not None:
        yield from widgets(root.content)


class UXWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        LogisticsMobile.storage_root = Path(self.directory.name)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_documents()

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def test_recovery_is_not_reported_as_saved_and_conflict_has_a_resolution(self):
        app = self.app
        app.editor.value = 'Recovery is not a source save'
        self.assertEqual(app.status.text, 'Unsaved changes · recovery copy kept')
        self.assertEqual(app.current.snapshot.path.read_bytes(), b'')
        app.save_document()
        self.assertEqual(app.status.text, 'Saved on this device')
        app.current.snapshot.path.write_bytes(b'Externally changed')
        app.editor.value = 'Keep this newer draft'
        app.save_document()
        owner = app.editor_view
        self.assertIn(owner.conflict_copy, owner.conflict_actions.children)
        app.editor.value += '!'
        self.assertIn('File changed outside', app.status.text)
        owner.conflict_copy.on_press()
        self.assertEqual(app.current.text, 'Keep this newer draft!')
        self.assertNotEqual(app.editor_view, owner)
        self.assertEqual(owner.document.snapshot.path.read_bytes(), b'Externally changed')

    def test_recent_reopens_closed_file_without_duplicate_open_documents(self):
        app = self.app
        app.name.value = 'Recent.md'
        app.editor.value = '# Saved recent'
        app.save_document()
        key = app.current.id
        identity = app.editor_view.session.identity
        session_id = app.editor_view.session.id
        app.request_close_session(session_id)
        self.assertNotIn(session_id, app.workspace.sessions)
        items = app.recent_items()
        session, summary = next(item for item in items if item[0].resource == key)
        self.assertEqual(summary[0], 'Recent.md')
        app.loop.run_until_complete(app.recent_opener(session)())
        self.assertEqual(app.current.id, key)
        app.loop.run_until_complete(app.recent_opener(session)())
        self.assertEqual(sum(s.identity == identity for s in app.workspace.sessions.values()), 1)
        view = app.build_documents_hub()
        self.assertTrue(any(getattr(widget, 'text', '') == 'Recent' for widget in widgets(view)))

    def test_folder_tap_skips_actions_and_parent_navigation_stays_separate(self):
        app = self.app
        root = app.private_root / 'LocalFiles' / 'Notes'
        root.mkdir(parents=True)
        (root / 'Draft.md').write_text('# File')
        app.show_locations()
        app.folder_source_buttons['Local'].on_press()
        app.loop.run_until_complete(app.folder_buttons['Notes'].on_press())
        self.assertEqual([route[0] for route in app.routes.screens['files']], ['browser'])
        self.assertEqual(app.file_path, 'Notes')
        self.assertNotIn(app.file_browser.back_button, app.file_browser.navigation_controls.children)
        app.loop.run_until_complete(app.parent_file_folder())
        self.assertEqual(app.file_path, '')
        app.choose_folder('Notes')
        buttons = [w for w in widgets(app.body) if isinstance(w, toga.Button)]
        delete = next(w for w in buttons if w.text == 'Delete local folder…')
        self.assertEqual(delete.action_role, 'destructive')
        self.assertEqual(app.folder_browse_button.action_role, 'primary')

    def test_android_retained_roots_use_outer_allocation_and_subtract_the_rail(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        app = self.app
        impl = SimpleNamespace(native=SimpleNamespace(getWidth=Mock(return_value=1080)),
            native_navigationview=SimpleNamespace(getWidth=Mock(return_value=144), getVisibility=Mock(return_value=0)),
            scale_out=lambda value: value // 2)
        adapter = SimpleNamespace(impl=impl, mode='bottom')
        app.native_host.adapter = adapter
        try:
            with patch.object(type(app._impl), '__module__', 'toga_android.app'):
                app.adaptive.render()
                self.assertEqual(app.routes.body().style.width, 540)
                # Repeated layouts must not shrink from a child content minimum.
                app.adaptive.render()
                self.assertEqual(app.routes.body().style.width, 540)
                adapter.mode = 'rail'
                impl.native.getWidth.return_value = 1400
                app.adaptive.render()
                self.assertEqual(app.routes.body().style.width, 628)
                impl.native_navigationview.getVisibility.return_value = 8
                app.adaptive.render()
                self.assertEqual(app.routes.body().style.width, 700)
        finally:
            app.native_host.adapter = None

    def test_chat_setup_does_not_connect_and_keeps_the_unsent_draft(self):
        app = self.app
        app.show_chat()
        app.chat_prompt.value = 'Keep my draft'
        self.assertFalse(app.chat_send.enabled)
        self.assertIn(app.chat_setup, app.chat_setup_box.children)
        app.chat_setup.on_press()
        self.assertEqual(app.routes.screens['chat'][-1][0], 'chat-settings')
        app.chat_url.value = 'http://127.0.0.1:1/v1'
        app.chat_model.value = 'example'
        app.save_chat_configuration()
        self.assertTrue(app.chat_send.enabled)
        self.assertNotIn(app.chat_setup, app.chat_setup_box.children)
        self.assertEqual(app.chat_prompt.value, 'Keep my draft')
        self.assertIsNone(app.chat_client)

    def test_library_empty_state_has_import_and_folder_exits(self):
        app = self.app
        app.show_library()
        catalog = app.reader_manager().catalog
        labels = [getattr(w, 'text', '') for w in widgets(catalog.library_rows)]
        self.assertIn('No configured library folders.', labels)
        self.assertIn('Import a book or comic…', labels)
        self.assertIn('Open Workspaces', labels)
        folder_hub = next(w for w in widgets(catalog.library_rows)
                          if getattr(w, 'text', '') == 'Open Workspaces')
        folder_hub.on_press()
        self.assertEqual(app.native_host.state.destination, 'files')


if __name__ == '__main__':
    unittest.main()
