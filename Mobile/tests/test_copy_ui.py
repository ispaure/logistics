"""Guided copy destinations, conflict preservation, retries and cancellation."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.folder_download import pull_item


class Client:
    generation = 1
    def cancel(self): pass
    def entries(self, remote, path):
        return [dict(path='album', directory=True)] if not path else [dict(path='album/note.txt', directory=False)]
    def download_into(self, remote, path, descriptor): os.write(descriptor, b'remote contents')
    def download_decrypted_into(self, remote, path, descriptor): os.write(descriptor, b'decrypted contents')


class CopyUITests(unittest.TestCase):
    def test_file_copy_destination_preserves_collision_and_opens_local_selection(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            async def check():
                app.cloud_client = Client()
                app.show_cloud()
                app.cloud_remote.items = ['remote']
                self.assertFalse(app.cloud_copy_button.enabled)
                await app.browse_cloud()
                folder = next(entry for entry in app.remote_browser.entries if entry.container)
                await app.remote_browser.buttons[folder.identity].on_press()
                self.assertEqual(app.cloud_path, 'album')
                self.assertTrue(app.cloud_copy_folder.enabled)
                self.assertFalse(app.cloud_copy_button.enabled)
                file = app.remote_browser.entries[0]
                await app.remote_browser.buttons[file.identity].on_press()
                self.assertTrue(app.cloud_copy_button.enabled)
                await app.choose_cloud_copy()
                root = app.private_root / 'LocalFiles'
                (root / 'Books').mkdir()
                (root / 'Books/note.txt').write_bytes(b'local edits')
                (root / 'not-a-folder.txt').write_bytes(b'leave alone')
                await app.copy_visit_folder(('Local files', ''))
                self.assertEqual([entry.label for entry in app.copy_browser.entries], ['Books'])
                folder = app.copy_browser.entries[0]
                await app.copy_browser.buttons[folder.identity].on_press()
                self.assertEqual(app.copy_folder, 'Books')
                self.assertTrue(await app.confirm_cloud_copy())
                copied, is_folder = app.copy_result
                self.assertFalse(is_folder)
                self.assertEqual((root / copied).read_bytes(), b'remote contents')
                self.assertEqual((root / 'Books/note.txt').read_bytes(), b'local edits')
                self.assertFalse(app.copy_confirm.enabled)
                await app.open_cloud_copy()
                self.assertEqual(app.file_path, 'Books')
                self.assertEqual(app.selected_file()[1], copied)
                await app.file_browser.close()
                await app.remote_browser.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_current_folder_copy_crypt_warning_stale_credentials_failure_and_retry(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            async def check():
                client = Client()
                app.cloud_client = client
                app.show_cloud()
                app.cloud_remote.items = ['remote']
                app.cloud_crypt_remotes = {'remote'}
                await app.browse_cloud()
                await app.browser_cloud_location(('remote', 'album'))
                await app.copy_current_folder()
                self.assertTrue(any('unencrypted' in getattr(w, 'text', '') for w in app.copy_view.children))
                client.generation += 1
                self.assertFalse(await app.confirm_cloud_copy())
                self.assertIn('Connections changed', app.copy_status.value)
                await app.copy_current_folder()
                original = client.download_decrypted_into
                def fail(*args): raise ValueError('offline')
                client.download_decrypted_into = fail
                self.assertFalse(await app.confirm_cloud_copy())
                self.assertIsNone(app.copy_result)
                self.assertEqual(list((app.private_root / 'LocalFiles').iterdir()), [])
                self.assertTrue(app.copy_confirm.enabled)
                client.download_decrypted_into = original
                self.assertTrue(await app.confirm_cloud_copy())
                await app.open_cloud_copy()
                self.assertEqual((app.private_root / 'LocalFiles' / app.file_path / 'note.txt').read_bytes(), b'decrypted contents')
                await app.file_browser.close()
                await app.remote_browser.close()
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_progress_updates_while_native_transfer_is_running(self):
        import asyncio
        import threading
        release = threading.Event()
        class Streaming(Client):
            def download_into(self, remote, path, fd):
                os.write(fd, b'12345')
                if not release.wait(3):
                    raise ValueError('Test timed out')
                os.write(fd, b'67890')
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            async def check():
                app.cloud_client = Streaming()
                app.show_cloud()
                app.cloud_remote.items = ['remote']
                app.cloud_open_remote = 'remote'
                app.cloud_rows = {'file': dict(path='note.txt', directory=False, size=10)}
                app.cloud_entries.items = ['file']
                await app.choose_cloud_copy()
                task = asyncio.create_task(app.confirm_cloud_copy())
                try:
                    for _ in range(20):
                        await asyncio.sleep(0.05)
                        if app.copy_progress.value == 50:
                            break
                    self.assertEqual(app.copy_progress.value, 50)
                    self.assertIn('5 / 10 bytes', app.copy_status.value)
                finally:
                    release.set()
                    self.assertTrue(await task)
                self.assertEqual(app.copy_progress.value, 100)
                self.assertFalse(app.copy_progress.is_running)
            try:
                app.loop.run_until_complete(check())
            finally:
                release.set()
                app.main_window.close()
                app.loop.close()

    def test_file_transfer_cancellation_generation_change_and_failure_leave_no_partial_copy(self):
        for mode in ('cancel', 'generation', 'failure'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = Path(directory) / 'files'
                root.mkdir()
                client = Client()
                cancelled = [False]
                def download(remote, path, fd):
                    os.write(fd, b'partial')
                    if mode == 'cancel': cancelled[0] = True
                    if mode == 'generation': client.generation += 1
                    if mode == 'failure': raise ValueError('offline')
                client.download_into = download
                with self.assertRaises(ValueError):
                    pull_item(client, 'remote', dict(path='note.txt', directory=False), root,
                              cancelled=lambda: cancelled[0])
                self.assertEqual(list(root.iterdir()), [])
                self.assertEqual(list(Path(directory).iterdir()), [root])
