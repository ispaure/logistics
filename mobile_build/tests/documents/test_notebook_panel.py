"""Installed mobile destination, local recovery and shared drawing command bridge."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import unittest
from mobile.navigation import DESTINATIONS
from features.notebooks.notebook import Notebook
from features.notebooks.mobile.documents import open_notebook
from mobile_build.tests.support.notebooks import create_template_notebook_app


class NotebookPanelTests(unittest.TestCase):
    def setUp(self):
        self.app = create_template_notebook_app(self)

    def test_failed_canvas_retirement_keeps_private_protection_until_success(self):
        from unittest.mock import patch
        from services.session_auth import ResumePassword
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        gate = panel.privacy_gate = ResumePassword('synthetic')
        self.app.protection.changed()
        with patch.object(panel, 'retire_canvas', side_effect=RuntimeError('retirement failed')):
            with self.assertRaisesRegex(RuntimeError, 'retirement failed'):
                panel.dispose()
        self.assertIn(gate, self.app.protection.retained_gates())
        panel.dispose()
        self.assertNotIn(gate, self.app.protection.retained_gates())

    def test_recovery_notebook_title_follows_rename_and_close(self):
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.perform({'op': 'rename', 'name': 'Field notes'}))
        self.assertEqual(panel.view._native_reader_title(), 'Field notes')
        self.assertEqual(panel.view._document_path(), f'Field notes\n\n{panel.repository.root / panel.key}')
        panel.dispose()
        self.assertIsNone(panel.view._document_path())

    def test_title_hold_uses_the_notebooks_window_and_leaves_it_clean(self):
        from unittest.mock import AsyncMock, patch
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        self.assertIsNotNone(panel.view.window)
        with patch.object(panel.view.window, 'dialog', new_callable=AsyncMock) as dialog, \
                patch('toga.InfoDialog') as location_dialog:
            self.app.loop.run_until_complete(panel.perform({'op': 'document-location'}))
        location_dialog.assert_called_once_with('Document location', panel.view._document_path())
        dialog.assert_awaited_once_with(location_dialog.return_value)
        self.assertFalse(panel.document.dirty)

    def test_reopen_uses_document_recovery_owner_and_can_checkpoint_afterward(self):
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        self.assertIs(panel.repository, panel.document.recovery)
        key = panel.key
        app.loop.run_until_complete(panel.load(lambda: panel.repository.open(key), key))
        panel.editor.apply({'op': 'stroke', 'points': [[30, 40, .5]]})
        self.assertEqual(len(panel.document.recovery.open(key).page(0).strokes), 1)

    def test_replacing_canvas_during_native_confirmation_does_not_delete_new_page(self):
        from unittest.mock import patch
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        panel.editor.apply({'op': 'add-page'})
        old_editor, old_bridge = panel.editor, panel.bridge
        replacement = Notebook.new('Replacement')
        async def confirm(dialog):
            panel.open(replacement, panel.repository.create(replacement))
            return True
        with patch.object(app.main_window, 'dialog', side_effect=confirm):
            app.loop.run_until_complete(panel.perform({'op': 'delete-page'}))
        self.assertEqual(len(old_editor.notebook.pages), 2)
        self.assertEqual(len(replacement.pages), 1)
        self.assertFalse(old_bridge.active)
        self.assertFalse(panel.busy)
        panel.web.evaluate_javascript.assert_not_awaited()
        app.loop.run_until_complete(panel.perform({'op': 'rename', 'name': 'Usable replacement'}))
        self.assertEqual(replacement.name, 'Usable replacement')

    def test_queued_command_for_retired_canvas_cannot_rename_replacement(self):
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        old = panel.bridge
        panel.mount_canvas()
        app.loop.run_until_complete(panel.perform({'op': 'rename', 'name': 'Stale'}, canvas=old))
        self.assertNotEqual(panel.editor.notebook.name, 'Stale')
        self.assertFalse(panel.document.dirty)

    def test_close_acknowledges_before_cancelled_dirty_guard(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        path = self.app.storage_root / 'cancel-close.rmdoc'
        path.write_bytes(Notebook.new().to_bytes())
        app.loop.run_until_complete(open_notebook(app, path=path))
        panel = app.notebook_panel
        panel.editor.apply(dict(op='rename', name='Dirty'))
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='cancel')) as dialog:
            app.loop.run_until_complete(panel.perform(dict(op='library')))
        dialog.assert_awaited_once()
        panel.web.evaluate_javascript.assert_awaited()
        app.keep_reader_editing(panel.session.id)
        self.assertFalse(panel.busy)
        self.assertIn(panel.session.id, app.workspace.sessions)

    def test_delete_notebook_draft_cancel_then_confirm(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        recovery = panel.repository.root / panel.key
        key = panel.session.id
        self.assertTrue(panel.state()['can_delete'])
        self.assertFalse(panel.state()['has_source'])
        del panel.session
        self.assertTrue(panel.state()['can_delete'], 'Draft menu must initialize before session attachment')
        panel.session = app.workspace.sessions[key]
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='cancel')):
            app.loop.run_until_complete(panel.perform(dict(op='delete-file')))
        self.assertTrue(recovery.exists())
        self.assertIn(key, app.workspace.sessions)
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='delete')):
            app.loop.run_until_complete(panel.perform(dict(op='delete-file')))
        self.assertFalse(recovery.exists())
        self.assertNotIn(key, app.workspace.sessions)
        self.assertTrue(panel.closed)

    def test_delete_saved_notebook_preserves_external_changes(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        path = self.app.storage_root / 'delete-source.rmdoc'
        path.write_bytes(Notebook.new().to_bytes())
        app.loop.run_until_complete(open_notebook(app, path=path))
        panel = app.notebook_panel
        original = path.read_bytes()
        path.write_bytes(Notebook.new('Changed elsewhere').to_bytes())
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='delete')):
            app.loop.run_until_complete(panel.perform(dict(op='delete-file')))
        self.assertTrue(path.exists())
        self.assertFalse(panel.closed)
        self.assertNotEqual(path.read_bytes(), original)
        self.assertIn('File changed', panel.web.evaluate_javascript.call_args.args[0])
        # Reopen to admit the new revision, then delete its file and recovery.
        panel.document.resource.read()
        recovery = panel.repository.root / panel.key
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='delete')):
            app.loop.run_until_complete(panel.perform(dict(op='delete-file')))
        self.assertFalse(path.exists())
        self.assertFalse(recovery.exists())

    def test_folder_action_uses_live_notebook_source(self):
        from mobile.document_sources import folder_location
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        self.assertIsNone(folder_location(app, panel.session))
        path = self.app.storage_root / 'reveal.rmdoc'
        path.write_bytes(Notebook.new().to_bytes())
        app.loop.run_until_complete(open_notebook(app, path=path))
        panel = app.notebook_panel
        location = folder_location(app, panel.session)
        self.assertIs(location['provider'], panel.document.resource.provider)
        self.assertEqual(location['key'], path.name)
        self.assertTrue(panel.state()['has_source'])

    def test_page_delete_cancel_then_confirm_retains_history(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        panel.editor.apply(dict(op='add-page'))
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value=False)):
            app.loop.run_until_complete(panel.perform(dict(op='delete-page')))
        self.assertEqual(len(panel.editor.notebook.pages), 2)
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value=True)):
            app.loop.run_until_complete(panel.perform(dict(op='delete-page')))
        self.assertEqual(len(panel.editor.notebook.pages), 1)
        panel.editor.apply(dict(op='undo'))
        self.assertEqual(len(panel.editor.notebook.pages), 2)

    def test_destination_order_and_retained_workspace(self):
        app=self.app
        self.assertEqual(DESTINATIONS[:3],('home','files','documents'))
        self.assertNotIn('notebooks', DESTINATIONS)
        app.loop.run_until_complete(open_notebook(app))
        panel=app.notebook_panel
        self.assertIn(panel.session.id, app.workspace.sessions)
        app.loop.run_until_complete(panel.new())
        book=panel.editor.notebook
        panel.editor.apply(dict(op='stroke',points=[[100,100,.4],[130,140,.7]],tool=12,width=3))
        app.select_destination('home')
        app.native_host.activate('home')
        previous = asyncio.all_tasks(app.loop)
        app.session_opener(panel.session.id)()
        opening = [task for task in asyncio.all_tasks(app.loop) - previous
                   if task.get_coro().__name__ == 'open_notebook']
        self.assertEqual(len(opening), 1)
        self.assertTrue(app.loop.run_until_complete(opening[0]))
        self.assertIs(app.notebook_panel.editor.notebook,book)
        restored=panel.repository.open(panel.key)
        self.assertEqual(len(restored.page(0).strokes),1)
        self.assertEqual(restored.page(0).strokes[0].tool,12)

    def test_retiring_canvas_releases_native_refresh_controller(self):
        from unittest.mock import Mock
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.new())
        controller = Mock()
        panel.boox_refresh = controller
        panel.library()
        controller.close.assert_called_once_with()
        self.assertIsNone(panel.boox_refresh)
        panel.dispose()
        controller.close.assert_called_once_with()

    def test_notebook_close_returns_to_the_documents_overview(self):
        app = self.app
        app.show_documents_hub()
        app.loop.run_until_complete(open_notebook(app))
        panel = app.notebook_panel
        key = panel.session.id
        app.loop.run_until_complete(panel.perform(dict(op='library')))
        self.assertNotIn(key, app.workspace.sessions)
        self.assertTrue(panel.closed)
        self.assertEqual(app.native_host.state.destination, 'documents')
        self.assertFalse(app.routes.screens['documents'])

    def test_notebook_close_keeps_unsaved_edits_for_the_close_prompt(self):
        from unittest.mock import AsyncMock, patch
        app = self.app
        path = self.app.storage_root / 'unsaved.rmdoc'
        path.write_bytes(Notebook.new('Original').to_bytes())
        original = path.read_bytes()
        app.loop.run_until_complete(open_notebook(app, path=path))
        panel = app.notebook_panel
        panel.editor.apply(dict(op='rename', name='Unsaved title'))
        with patch.object(app.main_window, 'dialog', AsyncMock(return_value='cancel')) as dialog:
            app.loop.run_until_complete(panel.perform(dict(op='library')))
        dialog.assert_awaited_once()
        self.assertIn(panel.session.id, app.workspace.sessions)
        self.assertTrue(panel.document.dirty)
        self.assertFalse(panel.closed)
        self.assertEqual(path.read_bytes(), original)

    def test_workspace_opens_a_notebook_copy_without_changing_source(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        app = self.app
        owner = app.read_managed_file.__self__
        path = self.app.storage_root / 'from-workspaces.rmdoc'
        path.write_bytes(Notebook.new('From Workspaces').to_bytes())
        original = path.read_bytes()
        app.loop.run_until_complete(app.show_files())
        with patch.object(owner, 'selected_file', return_value=(LocalFiles(path.parent), path.name)):
            result = app.loop.run_until_complete(owner.read_managed_file())
        self.assertTrue(result)
        self.assertEqual(app.native_host.state.destination, 'files')
        self.assertEqual(app.notebook_panel.session.provider, 'notebook')
        self.assertEqual(app.notebook_panel.editor.notebook.name, 'From Workspaces')
        app.notebook_panel.editor.apply(dict(op='add-page'))
        self.assertEqual(path.read_bytes(), original)

    def test_workspace_rmdoc_open_honors_navigation_veto(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        app = self.app
        owner = app.read_managed_file.__self__
        path = self.app.storage_root / 'veto.rmdoc'
        path.write_bytes(Notebook.new().to_bytes())
        provider = LocalFiles(path.parent)
        # Build ordinary local controls before supplying an explicit selection.
        app.loop.run_until_complete(app.show_files())
        with patch.object(owner, 'selected_file', return_value=(provider, path.name)), \
                patch.object(app, 'checkpoint', return_value=False):
            result = app.loop.run_until_complete(owner.read_managed_file())
        self.assertFalse(result)
        self.assertFalse(hasattr(app, 'notebook_panel'))

    def test_copy_and_reopen_synthetic_import(self):
        app=self.app
        app.loop.run_until_complete(open_notebook(app))
        panel=app.notebook_panel
        path=self.app.storage_root/'sample.rmdoc'
        path.write_bytes(Notebook.new('Original').to_bytes())
        original=path.read_bytes()
        app.loop.run_until_complete(panel.open_path(path))
        panel.editor.apply(dict(op='add-page'))
        self.assertEqual(path.read_bytes(),original)
        self.assertEqual(len(panel.repository.open(panel.key).pages),2)

    def test_invalid_workspace_import_reports_failure(self):
        from unittest.mock import patch
        from commonUtils.runtime.resources.local import LocalFiles
        path = self.app.storage_root / 'damaged.rmdoc'
        path.write_bytes(b'not a ZIP')
        owner = self.app.read_managed_file.__self__
        self.app.loop.run_until_complete(self.app.show_files())
        with patch.object(owner, 'selected_file', return_value=(LocalFiles(path.parent), path.name)):
            result = self.app.loop.run_until_complete(owner.read_managed_file())
        self.assertFalse(result)
        self.assertIn('Invalid RMDOC', self.app.notebook_panel.status.text)

    def test_retired_canvas_and_busy_commands_do_not_consume_current_sequence(self):
        import json
        from threading import Event
        from unittest.mock import patch
        from urllib.parse import quote
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.new())
        old = panel.web
        self.app.loop.run_until_complete(panel.new())
        self.assertIsNone(old.on_navigation_starting._raw)
        command = panel.bridge.url + '?command=' + quote(json.dumps(dict(sequence=1,action=dict(op='rename',name='Current'))))
        applied, released = asyncio.Event(), Event()
        apply = panel.editor.apply
        def held_apply(action):
            apply(action)
            self.app.loop.call_soon_threadsafe(applied.set)
            if not released.wait(5):
                raise TimeoutError('fixture was not released')
        scheduled = []
        create_task = self.app.loop.create_task
        def schedule(coroutine):
            task = create_task(coroutine)
            scheduled.append(task)
            return task
        with patch.object(panel.editor, 'apply', side_effect=held_apply):
            with patch.object(self.app.loop, 'create_task', side_effect=schedule):
                panel.navigate(old, command)
                self.assertEqual(panel.bridge.sequence, 0)
                panel.busy = True
                panel.navigate(panel.web, command)
                self.assertEqual(panel.bridge.sequence, 0)
                self.assertEqual(scheduled, [])
                panel.busy = False
                panel.navigate(panel.web, command)
                self.assertTrue(panel.busy)
                self.assertEqual(len(scheduled), 1)
            async def complete_command():
                try:
                    await asyncio.wait_for(applied.wait(), 5)
                    self.assertEqual(panel.editor.notebook.name, 'Current')
                    self.assertTrue(panel.busy)
                    self.assertFalse(scheduled[0].done())
                    next_command = panel.bridge.url + '?command=' + quote(json.dumps(
                        dict(sequence=2, action=dict(op='rename', name='Must not run'))))
                    panel.navigate(panel.web, next_command)
                    self.assertEqual(panel.bridge.sequence, 1)
                finally:
                    released.set()
                    await asyncio.wait_for(scheduled[0], 5)
            self.app.loop.run_until_complete(complete_command())
        self.assertEqual(panel.editor.notebook.name, 'Current')
        self.assertEqual(panel.bridge.sequence, 1)
        self.assertFalse(panel.busy)

    def test_disposal_during_import_cannot_reopen_canvas(self):
        from threading import Event
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        started, released = Event(), Event()
        def read():
            started.set()
            if not released.wait(5):
                raise TimeoutError('fixture was not released')
            return Notebook.new('Pending')
        async def scenario():
            loading = asyncio.create_task(panel.load(read))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertFalse(await panel.new())
                panel.dispose()
            finally:
                released.set()
            self.assertFalse(await loading)
            self.assertIsNone(panel.web)
            self.assertFalse(panel.busy)
        self.app.loop.run_until_complete(scenario())

    def test_failed_canvas_acknowledgement_offers_reopen_of_saved_content(self):
        from unittest.mock import AsyncMock, patch
        self.app.loop.run_until_complete(open_notebook(self.app))
        panel = self.app.notebook_panel
        self.app.loop.run_until_complete(panel.new())
        key = panel.key
        with patch.object(panel.web, 'evaluate_javascript', AsyncMock(side_effect=RuntimeError('view unavailable'))):
            self.app.loop.run_until_complete(panel.perform(dict(op='rename', name='Saved content')))
        self.assertIsNone(panel.web)
        self.assertIn('Reopen it to resume', panel.status.text)
        self.assertEqual(panel.repository.open(key).name, 'Saved content')


if __name__=='__main__':
    unittest.main()
