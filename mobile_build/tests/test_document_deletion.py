"""Confirmed managed-document deletion preserves cancellation and neighboring drafts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from mobile.recent_documents import RecentDocuments


class DocumentDeletionTests(unittest.TestCase):
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

    def delete(self, owner, answer='delete'):
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value=answer)) as dialog:
            result = self.app.loop.run_until_complete(self.app.request_delete_document(owner.session.id))
        return result, dialog

    def test_cancel_keeps_unsaved_document_and_recent_entry(self):
        app = self.app
        app.editor.value = 'Unsaved content'
        owner = app.editor_view
        result, dialog = self.delete(owner, 'cancel')
        self.assertFalse(result)
        self.assertIn('unsaved changes will be lost', dialog.call_args.args[0].message)
        self.assertIn(owner.session.id, app.workspace.sessions)
        self.assertEqual(app.store.open(owner.document.id).text, 'Unsaved content')
        self.assertIn(owner.document.id, [item['resource'] for item in app.recent_documents.items])

    def test_delete_removes_recovery_history_and_import_identity_keeps_neighbor(self):
        app = self.app
        app.new_document(extension='md')
        owner = app.editor_view
        app.editor.value = '# Unsaved'
        app.show_preview()
        self.assertIn('Delete document…', dict(owner.actions.actions))
        self.assertIn('Delete document…', dict(owner.preview_actions.actions))
        self.assertIn(owner.preview_actions_button, owner.preview_box._native_reader_buttons())
        from mobile.resource_imports import ResourceImports
        app.resource_imports = ResourceImports(app.private_root)
        source = app.private_root / 'original.md'
        source.write_text('original')
        app.resource_imports.remember(source, 'managed-text', owner.document.id)
        app.new_document()
        neighbor = app.editor_view
        app.editor.value = 'Keep this draft'
        self.assertTrue(self.delete(owner)[0])
        self.assertNotIn(owner.session.id, app.workspace.sessions)
        self.assertFalse(app.store.path(owner.document.id, '.data').exists())
        self.assertFalse(app.store.path(owner.document.id, '.json').exists())
        self.assertNotIn(owner.document.id, [item['resource'] for item in RecentDocuments(app.private_root).items])
        self.assertIsNone(app.resource_imports.find(source))
        self.assertEqual(source.read_text(), 'original')
        self.assertIs(app.editor_view, neighbor)
        self.assertEqual(neighbor.document.text, 'Keep this draft')

    def test_empty_untitled_requires_confirmation_and_leaves_empty_workspace(self):
        owner = self.app.editor_view
        self.assertFalse(owner.document.modified)
        self.assertFalse(self.delete(owner, False)[0])
        self.assertTrue(self.delete(owner)[0])
        self.assertFalse(self.app.workspace.sessions)
        self.assertIsNone(self.app.current)
        self.assertEqual(self.app.store.documents(), ([], []))

    def test_failed_delete_keeps_open_buffer(self):
        owner = self.app.editor_view
        self.app.editor.value = 'Retain me'
        with patch.object(self.app.store, 'delete', side_effect=OSError('read-only')):
            self.assertFalse(self.delete(owner)[0])
        self.assertIn(owner.session.id, self.app.workspace.sessions)
        self.assertEqual(owner.document.text, 'Retain me')
        self.assertEqual(self.app.store.open(owner.document.id).text, 'Retain me')
        self.assertIn('read-only', owner.status.text)

    def test_deleting_current_document_resumes_neighbor_without_recreating_recovery(self):
        app = self.app
        neighbor = app.editor_view
        app.editor.value = 'Neighbor'
        app.new_document(extension='md')
        owner = app.editor_view
        app.editor.value = '# Delete me'
        app.show_preview()
        self.assertTrue(self.delete(owner)[0])
        self.assertIs(app.editor_view, neighbor)
        self.assertFalse(app.store.path(owner.document.id, '.json').exists())
        self.assertNotIn(owner.document.id, [item['resource'] for item in RecentDocuments(app.private_root).items])

    def test_new_window_while_confirming_blocks_deletion(self):
        app = self.app
        owner = app.editor_view
        hosts = dict(app.scene_manager.owners.hosts)
        async def open_window(dialog):
            app.scene_manager.owners.hosts['another-window'] = object()
            return 'delete'
        try:
            with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=open_window)):
                self.assertFalse(app.loop.run_until_complete(app.request_delete_document(owner.session.id)))
            self.assertIn(owner.session.id, app.workspace.sessions)
            self.assertTrue(app.store.path(owner.document.id, '.json').exists())
            self.assertIn('other app windows', owner.status.text)
        finally:
            app.scene_manager.owners.hosts.clear()
            app.scene_manager.owners.hosts.update(hosts)

    def test_changed_owner_while_confirmation_open_is_not_deleted(self):
        app = self.app
        owner = app.editor_view
        async def close_while_confirming(dialog):
            app.close_session(owner.session.id)
            return 'delete'
        with patch.object(app.main_window, 'dialog', new=AsyncMock(side_effect=close_while_confirming)):
            self.assertFalse(app.loop.run_until_complete(app.request_delete_document(owner.session.id)))
        self.assertTrue(app.store.path(owner.document.id, '.json').exists())
