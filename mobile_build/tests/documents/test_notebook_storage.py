"""Notebook storage parity, privacy, failure retention and destination handoff."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, AsyncMock

from mobile.app import LogisticsMobile
from features.notebooks.notebook import Notebook, MAX_ARCHIVE
from features.notebooks.mobile.documents import open_notebook
from features.rclone.localcrypt.mobile.resources import CryptFiles
from services.documents.storage import DocumentResource
from mobile_build.tests.documents.test_document_creation import CreationClient


class NotebookStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_home()
        import toga
        def canvas(resource=None, **kwargs):
            view = toga.WebView(**kwargs)
            view.evaluate_javascript = AsyncMock(return_value=None)
            return view
        factory = patch('services.documents.mobile_views.document_webview', side_effect=canvas)
        factory.start()
        self.addCleanup(factory.stop)
        self.client = CreationClient()
        self.app.cloud_client = self.client
        self.provider = CryptFiles(self.root / 'LocalCryptFolders', self.client, 'Secret')

    def tearDown(self):
        for panel in getattr(self.app, '_notebook_views', {}).values():
            panel.dispose()
        self.app.main_window.close()
        self.app.loop.run_until_complete(self.app.loop.shutdown_default_executor())
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temp.cleanup()

    def run_async(self, action):
        return self.app.loop.run_until_complete(action)

    def create(self, *, private=True):
        with patch.object(self.app, 'existing_crypt_locations', return_value={'LocalCrypt: Secret': self.provider}):
            self.app.choose_document_type()
            form = self.app.body.children[0].content
            form.name_input.value, form.type_selector.value = 'Private sketch', 'Notebook (.rmdoc)'
            self.run_async(form.create_button.on_press())
        picker = self.app.editor_picker()
        picker.save_as_storage.value = 'LocalCrypt: Secret' if private else 'Local'
        self.run_async(picker.refresh_editor_browser())
        self.run_async(picker.confirm_editor_file())
        panel = self.app.notebook_panel
        self.assertIsNotNone(panel.editor, picker.save_as_status.value)
        panel.web.evaluate_javascript = AsyncMock(return_value=None)
        return panel

    def stroke(self, panel):
        panel.editor.apply(dict(op='stroke', points=[[20,30,.4],[40,50,.8]], tool=12, width=2))

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
        picker.save_as_storage.value = 'Local files'
        picker.save_as_name.value = 'Copy.rmdoc'
        self.run_async(picker.refresh_editor_browser())
        with patch.object(self.app.main_window, 'dialog', return_value=False):
            self.run_async(picker.confirm_editor_file())
        self.assertTrue(panel.session.transient)
        self.assertFalse((picker.editor_provider('Local files').root / 'Copy.rmdoc').exists())
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
