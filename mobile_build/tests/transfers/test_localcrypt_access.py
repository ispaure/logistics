"""LocalCrypt resource sessions close independently and never revive old grants."""
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from features.rclone.mobile.service import LocalCryptLocation, native_service
from features.rclone.localcrypt.mobile.resources import encrypted_copies


class Client:
    generation = 0

    def request(self, action, **values):
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
            browser = FileBrowser()
            try:
                browser.set_entries(provider, '', provider.list())
                app.loop.run_until_complete(browser.close())
                self.assertTrue(provider.closed)
                self.assertEqual(reader.record('note.txt')['remote'], 'Secret')
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
            release = browser.acquire()
            release()
            release()  # GUI close and destruction can both release their lease.
            with self.assertRaisesRegex(ValueError, 'closed'):
                browser.list()
            self.assertEqual(other.list()[0]['name'], 'note.txt')
            self.assertEqual(reader.record('note.txt')['remote'], 'Secret')
            self.assertFalse(reader.provider.closed)

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
