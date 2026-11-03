"""LocalCrypt resource sessions close independently and never revive old grants."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
from features.rclone.mobile.service import native_service
from features.rclone.localcrypt.mobile.resources import encrypted_copies


class Client:
    generation = 0

    def request(self, action, **values):
        if action == 'crypt_describe':
            return 'note.txt'
        if action == 'crypt_path':
            return dict(identity='a' * 64, path=values['path'])
        if action == 'crypt_paths':
            return [item['path'] for item in values['entries']]
        if action == 'crypt_raw_read':
            return dict(data=base64.b64encode(b'fixture content').decode())
        if action == 'crypt_decode':
            return dict(name='note.txt', data=base64.b64encode(b'fixture content').decode())
        raise AssertionError(action)

    def lock(self):
        self.generation += 1


class LocalCryptAccessTests(unittest.TestCase):
    def test_note_lookup_decodes_only_candidate_paths_and_preserves_matching_rules(self):
        from features.text_editor.notes import NotesLibrary
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            for folder in ('Topics', 'Other', '.hidden', 'Topics/Nested'):
                (provider.root / folder).mkdir(parents=True)
            for name in ('Topics/Unique.md', '.hidden/Unique.md', 'Other/Unrelated.md', 'Topics/Nested/Deep.md'):
                (provider.root / name).write_bytes(b'opaque fixture')
            library = NotesLibrary(provider)
            with patch.object(provider, 'list', side_effect=AssertionError('Full folder listing')), patch.object(
                    client, 'request', wraps=client.request) as requests:
                self.assertEqual(library.link('Start.md', 'Unique#section'), ('Topics/Unique.md', 'section'))
                self.assertEqual(library.link('Start.md', 'Nested/Deep'), ('Topics/Nested/Deep.md', ''))
                decoded = [entry for call in requests.call_args_list if call.args[0] == 'crypt_paths'
                           for entry in call.kwargs['entries']]
                self.assertTrue(decoded)
                if hasattr(os, 'fwalk'):
                    self.assertTrue(all(not entry['directory'] for entry in decoded))
                    self.assertTrue(all(Path(entry['path']).name in {'Unique.md', 'Deep.md'} for entry in decoded))
                else:
                    self.assertTrue(all(entry['directory'] for entry in decoded))
            self.assertEqual(provider.find_note_paths('Unique.md', root='Other'), [])
            (provider.root / 'Other/Unique.md').write_bytes(b'opaque duplicate')
            with self.assertRaisesRegex(ValueError, 'Several notes'):
                library.link('Start.md', 'Unique')
            with self.assertRaisesRegex(ValueError, 'not found'):
                library.link('Start.md', 'Missing')
            with self.assertRaises(OperationCancelled):
                library.link('Start.md', 'Unique', cancelled=lambda: True)
            (provider.root / 'Other/Linked.md').symlink_to(provider.root / 'Topics/Unique.md')
            with self.assertRaisesRegex(ValueError, 'Linked storage'):
                library.link('Start.md', 'Unique')
            provider.close()

    def test_note_lookup_cannot_publish_after_revocation_during_decode(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            original = client.request
            def revoke(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    client.lock()
                return result
            with patch.object(client, 'request', side_effect=revoke):
                with self.assertRaises(ValueError):
                    provider.find_note_paths('Unique.md')

    def test_note_lookup_rechecks_collection_selection_before_publishing(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            provider.collection_storage_root = Path(root) / 'app'
            selected = [provider.root.parent]
            original = client.request
            def relocate(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    selected[0] = provider.root.parent / 'Changed'
                return result
            with patch('features.rclone.localcrypt.mobile.resources.collection_path', side_effect=lambda *a: selected[0]), patch.object(
                    client, 'request', side_effect=relocate):
                with self.assertRaisesRegex(ValueError, 'Collection location changed'):
                    provider.find_note_paths('Unique.md')

    def test_ciphertext_scan_falls_back_for_hidden_heavy_trees(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            hidden = provider.root / '.hidden'
            hidden.mkdir()
            for index in range(10001):
                (hidden / str(index)).touch()
            (provider.root / 'Folder').mkdir()
            (provider.root / 'Folder/Unique.md').write_bytes(b'opaque fixture')
            self.assertEqual(provider.find_note_paths('Unique.md'), ['Folder/Unique.md'])

    def test_candidate_replacement_during_decode_is_rejected(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'Folder').mkdir()
            candidate = provider.root / 'Folder/Unique.md'
            candidate.write_bytes(b'original opaque fixture')
            original = client.request
            def replace(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    candidate.write_bytes(b'replacement opaque fixture with another revision')
                return result
            with patch.object(client, 'request', side_effect=replace):
                with self.assertRaisesRegex(ValueError, 'changed during lookup'):
                    provider.find_note_paths('Unique.md')

    def test_failed_archive_construction_releases_its_native_source(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.provider_documents import ProviderDocuments
        with TemporaryDirectory() as root:
            provider = LocalFiles(root)
            Path(root, 'broken.cbz').write_bytes(b'ciphertext')
            source = SimpleNamespace(close=Mock())
            provider.content_source = Mock(return_value=source)
            with patch('services.documents.readers.PrivateReader', side_effect=ValueError('Invalid archive')):
                with self.assertRaisesRegex(ValueError, 'Invalid archive'):
                    ProviderDocuments(provider).open('broken.cbz')
            source.close.assert_called_once_with()

    def test_revocation_after_loading_releases_the_unpublished_reader(self):
        from commonUtils.runtime.resources.local import LocalFiles
        from services.documents.provider_documents import ProviderDocuments
        with TemporaryDirectory() as root:
            provider = LocalFiles(root)
            Path(root, 'note.txt').write_bytes(b'original')
            source = SimpleNamespace(close=Mock())
            provider.content_source = Mock(return_value=source)
            provider.check = Mock(side_effect=[None, ValueError('Credentials locked')])
            with self.assertRaisesRegex(ValueError, 'Credentials locked'):
                ProviderDocuments(provider).open('note.txt')
            source.close.assert_called_once_with()

    def provider(self, root, client):
        return native_service(client).localcrypt.open(LocalCryptLocation(Path(root), 'Secret'))

    def test_mobile_browser_stop_releases_only_its_own_access(self):
        from mobile.app import LogisticsMobile
        from mobile.browser_ui import FileBrowser
        with TemporaryDirectory() as root:
            LogisticsMobile.storage_root = Path(root)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            provider = self.provider(Path(root) / 'encrypted', Client())
            (provider.root / 'note.txt').write_bytes(b'ciphertext fixture')
            reader = encrypted_copies(provider)
            document = reader.open('note.txt')
            self.addCleanup(document.source.close)
            browser = FileBrowser()
            try:
                browser.set_entries(provider, '', provider.list())
                app.loop.run_until_complete(browser.close())
                self.assertTrue(provider.closed)
                self.assertEqual(document.text, 'fixture content')
                document.source.check_access()
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                app.loop.close()

    def test_browser_close_preserves_independent_reader_and_other_browser(self):
        with TemporaryDirectory() as root:
            client = Client()
            browser = self.provider(root, client)
            other = self.provider(root, client)
            (browser.root / 'note.txt').write_bytes(b'ciphertext fixture')
            reader = encrypted_copies(browser)
            document = reader.open('note.txt')
            self.addCleanup(document.source.close)
            release = browser.acquire()
            release()
            release()  # GUI close and destruction can both release their lease.
            with self.assertRaisesRegex(ValueError, 'closed'):
                browser.list()
            self.assertEqual(other.list()[0]['name'], 'note.txt')
            self.assertEqual(document.text, 'fixture content')
            document.source.check_access()
            self.assertFalse(document.source.provider.closed)

    def test_lock_and_identical_reunlock_never_revive_old_provider_or_buffer(self):
        with TemporaryDirectory() as root:
            client = Client()
            service = native_service(client)
            provider = self.provider(root, client)
            (provider.root / 'note.txt').write_bytes(b'ciphertext fixture')
            with provider.open('note.txt') as stream:
                self.assertEqual(stream.read(), b'fixture content')
                service.credentials.lock()
                with self.assertRaisesRegex(ValueError, 'locked'):
                    stream.seek(0)
                with self.assertRaises(ValueError):
                    stream.readline()
            client.generation += 1  # The same crypt key can be unlocked again.
            with self.assertRaises(ValueError):
                provider.reopen()
            self.assertEqual(self.provider(root, client).list()[0]['name'], 'note.txt')

    def test_revocation_during_listing_cannot_publish_plaintext_names(self):
        with TemporaryDirectory() as root:
            client = Client()
            provider = self.provider(root, client)
            (provider.root / 'private-name.txt').write_bytes(b'ciphertext fixture')
            original = client.request
            def request(action, **values):
                result = original(action, **values)
                if action == 'crypt_paths':
                    client.lock()
                return result
            client.request = request
            with self.assertRaisesRegex(ValueError, 'locked'):
                provider.list()

    def test_generation_change_while_opening_does_not_create_storage(self):
        with TemporaryDirectory() as root:
            client = Client()
            original = client.request
            def request(action, **values):
                result = original(action, **values)
                client.lock()
                return result
            client.request = request
            with self.assertRaises(ValueError):
                self.provider(root, client)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_native_lock_scope_is_explicit_and_saved_material_is_untouched(self):
        client = Client()
        client.vault = SimpleNamespace(forget=lambda: self.fail('Lock must not forget saved credentials'))
        service = native_service(client)
        self.assertIs(service, native_service(client))
        self.assertEqual(service.credentials.lock_scope, 'all')
        with self.assertRaisesRegex(ValueError, 'all loaded packages'):
            service.credentials.lock('Personal')
        self.assertEqual(client.generation, 0)

    def test_worker_cancellation_does_not_revoke_the_view_or_a_completed_operation(self):
        from commonUtils.runtime.operations import OperationCancelled
        with TemporaryDirectory() as root:
            provider = self.provider(root, Client())
            cancelled = [False]
            with provider.operation(lambda: cancelled[0]):
                self.assertEqual(provider.list(), [])
                cancelled[0] = True  # Publication/operation already completed.
            self.assertFalse(provider.closed)
            with self.assertRaises(OperationCancelled), provider.operation(lambda: True):
                self.fail('Cancelled work was admitted')
            self.assertEqual(provider.list(), [])

    def test_offline_reader_cannot_save_after_lock_and_identical_reunlock(self):
        from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
        with TemporaryDirectory() as root:
            client = Client()
            copies = LocalCryptCopies(Path(root), client)
            key = 'b' * 32
            folder = Path(root) / key
            folder.mkdir()
            (folder / 'data').write_bytes(b'ciphertext fixture')
            (folder / 'record.json').write_text(json.dumps(dict(
                remote='Secret', encrypted_path='encoded-name', identity='a' * 64)))
            reader = copies.open(key)
            client.lock()
            client.generation += 1
            with self.assertRaisesRegex(ValueError, 'locked'):
                copies.save(reader, 'old reader must not publish')
            self.assertEqual((folder / 'data').read_bytes(), b'ciphertext fixture')
            self.assertEqual(copies.open(key).text, 'fixture content')
