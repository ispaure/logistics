"""Two editor owners survive switches, cold launch and close independently."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile


class WorkspaceUITests(unittest.TestCase):
    def test_two_drafts_have_independent_widgets_recovery_and_close(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_documents()
            a = app.current.id
            app.name.value = 'Same.md'
            app.editor.value = 'A draft'
            a_view = app.editor_view
            app.new_document()
            b = app.current.id
            app.name.value = 'Same.md'
            app.editor.value = 'B draft'
            b_view = app.editor_view
            self.assertIsNot(a_view.editor, b_view.editor)
            # A delayed callback from the inactive native editor owns A, not B.
            a_view.editor.value = 'A independent draft'
            self.assertEqual(app.current.text, 'B draft')
            self.assertEqual(app.store.open(a).text, 'A independent draft')
            self.assertEqual(len(app.workspace.sessions), 2)
            app.open_document(a)
            self.assertIs(app.editor_view, a_view)
            app.show_locations()
            app.show_settings()
            app.open_document(b)
            app.save_workspace()
            restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.assertEqual(restored.current.id, b)
            self.assertEqual(restored.current.text, 'B draft')
            restored.open_document(a)
            self.assertEqual(restored.current.text, 'A independent draft')
            closed = restored.editor_view
            self.assertTrue(restored.close_session(closed.session.id))
            self.assertEqual(restored.current.id, b)
            self.assertEqual(restored.current.text, 'B draft')
            closed.editor.value = 'stale after close'
            self.assertEqual(restored.store.open(a).text, 'A independent draft')
            self.assertEqual(len(restored.workspace.sessions), 1)
            restored.open_document(a)
            restored.open_document(a)
            self.assertEqual(len(restored.workspace.sessions), 2)

