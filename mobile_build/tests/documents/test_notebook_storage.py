"""Notebook storage parity, privacy, failure retention and destination handoff."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, AsyncMock

from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.mobile.documents import open_notebook
from services.documents.storage import DocumentResource
from mobile_build.tests.support.notebooks import create_notebook, create_storage_notebook_app, draw_stroke


class NotebookStorageTests(unittest.TestCase):
    def setUp(self):
        self.app, self.client, self.provider = create_storage_notebook_app(self)
        self.root = self.app.storage_root

    def run_async(self, action):
        return self.app.loop.run_until_complete(action)

    def create(self, *, private=True):
        return create_notebook(self, private=private)

    def stroke(self, panel):
        draw_stroke(panel)

    def select_missing_collection(self):
        import json
        from services.documents.locations import CONFIG
        volume = self.root / 'Removed SD card'
        (self.app.private_root / CONFIG).write_text(json.dumps(
            dict(volume=str(volume), token='a' * 32)))

    def private_download(self):
        source = self.app.private_root / 'Downloads' / 'Sketch.rmdoc'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(Notebook.new('Sketch').to_bytes())
        return source

    def test_private_download_reuses_indexed_draft_without_collection_drive(self):
        from mobile.resource_imports import ResourceImports
        source = self.private_download()
        self.select_missing_collection()
        self.assertTrue(self.run_async(self.app.open_local_document(source)))
        panel = self.app.notebook_panel
        self.assertEqual(ResourceImports(self.app.private_root).find(source),
                         dict(provider='notebook', resource=panel.key))
        self.stroke(panel)
        undo = list(panel.editor.undo)
        panel.document.resource.close()
        panel.document.resource = None
        self.assertTrue(self.run_async(self.app.open_local_document(source)))
        self.assertIs(self.app.notebook_panel, panel)
        self.assertEqual(panel.editor.undo, undo)
        self.assertTrue(panel.document.dirty)

    def test_private_download_orphan_discard_without_collection_drive(self):
        from mobile.resource_imports import ResourceImports
        source = self.private_download()
        original = source.read_bytes()
        self.assertTrue(self.run_async(self.app.open_local_document(source)))
        panel = self.app.notebook_panel
        key = panel.key
        self.stroke(panel)
        panel.document.resource.close()
        panel.document.resource = None
        self.select_missing_collection()
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))
        self.assertFalse((self.app.private_root / 'notebooks' / key).exists())
        self.assertIsNone(ResourceImports(self.app.private_root).find(source))
        self.assertEqual(source.read_bytes(), original)

    def test_external_notebook_open_reports_missing_collection_drive(self):
        with TemporaryDirectory() as public:
            source = Path(public) / 'Public sketch.rmdoc'
            original = Notebook.new('Public sketch').to_bytes()
            source.write_bytes(original)
            self.select_missing_collection()
            self.assertFalse(self.run_async(self.app.open_local_document(source)))
            self.assertIn('Collection drive unavailable', self.app.notebook_panel.status.text)
            self.assertFalse(self.app.workspace.sessions)
            self.assertEqual(source.read_bytes(), original)

    def test_delete_uses_resource_and_recovery_owners_for_local_and_private(self):
        for private in (False, True):
            with self.subTest(private=private):
                panel = self.create(private=private)
                document = panel.document
                resource, recovery, key = document.resource, document.recovery, document.key
                physical = resource.provider._physical(resource.path)
                with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='delete')):
                    self.run_async(panel.delete_document())
                self.assertFalse(physical.exists())
                if recovery is not None:
                    self.assertFalse((recovery.root / key).exists())

    def test_delete_cancel_and_changed_source_preserve_notebook_draft(self):
        panel = self.create()
        self.stroke(panel)
        resource = panel.document.resource
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')):
            self.run_async(panel.delete_document())
        self.assertTrue(panel.document.dirty)
        DocumentResource.publish(self.provider, resource.path, Notebook.new('External').to_bytes(),
            max_bytes=MAX_ARCHIVE, expected_revision=resource.revision)
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='delete')):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.run_async(panel.delete_document())
        self.assertTrue(panel.document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)

    def test_private_creation_save_reopen_and_plaintext_persistence_exclusion(self):
        panel = self.create()
        self.assertTrue(panel.session.transient)
        self.assertIsNone(panel.document.recovery)
        self.stroke(panel)
        self.assertTrue(panel.document.dirty)
        self.assertFalse(self.app.close_session(panel.session.id))
        self.assertFalse(self.app.clear_private_reader())
        self.run_async(panel.perform({'op': 'save'}))
        self.assertFalse(panel.document.dirty)
        resource = panel.document.resource
        with resource.provider.open(resource.path) as stream:
            self.assertEqual(len(Notebook.read(stream.read()).page(0).strokes), 1)
        raw = resource.provider._physical(resource.path).read_bytes()
        self.assertNotIn(b'Private sketch', raw)
        self.assertTrue(self.app.close_session(panel.session.id))
        reopened = DocumentResource(self.provider, 'Private sketch.rmdoc', max_bytes=MAX_ARCHIVE)
        self.assertTrue(self.run_async(open_notebook(self.app, resource=reopened)))
        self.assertEqual(len(self.app.notebook_panel.editor.notebook.page(0).strokes), 1)
        for name in ('workspace.json', 'recent-documents.json', 'resource-imports.json'):
            path = self.root / name
            if path.exists():
                self.assertNotIn('Private sketch', path.read_text())
        self.assertEqual(list((self.root / 'notebooks').glob('**/base.rmdoc')), [])
        self.assertEqual(list((self.root / 'notebooks').glob('**/*.rm')), [])
        self.assertEqual(list((self.root / 'notebooks').glob('**/source.json')), [])

    def test_failed_save_and_revision_conflict_keep_strokes_and_original(self):
        panel = self.create()
        self.stroke(panel)
        resource = panel.document.resource
        original = resource.provider._physical(resource.path).read_bytes()
        with patch.object(resource.provider, 'replace_bytes', side_effect=OSError('full disk')):
            self.run_async(panel.perform({'op': 'save'}))
        self.assertTrue(panel.document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        self.assertEqual(resource.provider._physical(resource.path).read_bytes(), original)
        DocumentResource.publish(self.provider, resource.path, Notebook.new('External').to_bytes(),
            max_bytes=MAX_ARCHIVE, expected_revision=resource.revision)
        self.run_async(panel.perform({'op': 'save'}))
        self.assertTrue(panel.document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        with self.provider.open(resource.path) as stream:
            self.assertEqual(Notebook.read(stream.read()).name, 'External')

    def test_quit_without_saving_drops_recovery_edits_on_file_and_key_reopen(self):
        panel = self.create(private=False)
        source = panel.document.resource.provider.root / panel.document.resource.path
        key = panel.key
        for by_key in (False, True):
            with self.subTest(by_key=by_key):
                if by_key:
                    self.assertTrue(self.run_async(open_notebook(self.app, path=source)))
                    panel = self.app.notebook_panel
                original = source.read_bytes()
                saved_strokes = len(Notebook.read(original).page(0).strokes)
                self.stroke(panel)
                with patch.object(self.app.main_window, 'dialog', AsyncMock(return_value='discard')):
                    self.assertTrue(self.app.request_close_session(panel.session.id))
                    tasks = list(self.app._document_close_tasks.values())
                    for task in tasks:
                        self.run_async(task)
                self.assertNotIn(panel.session.id, self.app.workspace.sessions)
                self.assertEqual(source.read_bytes(), original)
                self.assertTrue(self.run_async(open_notebook(self.app, **({'key': key} if by_key else {'path': source}))))
                reopened = self.app.notebook_panel
                self.assertFalse(reopened.document.dirty)
                self.assertEqual(len(reopened.editor.notebook.page(0).strokes), saved_strokes)
                self.assertTrue(self.app.close_session(reopened.session.id))

    def test_discard_after_save_keeps_saved_strokes(self):
        panel = self.create(private=False)
        self.stroke(panel)
        self.run_async(panel.perform({'op': 'save'}))
        source = panel.document.resource.provider.root / panel.document.resource.path
        saved = source.read_bytes()
        self.stroke(panel)
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))
        self.assertEqual(source.read_bytes(), saved)
        self.assertTrue(self.run_async(open_notebook(self.app, path=source)))
        self.assertEqual(len(self.app.notebook_panel.editor.notebook.page(0).strokes), 1)

    def test_rejected_first_checkpoint_reopens_latest_clean_source(self):
        from services.documents.mobile_storage import notebook_binding
        panel = self.create(private=False)
        document = panel.document
        key = document.key
        binding = notebook_binding(document.recovery, key)
        before = binding.read_bytes()
        source = document.resource.provider.root / document.resource.path
        replacement = Notebook.new('Replacement source', template='Logistics Daily planner')
        replacement.members['opaque/future.bin'] = b'new source asset'
        saved = replacement.to_bytes()
        source.write_bytes(saved)
        with patch('features.notebooks.recovery.atomic_write_json', side_effect=OSError('Recovery unavailable')):
            with self.assertRaisesRegex(OSError, 'Recovery unavailable'):
                self.stroke(panel)
        self.assertFalse(document.dirty)
        self.assertEqual(binding.read_bytes(), before)
        self.assertEqual(len(document.book.page(0).strokes), 0)
        self.assertTrue(self.app.close_session(panel.session.id))
        self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        reopened = self.app.notebook_panel.document
        self.assertEqual(reopened.book.id, replacement.id)
        self.assertEqual(reopened.book.name, 'Replacement source')
        self.assertIsNotNone(reopened.resource)
        self.assertFalse(reopened.dirty)
        self.assertEqual(reopened.recovery.open(key).members, Notebook.read(saved).members)
        self.assertEqual(source.read_bytes(), saved)

    def test_unconfirmed_recovery_blocks_close_until_confirmed_retry(self):
        from features.notebooks.recovery import RecoveryIncomplete
        self.assertTrue(self.run_async(open_notebook(self.app, name='Recovery-only draft')))
        panel = self.app.notebook_panel
        document = panel.document
        self.assertIsNone(document.resource)
        original_read = Path.read_bytes
        manifest = document.recovery.root / document.key / 'state.json'
        attempted = False
        def reject_publication(*args, **kwargs):
            nonlocal attempted
            attempted = True
            raise OSError('Publication interrupted')
        def unreadable(path):
            if attempted and path == manifest:
                raise OSError('Recovery readback unavailable')
            return original_read(path)
        with patch('features.notebooks.recovery.atomic_write_json', side_effect=reject_publication), \
                patch.object(Path, 'read_bytes', unreadable):
            with self.assertRaisesRegex(RecoveryIncomplete, 'could not be verified'):
                self.stroke(panel)
        self.assertTrue(panel.editor.checkpoint_unconfirmed)
        self.assertTrue(document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        responses = self.app.main_window._impl.dialog_responses
        responses['ErrorDialog'] = [None]
        self.assertFalse(self.app.close_session(panel.session.id))
        self.run_async(asyncio.sleep(0))
        self.assertEqual(responses['ErrorDialog'], [])
        self.assertIn(panel.session.id, self.app.workspace.sessions)
        self.assertIn('Save As', panel.status.text)
        self.stroke(panel)
        self.assertFalse(panel.editor.checkpoint_unconfirmed)
        self.assertFalse(document.dirty)
        self.assertEqual(len(document.recovery.open(document.key).page(0).strokes), 2)
        self.assertTrue(self.app.close_session(panel.session.id))

    def test_discard_recovery_failure_keeps_session_and_dirty_draft(self):
        panel = self.create(private=False)
        self.stroke(panel)
        document = panel.document
        with patch.object(document.recovery, 'save', side_effect=OSError('disk busy')):
            responses = self.app.main_window._impl.dialog_responses
            responses['ErrorDialog'] = [None]
            self.assertFalse(self.app.close_session(panel.session.id, choice='discard'))
            self.run_async(asyncio.sleep(0))
            self.assertEqual(responses['ErrorDialog'], [], 'Expected close error was not presented')
        self.assertIn(panel.session.id, self.app.workspace.sessions)
        self.assertTrue(document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        self.assertEqual(len(document.recovery.open(document.key).page(0).strokes), 1)
        self.assertIn('disk busy', panel.status.text)
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))

    def test_discard_never_overwrites_an_external_source_change(self):
        panel = self.create(private=False)
        self.stroke(panel)
        source = panel.document.resource.provider.root / panel.document.resource.path
        external = Notebook.new('External version').to_bytes()
        source.write_bytes(external)
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))
        self.assertEqual(source.read_bytes(), external)
        self.assertTrue(self.run_async(open_notebook(self.app, path=source)))
        self.assertEqual(self.app.notebook_panel.editor.notebook.name, 'External version')
        self.assertFalse(self.app.notebook_panel.document.dirty)

    def test_discard_does_not_erase_another_windows_recovery_edits(self):
        from features.notebooks.editor import Editor
        panel = self.create(private=False)
        self.stroke(panel)
        document = panel.document
        other = document.recovery.open(document.key)
        Editor(other, lambda book: document.recovery.save(document.key, book)).apply(
            dict(op='rename', name='Other window draft'))
        responses = self.app.main_window._impl.dialog_responses
        responses['ErrorDialog'] = [None]
        self.assertFalse(self.app.close_session(panel.session.id, choice='discard'))
        self.run_async(asyncio.sleep(0))
        self.assertEqual(responses['ErrorDialog'], [], 'Expected close error was not presented')
        self.assertIn('another window', panel.status.text)
        self.assertEqual(document.recovery.open(document.key).name, 'Other window draft')
        self.assertTrue(document.dirty)

    def test_failed_discard_binding_keeps_draft_editable_and_retryable(self):
        panel = self.create(private=False)
        self.stroke(panel)
        document = panel.document
        with patch.object(document, 'changed', side_effect=OSError('binding busy')):
            responses = self.app.main_window._impl.dialog_responses
            responses['ErrorDialog'] = [None]
            self.assertFalse(self.app.close_session(panel.session.id, choice='discard'))
            self.run_async(asyncio.sleep(0))
            self.assertEqual(responses['ErrorDialog'], [], 'Expected close error was not presented')
        self.assertTrue(document.dirty)
        self.stroke(panel)
        self.assertEqual(len(document.recovery.open(document.key).page(0).strokes), 2)
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))

    def test_private_discard_keeps_saved_ciphertext_and_reopens_without_edits(self):
        panel = self.create()
        resource = panel.document.resource
        source = resource.provider._physical(resource.path)
        original = source.read_bytes()
        self.stroke(panel)
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))
        self.assertEqual(source.read_bytes(), original)
        reopened = DocumentResource(self.provider, resource.path, max_bytes=MAX_ARCHIVE)
        self.assertTrue(self.run_async(open_notebook(self.app, resource=reopened)))
        self.assertEqual(len(self.app.notebook_panel.editor.notebook.page(0).strokes), 0)

    def test_ordinary_save_updates_source_and_recovery_reopen_retains_binding(self):
        panel = self.create(private=False)
        self.stroke(panel)
        source = panel.document.resource.provider.root / panel.document.resource.path
        self.assertEqual(len(Notebook.read(source.read_bytes()).page(0).strokes), 0)
        self.run_async(panel.perform({'op': 'save'}))
        self.assertEqual(len(Notebook.read(source.read_bytes()).page(0).strokes), 1)
        key = panel.key
        self.assertTrue(self.app.close_session(panel.session.id))
        self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        panel = self.app.notebook_panel
        panel.web.evaluate_javascript = AsyncMock(return_value=None)
        self.stroke(panel)
        self.run_async(panel.perform({'op': 'save'}))
        self.assertEqual(len(Notebook.read(source.read_bytes()).page(0).strokes), 2)

    def test_private_save_as_to_local_requires_confirmation_and_retargets_editor(self):
        panel = self.create()
        self.stroke(panel)
        self.run_async(self.app.editor_picker().show_notebook_destination(panel))
        picker = self.app.editor_picker()
        picker.save_as_storage.value = 'Local'
        picker.save_as_name.value = 'Copy.rmdoc'
        self.run_async(picker.refresh_editor_browser())
        with patch.object(self.app.main_window, 'dialog', return_value=False):
            self.run_async(picker.confirm_editor_file())
        self.assertTrue(panel.session.transient)
        self.assertFalse((picker.editor_provider('Local').root / 'Copy.rmdoc').exists())
        with patch.object(self.app.main_window, 'dialog', return_value=True):
            self.run_async(picker.confirm_editor_file())
        self.assertFalse(panel.session.transient, picker.save_as_status.value)
        self.assertFalse(panel.document.dirty)
        self.assertEqual(panel.document.resource.path, 'Copy.rmdoc')
        panel.web.evaluate_javascript = AsyncMock(return_value=None)
        self.stroke(panel)
        self.run_async(panel.perform({'op': 'save'}))
        resource = panel.document.resource
        self.assertEqual(len(Notebook.read((resource.provider.root / resource.path).read_bytes()).page(0).strokes), 2)

    def test_private_export_cancel_preserves_canvas_and_does_not_create_recovery(self):
        panel = self.create()
        self.stroke(panel)
        with patch.object(self.app.main_window, 'dialog', return_value=False), \
                patch('commonUtils.ui.native.documents.export_stream') as export:
            self.run_async(panel.perform({'op': 'export'}))
        export.assert_not_called()
        self.assertFalse(panel.closed)
        self.assertTrue(panel.document.dirty)
        self.assertEqual(list((self.root / 'notebooks').glob('**/base.rmdoc')), [])

    def test_native_acknowledgement_failure_keeps_private_draft_without_recovery(self):
        panel = self.create()
        panel.web.evaluate_javascript.side_effect = ValueError('native view retired')
        self.run_async(panel.perform(dict(op='rename', name='Retained private draft')))
        self.assertIsNotNone(panel.document)
        self.assertTrue(panel.document.dirty)
        self.assertIsNone(panel.document.recovery)
        self.assertEqual(panel.editor.notebook.name, 'Retained private draft')
        self.assertEqual(list((self.root / 'notebooks').glob('**/base.rmdoc')), [])
        self.assertIn('draft retained', panel.status.text)

    def test_closed_notebook_rename_reopens_the_file_from_recents(self):
        from mobile.document_mutations import prepare_document_mutation
        from mobile.file_operations import FileOperationRequest, retiring_work
        from threading import Event

        panel = self.create(private=False)
        resource = panel.document.resource
        request = FileOperationRequest('rename', resource.provider, resource.path, 'Renamed.rmdoc')
        self.assertTrue(self.app.close_session(panel.session.id))

        async def rename():
            plan = await prepare_document_mutation(self.app, request)
            try:
                await retiring_work(plan.execute, Event(), completed=plan.apply)
            finally:
                plan.release()

        self.run_async(rename())
        [(session, summary)] = self.app.recent_items()
        self.assertEqual(summary[0], 'Renamed.rmdoc')
        [menu_button] = self.app.hub_controller().document_row_menu(session)
        commands = dict(menu_button.document_actions.raw_actions)
        self.assertIn('Rename…', commands)
        self.assertIn('Delete…', commands)
        self.assertTrue(self.run_async(commands['Document location']()))
        self.assertEqual(self.app.selected_file()[1], 'Renamed.rmdoc')
        self.run_async(self.app.recent_opener(session)())
        reopened = self.app.notebook_panel
        self.assertEqual(reopened.document.resource.path, 'Renamed.rmdoc')
        self.stroke(reopened)
        with patch.object(self.app, 'document_close_dialog', return_value=True) as dialog:
            self.assertTrue(self.app.request_close_session(reopened.session.id))
        dialog.assert_called_once()
        with patch.object(self.app.main_window, 'dialog', new=AsyncMock(return_value='cancel')) as confirm:
            self.assertFalse(self.run_async(reopened.delete_document()))
        self.assertEqual(confirm.call_args.args[0].title, 'Delete Renamed.rmdoc?')
        self.assertIn('Renamed.rmdoc', confirm.call_args.args[0].message)

    def test_live_notebook_rename_retains_draft_and_saves_only_to_new_name(self):
        from mobile.document_mutations import prepare_document_mutation
        from mobile.file_operations import FileOperationRequest, retiring_work
        from threading import Event
        panel = self.create()
        self.stroke(panel)
        original_resource = panel.document.resource
        request = FileOperationRequest('rename', original_resource.provider, original_resource.path, 'Moved.rmdoc')
        async def rename():
            plan = await prepare_document_mutation(self.app, request)
            try:
                await retiring_work(plan.execute, Event(), completed=plan.apply)
            finally:
                plan.release()
        self.run_async(rename())
        self.assertTrue(panel.document.dirty)
        self.assertEqual(panel.document.resource.path, 'Moved.rmdoc')
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)
        self.run_async(panel.perform(dict(op='save')))
        self.assertFalse(panel.document.dirty)
        self.assertFalse(self.provider._physical('Private sketch.rmdoc').exists())
        with self.provider.open('Moved.rmdoc') as stream:
            self.assertEqual(len(Notebook.read(stream.read()).page(0).strokes), 1)

    def test_revocation_retires_private_canvas_and_pending_save_as_material(self):
        from features.notebooks.mobile.documents import retire_stale_notebooks
        from mobile.document_sources import source_icons
        panel = self.create()
        self.assertEqual(source_icons(self.app, panel.session)[-1][0], 'storage_unlocked')
        self.stroke(panel)
        self.run_async(self.app.editor_picker().show_notebook_destination(panel))
        picker = self.app.editor_picker()
        self.assertIsNotNone(picker.save_as_data)
        self.client.generation += 1
        retire_stale_notebooks(self.app)
        self.assertTrue(panel.closed)
        self.assertIsNone(panel.editor)
        self.assertIsNone(picker.save_as_data)
        self.assertNotIn(panel.session.id, self.app.workspace.sessions)

    def test_changed_source_recovers_ordinary_draft_without_overwriting_external_edits(self):
        panel = self.create(private=False)
        self.stroke(panel)
        resource = panel.document.resource
        source = resource.provider.root / resource.path
        key = panel.key
        self.assertTrue(self.app.close_session(panel.session.id))
        source.write_bytes(Notebook.new('External version').to_bytes())
        self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        recovered = self.app.notebook_panel
        self.assertIsNone(recovered.document.resource)
        self.assertEqual(len(recovered.editor.notebook.page(0).strokes), 1)
        self.assertEqual(Notebook.read(source.read_bytes()).name, 'External version')

    def test_ordinary_to_private_save_as_changes_checkpoint_policy_and_keeps_original(self):
        panel = self.create(private=False)
        self.stroke(panel)
        source = panel.document.resource.provider.root / panel.document.resource.path
        original = source.read_bytes()
        with patch.object(self.app, 'existing_crypt_locations', return_value={'LocalCrypt: Secret': self.provider}):
            self.run_async(self.app.editor_picker().show_notebook_destination(panel))
        picker = self.app.editor_picker()
        picker.save_as_storage.value = 'LocalCrypt: Secret'
        picker.save_as_name.value = 'Encrypted.rmdoc'
        self.run_async(picker.refresh_editor_browser())
        self.run_async(picker.confirm_editor_file())
        self.assertTrue(panel.session.transient, picker.save_as_status.value)
        self.assertIsNone(panel.document.recovery)
        self.assertEqual(source.read_bytes(), original)
        self.run_async(panel.perform(dict(op='rename', name='After encryption sentinel')))
        self.assertTrue(panel.document.dirty)
        for path in (self.root / 'notebooks').glob('**/state.json'):
            self.assertNotIn('After encryption sentinel', path.read_text())

    def test_missing_source_folder_recovers_unsaved_ordinary_draft(self):
        from commonUtils.runtime.resources.local import LocalFiles
        folder = self.root / 'removable'
        folder.mkdir()
        (folder / 'Source.rmdoc').write_bytes(Notebook.new('Recoverable').to_bytes())
        resource = DocumentResource(LocalFiles(folder), 'Source.rmdoc', max_bytes=MAX_ARCHIVE)
        self.assertTrue(self.run_async(open_notebook(self.app, resource=resource)))
        panel = self.app.notebook_panel
        self.stroke(panel)
        key = panel.key
        self.assertTrue(self.app.close_session(panel.session.id))
        folder.rename(self.root / 'disconnected')
        self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        panel = self.app.notebook_panel
        self.assertIsNone(panel.document.resource)
        self.assertTrue(panel.document.dirty)
        self.assertEqual(len(panel.editor.notebook.page(0).strokes), 1)

    def test_private_canvas_resume_preserves_draft_and_undo_without_repository(self):
        panel = self.create()
        self.stroke(panel)
        editor = panel.editor
        for reopen_by_key in (True, False):
            with self.subTest(reopen_by_key=reopen_by_key):
                panel.retire_canvas()
                self.assertIsNone(panel.web)
                if reopen_by_key:
                    opened = self.run_async(open_notebook(self.app, key=panel.key))
                else:
                    resource = DocumentResource(self.provider, panel.document.resource.path, max_bytes=MAX_ARCHIVE)
                    opened = self.run_async(open_notebook(self.app, resource=resource))
                self.assertTrue(opened)
                self.assertIs(self.app.notebook_panel, panel)
                self.assertIs(panel.editor, editor)
                self.assertTrue(editor.undo)
                self.assertTrue(panel.document.dirty)
                self.assertIsNotNone(panel.web)
                self.assertIsNone(panel._repository)
        self.assertEqual(list((self.root / 'notebooks').glob('**/base.rmdoc')), [])

    def test_ordinary_retired_canvas_is_detached_even_while_its_panel_is_retained(self):
        panel = self.create(private=False)
        retired = panel.web
        self.assertIs(retired.parent, panel.view)
        panel.retire_canvas()
        self.assertIsNone(panel.web)
        self.assertIsNone(retired.parent)
        self.assertNotIn(retired, panel.view.children)
        self.assertIsNotNone(panel.editor)
        panel.mount_canvas()
        replacement = panel.web
        self.assertIsNot(replacement, retired)
        panel.dispose()
        self.assertIsNone(replacement.parent)
        self.assertNotIn(replacement, panel.view.children)

    def test_explicit_orphan_discard_removes_only_observed_draft_and_references(self):
        from mobile.resource_imports import ResourceImports
        panel = self.create(private=False)
        self.stroke(panel)
        key = panel.key
        resource = panel.document.resource
        source = resource.provider.root / resource.path
        original = source.read_bytes()
        other = panel.document.recovery.create(Notebook.new('Other draft'))
        resource.close(); panel.document.resource = None
        self.assertTrue(self.app.close_session(panel.session.id, choice='discard'))
        self.assertFalse((self.app.private_root / 'notebooks' / key).exists())
        self.assertTrue((self.app.private_root / 'notebooks' / other).exists())
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse(any(row['resource'] == key for row in self.app.recent_documents.items))
        imports = ResourceImports(self.app.private_root, collection_root=source.parent)
        self.assertFalse(any(row['resource'] == key for row in imports.items.values()))

    def test_orphan_discard_conflict_keeps_other_window_revision_and_shows_error(self):
        panel = self.create(private=False)
        self.stroke(panel)
        recovery, key = panel.document.recovery, panel.key
        newer = recovery.open(key); newer.metadata['visibleName'] = 'Newer window'
        recovery.save(key, newer)
        resource = panel.document.resource
        resource.close(); panel.document.resource = None
        with patch.object(self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.assertFalse(self.app.close_session(panel.session.id, choice='discard'))
            self.run_async(__import__('asyncio').sleep(0))
            dialog.assert_awaited_once()
        self.assertTrue(panel.document.dirty)
        self.assertEqual(recovery.open(key).name, 'Newer window')
        self.assertIn('retained', panel.status.text)

    def test_orphan_discard_io_failure_keeps_draft_and_visible_retry_error(self):
        panel = self.create(private=False); self.stroke(panel)
        resource = panel.document.resource
        resource.close(); panel.document.resource = None
        with patch.object(panel.document.recovery, 'delete', side_effect=OSError('busy')), patch.object(
                self.app.main_window, 'dialog', new_callable=AsyncMock) as dialog:
            self.assertFalse(self.app.close_session(panel.session.id, choice='discard'))
            self.run_async(__import__('asyncio').sleep(0))
            dialog.assert_awaited_once()
        self.assertTrue(panel.document.dirty)
        self.assertIn(panel.session.id, self.app.workspace.sessions)

    def test_reopening_source_reuses_existing_orphan_owner_and_undo(self):
        panel = self.create(private=False); self.stroke(panel)
        resource = panel.document.resource
        source = resource.provider.root / resource.path
        undo = list(panel.editor.undo)
        resource.close(); panel.document.resource = None
        self.assertTrue(self.run_async(open_notebook(self.app, path=source)))
        self.assertIs(self.app.notebook_panel, panel)
        self.assertEqual(panel.editor.undo, undo)
        self.assertEqual(len(self.app._notebook_views), 1)
        self.assertTrue(panel.document.dirty)

    def test_owned_ios_source_binding_rebases_without_relaxing_revision(self):
        import json
        from services.documents.mobile_storage import notebook_binding
        panel = self.create(private=False); self.stroke(panel)
        key, root = panel.key, panel.document.resource.provider.root
        binding = notebook_binding(panel.document.recovery, key)
        data = json.loads(binding.read_text())
        data['root'] = '/var/mobile/Containers/Data/Application/OLD-CONTAINER/Documents'
        binding.write_text(json.dumps(data))
        self.assertTrue(self.app.close_session(panel.session.id))
        with patch('services.documents.locations.shared_documents_path', return_value=root):
            self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        restored = self.app.notebook_panel
        self.assertIsNotNone(restored.document.resource)
        self.assertEqual(restored.document.resource.provider.root, root)
        self.assertTrue(restored.document.dirty)
        self.run_async(restored.perform({'op':'save'}))
        self.assertFalse(restored.document.dirty)

    def test_rebased_changed_source_retains_draft_and_requires_save_as(self):
        import json
        from services.documents.mobile_storage import notebook_binding
        panel = self.create(private=False); self.stroke(panel)
        key, root = panel.key, panel.document.resource.provider.root
        source = root / panel.document.resource.path
        binding = notebook_binding(panel.document.recovery, key)
        data = json.loads(binding.read_text())
        data['root'] = '/var/mobile/Containers/Data/Application/OLD-CONTAINER/Documents'
        binding.write_text(json.dumps(data))
        replacement = Notebook.new('External changed copy').to_bytes()
        source.write_bytes(replacement)
        self.assertTrue(self.app.close_session(panel.session.id))
        with patch('services.documents.locations.shared_documents_path', return_value=root):
            self.assertTrue(self.run_async(open_notebook(self.app, key=key)))
        restored = self.app.notebook_panel
        self.assertIsNone(restored.document.resource)
        self.assertTrue(restored.document.dirty)
        self.assertEqual(source.read_bytes(), replacement)
        self.assertTrue(restored.document.source_unavailable)
