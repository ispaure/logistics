"""User-created documents publish into browsable local or encrypted folders."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.SMOKE
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mobile.app import LogisticsMobile
from mobile.local_sources import device_files
from mobile_build.tests.storage.test_storage_reader_opening import ReaderClient


class CreationClient(ReaderClient):
    def request(self, action, **values):
        if action in {'crypt_encode', 'crypt_write_buffer'}:
            data = base64.b64decode(values['data'])
            os.write(values['fd'], b'cipher:' + data[::-1])
            return {}
        if action == 'crypt_decode':
            data = os.read(values['fd'], 1024 * 1024)
            return dict(name=bytes.fromhex(values['path'].rsplit('/', 1)[-1]).decode(),
                        data=base64.b64encode(data.removeprefix(b'cipher:')[::-1]).decode())
        if action == 'crypt_raw_read':
            data = os.read(values['fd'], 1024 * 1024)
            return dict(data=base64.b64encode(data.removeprefix(b'cipher:')[::-1]).decode())
        return super().request(action, **values)


class DocumentCreationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        LogisticsMobile.storage_root = self.root
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.app.show_home()

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.run_until_complete(self.app.loop.shutdown_default_executor())
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.directory.cleanup()

    def choose(self, name, kind='Plain text (.txt)', *, local=True):
        self.app.loop.run_until_complete(self.app.choose_document_type())
        picker = self.app.editor_picker()
        form = picker.panel
        picker.save_as_name.value, picker.creation_type.value = name, kind
        if local:
            row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Local')
            self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        return form, picker

    def test_name_type_and_folder_share_one_route_until_publication(self):
        from features.notebooks.notebook import Notebook
        app = self.app
        origin = app.body
        _, picker = self.choose('Trip.txt')
        panel, location = picker.panel, picker.editor_picker_location
        self.assertTrue(picker.visible())
        self.assertIn(picker.creation_type, picker.save_as_view.children)
        self.assertFalse((self.root / 'LocalFiles/Trip.txt').exists())
        picker.creation_type.value = 'Markdown (.md)'
        self.assertEqual(picker.save_as_name.value, 'Trip.md')
        picker.creation_type.value = 'Notebook (.rmdoc)'
        self.assertEqual(picker.save_as_name.value, 'Trip.rmdoc')
        self.assertIs(picker.panel, panel)
        self.assertEqual(picker.editor_picker_location, location)
        picker.save_as_name.value = 'Final title'
        app.loop.run_until_complete(picker.confirm_editor_file())
        path = self.root / 'LocalFiles/Final title.rmdoc'
        self.assertEqual(Notebook.read(path.read_bytes()).name, 'Final title')
        self.assertFalse((self.root / 'LocalFiles/Trip.rmdoc').exists())
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])
        self.assertIsNot(app.body, origin)

    def test_received_files_notebook_creation_on_android_without_exclusive_rename(self):
        import errno
        from commonUtils.runtime.platform import OS
        from features.notebooks.notebook import Notebook
        from mobile.incoming_files import inbox_path
        _, picker = self.choose('Received sketch', 'Notebook (.rmdoc)', local=False)
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Received Files')
        self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        with patch('commonUtils.runtime.resources.local.rename_exclusive',
                   side_effect=OSError(errno.EINVAL, 'SD card rejects rename flags')), \
                patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID):
            self.app.loop.run_until_complete(picker.confirm_editor_file())
        received = inbox_path(self.root)
        path = received / 'Received sketch.rmdoc'
        self.assertTrue(path.is_file(), picker.save_as_status.value)
        self.assertEqual(Notebook.read(path.read_bytes()).name, 'Received sketch')
        self.assertIsNotNone(self.app.notebook_panel)
        self.assertEqual(sorted(p.name for p in received.iterdir()), ['Received sketch.rmdoc'])

    def test_sd_received_notebook_creation_and_workspace_reopen(self):
        import json
        from features.notebooks.mobile.documents import panels
        external = TemporaryDirectory()
        self.addCleanup(external.cleanup)
        volume = Path(external.name).resolve()
        base = volume / 'Logistics'
        base.mkdir()
        token = 'a' * 32
        (base / '.logistics-storage').write_text(token)
        (self.root / 'collection-storage.json').write_text(json.dumps(dict(volume=str(volume), token=token)))
        _, picker = self.choose('SD notebook', 'Notebook (.rmdoc)', local=False)
        row = next(row for row in picker.editor_picker_rows.values() if row['name'] == 'Received Files')
        self.app.loop.run_until_complete(picker.browser_editor_folder(row))
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        panel = self.app.notebook_panel
        self.assertTrue(panels(self.app), picker.save_as_status.value)
        self.assertEqual(panel.document.resource.provider.root, base / 'Received Files')
        session = panel.session
        self.assertTrue(self.app.close_session(session.id))
        self.app.loop.run_until_complete(self.app.open_download(path=base / 'Received Files/SD notebook.rmdoc'))
        self.assertIn(self.app.notebook_panel.session.id, panels(self.app))
        self.assertEqual(self.app.notebook_panel.session.resource, session.resource)

    def test_cold_start_client_and_credentials_changes_do_not_leave_loading_form(self):
        import asyncio
        from types import SimpleNamespace
        app = self.app
        original = asyncio.to_thread
        calls = []
        async def restoring(*args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1:
                app.cloud_client = SimpleNamespace(generation=0, cancel=lambda: None)
            elif len(calls) == 2:
                app.cloud_client.generation = 1
            return await original(*args, **kwargs)
        with patch('mobile.editor_picker.asyncio.to_thread', side_effect=restoring):
            app.loop.run_until_complete(app.choose_document_type())
        picker = app.editor_picker()
        self.assertEqual(picker.editor_picker_location, ('All files', ''))
        self.assertIn('Local', [row['name'] for row in picker.editor_picker_rows.values()])
        self.assertFalse(app.cloud_busy)
        self.assertNotEqual(picker.save_as_status.value, 'Loading folder…')

    def test_creation_keyboard_compaction_keeps_name_type_and_destination(self):
        _, picker = self.choose('Keep my name', 'Notebook (.rmdoc)')
        name, kind = picker.save_as_name, picker.creation_type
        location = picker.editor_picker_location
        picker.fit_keyboard(True)
        self.assertIn(kind, picker.save_as_view.children)
        self.assertIn(name, picker.save_as_view.children)
        self.assertEqual(name.value, 'Keep my name')
        picker.fit_keyboard(False)
        self.assertEqual(picker.editor_picker_location, location)
        self.assertEqual(kind.value, 'Notebook (.rmdoc)')

    def test_creation_starts_at_browse_all_files_and_can_return_from_collections(self):
        _, picker = self.choose('Anywhere', local=False)
        self.assertEqual(picker.editor_picker_location, ('All files', ''))
        self.assertEqual(picker.editor_provider('All files').root, device_files(self.root).root)
        self.assertFalse(picker.picker_primary.enabled)
        self.assertFalse(picker.picker_new_folder.enabled)
        self.assertEqual(picker.picker_primary.text, 'Create document')
        self.assertIn('Choose a folder below', picker.save_as_status.value)
        for name in ('Local', 'Received Files'):
            row = next(row for row in picker.editor_picker_rows.values() if row['name'] == name)
            self.app.loop.run_until_complete(picker.browser_editor_folder(row))
            self.assertEqual(picker.editor_picker_location, (name, ''))
            self.assertTrue(picker.picker_primary.enabled)
            self.assertTrue(picker.picker_parent.enabled)
            self.app.loop.run_until_complete(picker.parent_editor_folder())
            self.assertEqual(picker.editor_picker_location, ('All files', ''))

    def test_ios_shared_root_and_collection_destinations_publish_documents(self):
        from services.documents.locations import use_shared_local, _shared_local_roots
        from mobile.incoming_files import inbox_path
        shared_directory = TemporaryDirectory()
        self.addCleanup(shared_directory.cleanup)
        shared = Path(shared_directory.name)
        use_shared_local(self.root, shared)
        self.addCleanup(_shared_local_roots.pop, self.root)
        (shared / 'Notes').mkdir()
        for label, folder, target in (
                ('All files', 'Notes', shared / 'Notes/Public.md'),
                ('Local', '', shared / 'Local/Public.md'),
                ('Received Files', '', inbox_path(self.root) / 'Public.md')):
            with self.subTest(label=label):
                _, picker = self.choose('Public', 'Markdown (.md)', local=False)
                path = folder if label == 'All files' else picker.editor_provider(label).root.name
                self.app.loop.run_until_complete(picker.browser_editor_location(('All files', path)))
                self.assertEqual(picker.editor_picker_location, (label, folder))
                self.app.loop.run_until_complete(picker.confirm_editor_file())
                self.assertTrue(target.is_file(), picker.save_as_status.value)

    def test_notebook_name_preview_listing_validation_and_retry_use_notebook_format(self):
        from features.notebooks.notebook import Notebook
        local = self.root / 'LocalFiles'
        local.mkdir(exist_ok=True)
        (local / 'Existing.rmdoc').write_bytes(Notebook.new('Existing').to_bytes())
        (local / 'Text.txt').write_text('other format')
        _, picker = self.choose('Sketch', 'Notebook (.rmdoc)')
        self.assertEqual(picker.effective_name.text, 'Save as: Sketch.rmdoc')
        self.assertIn('Existing.rmdoc', [row['name'] for row in picker.editor_picker_rows.values()])
        self.assertIn('Text.txt', [row['name'] for row in picker.editor_picker_rows.values()])
        picker.save_as_name.value = 'Invalid.txt'
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('Creation failed:', picker.save_as_status.value)
        self.assertIsInstance(picker.save_as_status.label, __import__('toga').Label)
        self.assertTrue(picker.save_as_status.children)
        self.assertFalse((local / 'Invalid.txt').exists())
        picker.save_as_name.value = 'Renamed'
        self.assertEqual(picker.effective_name.text, 'Save as: Renamed.rmdoc')
        picker.new_folder_name.value = 'Test'
        self.app.loop.run_until_complete(picker.create_picker_folder())
        self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertTrue((local / 'Test/Renamed.rmdoc').is_file(), picker.save_as_status.value)
        self.assertIsNotNone(self.app.notebook_panel)

    def test_local_document_is_in_all_files_and_saves_to_the_chosen_folder(self):
        app = self.app
        (self.root / 'LocalFiles/Notes').mkdir(parents=True)
        before = app.store.documents()
        _, picker = self.choose('First note', 'Markdown (.md)')
        self.assertNotIn('Cloud', picker.editor_storage_roots)
        self.assertEqual(set(picker.editor_storage_roots), {'Local', 'All files', 'Received Files'})
        self.assertEqual(app.store.documents(), before)
        picker.picker_folder.value = 'Notes'
        app.loop.run_until_complete(picker.refresh_editor_browser())
        app.loop.run_until_complete(picker.confirm_editor_file())
        owner = app.private_sessions.active
        self.assertIsNotNone(owner)
        self.assertEqual(owner.crypt_reader.name, 'First note.md')
        self.assertEqual((self.root / 'LocalFiles/Notes/First note.md').read_bytes(), b'')
        owner.crypt_text.value = '# Saved in my folder'
        app.loop.run_until_complete(owner.save_crypt())
        self.assertEqual((self.root / 'LocalFiles/Notes/First note.md').read_text(), '# Saved in my folder')
        self.assertIn('First note.md', [row['name'] for row in device_files(self.root).list('LocalFiles/Notes')])
        self.assertEqual(app.store.documents(), before)
        self.assertNotIn('new-document', [row[0] for row in app.routes.screens['home']])
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])

    def test_cancel_and_duplicate_name_leave_existing_files_and_private_store_unchanged(self):
        app = self.app
        before = app.store.documents()
        original = self.root / 'LocalFiles/Keep.txt'
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(b'keep')
        form, picker = self.choose('Keep')
        app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertEqual(original.read_bytes(), b'keep')
        self.assertIn('already exists', picker.save_as_status.value)
        self.assertIsNone(app.provider_sessions().active)
        picker.cancel_text_destination()
        self.assertIsNot(app.body, form)
        self.assertEqual(app.store.documents(), before)

    def test_localcrypt_creation_and_editing_use_encrypted_provider_without_managed_plaintext(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        app = self.app
        app.cloud_client = client = CreationClient()
        provider = CryptFiles(self.root / 'LocalCryptFolders', client, 'Secret')
        before = app.store.documents()
        with patch.object(app, 'existing_crypt_locations', return_value={'LocalCrypt: Secret': provider}):
            _, picker = self.choose('Private note', 'Markdown (.md)')
        picker.save_as_storage.value = 'LocalCrypt: Secret'
        app.loop.run_until_complete(picker.refresh_editor_browser())
        app.loop.run_until_complete(picker.confirm_editor_file())
        owner = app.private_sessions.active
        self.assertIsNotNone(owner, picker.save_as_status.value)
        self.assertTrue(owner._crypt_reader_store.provider.private)
        self.assertEqual(provider._physical('Private note.md').read_bytes(), b'cipher:')
        owner.crypt_text.value = '# Secret draft'
        app.loop.run_until_complete(owner.save_crypt())
        raw = provider._physical('Private note.md').read_bytes()
        self.assertEqual(raw, b'cipher:' + b'# Secret draft'[::-1])
        self.assertNotIn(b'# Secret draft', raw)
        self.assertEqual(app.store.documents(), before)
        self.assertFalse((self.root / 'LocalFiles/Private note.md').exists())

    def test_remote_provider_cannot_be_used_for_creation(self):
        app = self.app
        _, picker = self.choose('Read only')
        provider = picker.editor_provider('Local')
        provider.remote_storage = True
        with patch.object(picker, 'editor_provider', return_value=provider):
            app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('read-only', picker.save_as_status.value)
        self.assertFalse((self.root / 'LocalFiles/Read only.txt').exists())

    def test_uncreated_localcrypt_roots_are_not_offered(self):
        app = self.app
        app.cloud_client = CreationClient()
        app.cloud_crypt_remotes = {'Secret'}
        _, picker = self.choose('First encrypted file')
        self.assertNotIn('LocalCrypt: Secret', picker.editor_storage_roots)
        self.assertFalse(picker.save_as_status.children)

    def test_session_capacity_rejects_creation_before_publishing(self):
        _, picker = self.choose('No capacity')
        with patch('mobile.workspace.MAX_SESSIONS', 0):
            self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('Close an open document', picker.save_as_status.value)
        self.assertFalse((self.root / 'LocalFiles/No capacity.txt').exists())

    def test_notebook_creation_opens_in_shared_documents_and_recovers_ink(self):
        from features.notebooks.notebook import Notebook
        from features.notebooks.mobile.documents import open_notebook
        app = self.app
        _, picker = self.choose('Sketches', 'Notebook (.rmdoc)')
        app.loop.run_until_complete(picker.confirm_editor_file())
        panel = getattr(app, 'notebook_panel', None)
        self.assertIsNotNone(panel, picker.save_as_status.value)
        self.assertEqual(panel.editor.notebook.name, 'Sketches')
        self.assertEqual(app.native_host.state.destination, 'home')
        source = self.root / 'LocalFiles/Sketches.rmdoc'
        self.assertEqual(Notebook.read(source.read_bytes()).name, 'Sketches')
        panel.editor.apply(dict(op='stroke', points=[[20,30,.4],[40,50,.8]], tool=12, width=2))
        key, session_id = panel.key, panel.session.id
        self.assertTrue(app.close_session(session_id))
        self.assertNotIn(session_id, app.workspace.sessions)
        self.assertTrue(app.loop.run_until_complete(open_notebook(app, path=source)))
        self.assertEqual(app.notebook_panel.key, key)
        self.assertEqual(len(app.notebook_panel.editor.notebook.page(0).strokes), 1)
        self.assertNotIn('new-document', [row[0] for row in app.routes.screens['home']])
        self.assertNotIn('text-destination', [row[0] for row in app.routes.screens['home']])

    def test_multiple_notebooks_keep_independent_editors_and_reopen_from_documents(self):
        from features.notebooks.mobile.documents import open_notebook
        app = self.app
        app.loop.run_until_complete(open_notebook(app, name='First'))
        first = app.notebook_panel
        app.loop.run_until_complete(open_notebook(app, name='Second'))
        second = app.notebook_panel
        self.assertIsNot(first, second)
        self.assertEqual(len(app._notebook_views), 2)
        self.assertTrue(app.loop.run_until_complete(open_notebook(app, key=first.key)))
        self.assertEqual(app.workspace.active, first.session.id)
        self.assertEqual(second.editor.notebook.name, 'Second')
