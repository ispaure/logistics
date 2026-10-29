"""Two editor owners survive switches, cold launch and close independently."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch
from mobile.app import LogisticsMobile


class WorkspaceUITests(unittest.TestCase):
    def test_unavailable_restored_entry_can_retry_or_remove_without_switching_editor(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_documents()
            owner = app.editor_view
            missing = app.workspace.open('managed-text', 'f' * 32, 'text')
            app.session_opener(missing.id)()
            self.assertIs(app.editor_view, owner)
            self.assertEqual(app.body.children[0].children[0].text, 'Document unavailable')
            app.session_opener(missing.id)()
            self.assertEqual(app.body.children[0].children[0].text, 'Document unavailable')
            self.assertTrue(app.close_session(missing.id))
            self.assertNotIn(missing.id, app.workspace.sessions)
            self.assertTrue(owner.document.snapshot.path.exists())

    def test_preview_mode_restores_per_session_and_back_targets_its_owner(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_documents()
            a = app.editor_view
            a.editor.value = '# A'
            app.show_preview()
            self.assertEqual(a.session.view['markdown_mode'], 'preview')
            back = next(child.on_press for child in app.editor_view.markdown_speech.button.parent.children
                        if getattr(child, 'accessible_name', '') == 'Edit Markdown')
            app.new_document()
            b = app.editor_view
            b.editor.value = '# B'
            app.show_documents()
            app.session_opener(a.session.id)()
            self.assertIs(app.editor_view, a)
            self.assertIs(app.body.children[0], app.preview_box)
            # The window-modal decision keeps the owner's preview mounted.
            with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as dialog:
                app.routes.back()
                app.loop.run_until_complete(asyncio.gather(*app._document_close_tasks.values()))
            dialog.assert_awaited_once()
            self.assertFalse(app._document_close_tasks)
            self.assertIs(app.body.children[0], a.preview_box)
            self.assertEqual(a.session.view['markdown_mode'], 'preview')
            self.assertIn(a.session.id, app.workspace.sessions)
            app.show_home()
            app.session_opener(b.session.id)()
            back()
            self.assertIs(app.editor_view, a)
            self.assertEqual(a.session.view['markdown_mode'], 'edit')
            self.assertEqual(app.editor.value, '# A')
            self.assertTrue(app.close_session(a.session.id, choice='discard'))
            back()
            self.assertIs(app.editor_view, b)

    def test_close_choices_target_owner_and_failed_save_keeps_it_open(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_documents()
            a = app.editor_view
            a.editor.value = 'A draft'
            app.new_document()
            b = app.editor_view
            b.editor.value = 'B draft'
            self.assertFalse(app.close_session(a.session.id, choice='cancel'))
            self.assertEqual(a.document.text, 'A draft')
            a.document.snapshot.path.write_bytes(b'External change')
            self.assertFalse(app.close_session(a.session.id, choice='save'))
            self.assertIn(a.session.id, app.workspace.sessions)
            self.assertEqual(app.current.id, b.document.id)
            self.assertTrue(app.close_session(a.session.id, choice='discard'))
            self.assertEqual(app.store.open(a.document.id).text, 'External change')
            self.assertEqual(app.current.text, 'B draft')
            self.assertTrue(app.close_session(b.session.id, choice='save'))
            self.assertEqual(app.store.open(b.document.id).snapshot.original, b'B draft')

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


    def test_formatted_editor_belongs_to_its_document_and_close_retires_it(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_documents()
                owner = app.editor_view
                owner.name.value = 'Preview.md'
                owner.session.view['markdown_split'] = True
                owner.apply_split(1200)
                for width in (1200, 800, 390):
                    owner.apply_split(width)
                    self.assertEqual(owner.editor_area.children, [owner.formatted.view])
                self.assertTrue(app.close_session(owner.session.id))
                self.assertTrue(owner.formatted.closed)
            finally:
                app.main_window.close()
                app.loop.close()
