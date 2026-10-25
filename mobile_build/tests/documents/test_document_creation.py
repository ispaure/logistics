"""User-created documents publish into browsable local or encrypted folders."""
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
        if action == 'crypt_encode':
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

    def choose(self, name, kind='Plain text (.txt)'):
        self.app.choose_document_type()
        form = self.app.body.children[0].content
        form.name_input.value, form.type_selector.value = name, kind
        self.app.loop.run_until_complete(form.create_button.on_press())
        return form, self.app.editor_picker()

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
        self.assertIs(app.body.children[0].content, form)
        form.cancel_button.on_press()
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

    def test_empty_unlocked_localcrypt_root_is_offered(self):
        app = self.app
        app.cloud_client = CreationClient()
        app.cloud_crypt_remotes = {'Secret'}
        _, picker = self.choose('First encrypted file')
        self.assertIn('LocalCrypt: Secret', picker.editor_storage_roots)
        picker.save_as_storage.value = 'LocalCrypt: Secret'
        app.loop.run_until_complete(picker.refresh_editor_browser())
        app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIsNotNone(app.private_sessions.active, picker.save_as_status.value)
        self.assertTrue(app.private_sessions.active._crypt_reader_store.provider.private)

    def test_session_capacity_rejects_creation_before_publishing(self):
        _, picker = self.choose('No capacity')
        with patch('mobile.workspace.MAX_SESSIONS', 0):
            self.app.loop.run_until_complete(picker.confirm_editor_file())
        self.assertIn('Close an open document', picker.save_as_status.value)
        self.assertFalse((self.root / 'LocalFiles/No capacity.txt').exists())
