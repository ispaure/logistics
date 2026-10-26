"""Notebook host actions retain document identity across native decisions/failures."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import test_notebook_storage as fixture
from services.documents.mobile_notebooks import install_notebook_controls, show_notebook_in_folder


class NotebookHostStorageTests(unittest.TestCase):
    setUp = fixture.NotebookStorageTests.setUp
    tearDown = fixture.NotebookStorageTests.tearDown
    run_async = fixture.NotebookStorageTests.run_async
    create = fixture.NotebookStorageTests.create
    stroke = fixture.NotebookStorageTests.stroke

    def test_canvas_html_loads_after_host_attachment_on_open_and_reopen(self):
        import toga
        from services.documents.mobile_notebooks import open_notebook
        attached = []
        original = toga.WebView.set_content
        def load(web, *args, **kwargs):
            if args[0] == 'https://logistics.invalid/notebooks/':
                attached.append(web.window is self.app.main_window)
            return original(web, *args, **kwargs)
        with patch.object(toga.WebView, 'set_content', new=load):
            panel = self.create(private=False)
            key = panel.key
            self.assertEqual(attached, [True])
            self.assertTrue(self.app.close_session(panel.session.id))
            self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
            self.assertEqual(attached, [True, True])

    def test_cancel_keeps_dirty_source_recovery_and_open_session(self):
        panel = self.create(private=False)
        self.stroke(panel)
        document = panel.document
        original = document.resource.read()
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='cancel')):
            self.assertFalse(self.run_async(panel.delete_document()))
        self.assertEqual(document.resource.read(), original)
        self.assertTrue(document.dirty)
        self.assertFalse(panel.busy)
        self.assertIn(panel.session.id, self.app.workspace.sessions)
        self.assertTrue((document.recovery.root / document.key).exists())

    def test_local_and_private_source_deletion_retires_only_that_session(self):
        for private in (False, True):
            with self.subTest(private=private):
                panel = self.create(private=private)
                document, session = panel.document, panel.session
                physical = document.resource.provider._physical(document.resource.path)
                recovery = document.recovery
                with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
                    self.assertTrue(self.run_async(panel.delete_document()))
                self.assertFalse(physical.exists())
                self.assertTrue(panel.closed)
                self.assertNotIn(session.id, self.app.workspace.sessions)
                if recovery:
                    self.assertFalse((recovery.root / document.key).exists())

    def test_changed_source_and_revoked_credentials_preserve_dirty_draft(self):
        for failure in ('changed', 'revoked'):
            panel = self.create(private=failure == 'revoked')
            self.stroke(panel)
            document = panel.document
            physical = document.resource.provider._physical(document.resource.path)
            if failure == 'changed':
                physical.write_bytes(b'external replacement')
            else:
                self.client.generation += 1
            expected = physical.read_bytes()
            with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
                with self.assertRaises((ValueError, OSError)):
                    self.run_async(panel.delete_document())
            self.assertEqual(physical.read_bytes(), expected)
            self.assertFalse(document.source_deleted)
            self.assertTrue(document.dirty)
            self.assertFalse(panel.closed)
            self.assertFalse(panel.busy)

    def test_multiple_windows_before_or_during_confirmation_block_deletion(self):
        panel = self.create(private=False)
        document = panel.document
        hosts = self.app.scene_manager.owners.hosts
        with patch.object(self.app.scene_manager.owners, 'hosts', {**hosts, 'other': object()}), \
                patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')) as dialog:
            with self.assertRaisesRegex(ValueError, 'other app windows'):
                self.run_async(panel.delete_document())
            dialog.assert_not_awaited()
        async def opened_window(dialog):
            self.app.scene_manager.owners.hosts = {**hosts, 'other': object()}
            return 'delete'
        try:
            with patch.object(self.app.main_window, 'dialog', side_effect=opened_window):
                with self.assertRaisesRegex(ValueError, 'other app windows'):
                    self.run_async(panel.delete_document())
        finally:
            self.app.scene_manager.owners.hosts = hosts
        self.assertTrue(document.resource.check())
        self.assertFalse(panel.busy)

    def test_retired_or_replaced_document_during_confirmation_is_not_deleted(self):
        panel = self.create(private=False)
        original = panel.document
        replacement = Mock()
        async def retarget(dialog):
            panel.document = replacement
            return 'delete'
        try:
            with patch.object(self.app.main_window, 'dialog', side_effect=retarget):
                self.assertFalse(self.run_async(panel.delete_document()))
            replacement.delete.assert_not_called()
            self.assertTrue(original.resource.check())
        finally:
            panel.document = original
        self.assertFalse(panel.busy)

    def test_recovery_failure_retains_draft_and_retry_never_deletes_replacement_file(self):
        panel = self.create(private=False)
        self.stroke(panel)
        document = panel.document
        physical = document.resource.provider._physical(document.resource.path)
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
            with patch.object(document.recovery, 'delete', side_effect=OSError('disk busy')):
                with self.assertRaisesRegex(OSError, 'file deleted, but recovery cleanup failed'):
                    self.run_async(panel.delete_document())
            self.assertTrue(document.source_deleted)
            self.assertFalse(physical.exists())
            self.assertTrue(document.dirty)
            self.assertFalse(panel.closed)
            self.assertIn(panel.session.id, self.app.workspace.sessions)
            physical.write_bytes(b'another writer created a new file')
            self.assertTrue(self.run_async(panel.delete_document()))
        self.assertEqual(physical.read_bytes(), b'another writer created a new file')
        self.assertFalse((document.recovery.root / document.key).exists())

    def test_failed_history_cleanup_can_be_retried_after_source_and_recovery_deleted(self):
        panel = self.create(private=False)
        document = panel.document
        with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='delete')):
            with patch.object(self.app.recent_documents, 'forget', side_effect=OSError('history busy')):
                with self.assertRaisesRegex(OSError, 'history busy'):
                    self.run_async(panel.delete_document())
            self.assertFalse(panel.closed)
            self.assertFalse(panel.busy)
            self.assertTrue(document.source_deleted)
            self.assertTrue(self.run_async(panel.delete_document()))
        self.assertTrue(panel.closed)

    def test_show_in_folder_delegates_to_host_and_ignores_retired_views(self):
        panel = self.create(private=False)
        with patch('mobile.document_sources.show_in_folder', AsyncMock(return_value=True)) as show:
            self.assertTrue(self.run_async(show_notebook_in_folder(panel)))
            show.assert_awaited_once_with(self.app, panel.session, panel)
            panel.closed = True
            self.assertFalse(self.run_async(show_notebook_in_folder(panel)))
            self.assertEqual(show.await_count, 1)
            panel.closed = False

    def test_ios_chrome_preserves_close_canvas_command(self):
        native = type('Native', (), {'__module__': 'toga_iOS.fixture'})()
        panel = SimpleNamespace(view=SimpleNamespace(_impl=native), web=Mock(evaluate_javascript=AsyncMock()))
        with patch('mobile.control_icons.icon_button', Mock()) as button:
            install_notebook_controls(panel)
        self.assertIs(panel.view._reader_close_button, button.return_value)
        self.assertEqual(panel.view._native_reader_buttons(), [])
        self.run_async(button.call_args.kwargs['on_press']())
        panel.web.evaluate_javascript.assert_awaited_once_with("send({op:'library'})")
