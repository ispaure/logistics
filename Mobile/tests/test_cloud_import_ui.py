"""Exercise choose/password/load, retries and bounded picker access."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.cloud_ui import SelectedCredentialZIP


class CredentialImportUITests(unittest.TestCase):
    def test_explicit_decrypted_download_and_failed_partial_copy_cleanup(self):
        import os
        class Client:
            fail = False
            def crypt_remotes(self): return ['Secret']
            def cancel(self): pass
            def download_into(self, *args): raise AssertionError('Ordinary read used for crypt')
            def download_decrypted_into(self, remote, path, descriptor):
                self.requested = (remote, path)
                os.write(descriptor, b'decrypted fixture contents')
                if self.fail: raise ValueError('Synthetic authentication failure')
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.loop.run_until_complete(app._load_crypt_remote_names())
                app.cloud_remote.items = ['Secret']
                app.cloud_open_remote = 'Secret'
                app.cloud_rows = {'file': {'path': 'folder/note.txt', 'directory': False}}
                app.cloud_entries.items = ['file']
                self.assertTrue(app.cloud_download.enabled)
                self.assertTrue(app.crypt_download.enabled)
                self.assertIn('saved unencrypted', app.cloud_download_help.text.replace('\n', ' '))
                app.loop.run_until_complete(app.download_cloud())
                self.assertEqual(app.cloud_client.requested, ('Secret', 'folder/note.txt'))
                self.assertEqual(app.downloads.items()[0].read_bytes(), b'decrypted fixture contents')
                self.assertTrue(app.download_export.enabled)
                self.assertIn('unencrypted', app.cloud_status.value)
                self.assertEqual(app.crypt_labels, {})
                app.cloud_client.fail = True
                app.loop.run_until_complete(app.download_cloud())
                self.assertEqual(len(app.downloads.items()), 1)
                self.assertEqual(len(list(app.downloads.root.iterdir())), 1)
                self.assertIn('Download failed', app.cloud_status.value)
            finally:
                app.main_window.close()
                app.loop.close()
    def test_remote_selector_explains_available_crypts_and_selected_kind(self):
        class Client:
            def crypt_remotes(self): return ['Private', 'Books']
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.loop.run_until_complete(app._load_crypt_remote_names())
                app.cloud_remote.items = ['Dropbox', 'Private', 'Books']
                self.assertIn('Crypt remotes: Books, Private', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertIn('tap the name', app.cloud_remote_heading.text)
                app.cloud_remote.value = 'Private'
                self.assertIn('Crypt remote selected: Private', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertIn('decrypted filenames', app.cloud_remote_help.text.replace('\n', ' '))
                self.assertTrue(app.crypt_download.enabled)
                self.assertTrue(app.cloud_download.enabled)
                self.assertEqual(app.cloud_download.text, 'Download decrypted')
                app.cloud_crypt_remotes = set()
                app.cloud_remote.value = 'Dropbox'
                self.assertIn('No crypt remote', app.cloud_remote_help.text)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_zip_is_selected_before_password_and_failed_load_can_retry_without_picker(self):
        class Client:
            def __init__(self): self.calls = []
            def import_package(self, access, reference, password, *, remember=True):
                with access.open(reference) as (name, stream):
                    self.calls.append((name, stream.read(), password, remember))
                if password != 'correct': raise ValueError('Incorrect ZIP password')
                self.package_name = name
                return ['Example']
            def cancel(self): pass
            def clear(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                self.assertFalse(app.cloud_import.enabled)
                with patch('logisticsmobile.pickers.pick_document', new=AsyncMock()) as no_picker:
                    app.loop.run_until_complete(app.import_cloud_package(app.cloud_password))
                    no_picker.assert_not_awaited()
                source = Path(directory) / 'example.zip'
                source.write_bytes(b'encrypted fixture bytes')
                picker = AsyncMock(return_value=(LocalDocuments(), source))
                with patch('logisticsmobile.pickers.pick_document', new=picker):
                    app.loop.run_until_complete(app.choose_cloud_package())
                    self.assertEqual(app.cloud_client.calls, [])
                    self.assertIn('example.zip', app.cloud_selected_zip.text)
                    self.assertTrue(app.cloud_import.enabled)
                    source.unlink()  # Picker access was consumed and closed.
                    app.cloud_password.value = 'wrong'
                    app.loop.run_until_complete(app.import_cloud_package())
                    self.assertEqual(app.cloud_password.value, '')
                    self.assertTrue(app.cloud_import.enabled)
                    self.assertIn('tap Load remotes again', app.cloud_import_message.text.replace('\n', ' '))
                    app.cloud_password.value = 'correct'
                    app.loop.run_until_complete(app.import_cloud_package())
                    self.assertEqual(picker.await_count, 1)
                self.assertEqual(app.cloud_remote.value, 'Example')
                self.assertIsNone(app.cloud_pending_zip)
                self.assertFalse(app.cloud_import.enabled)
                self.assertIn('Browse folder', app.cloud_import_message.text.replace('\n', ' '))
                self.assertEqual(app.cloud_password.value, '')
            finally:
                app.main_window.close()
                app.loop.close()

    def test_cancelling_selection_keeps_loaded_remotes(self):
        class Client:
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.cloud_remote.items = ['Existing']
                with patch('logisticsmobile.pickers.pick_document', new=AsyncMock(return_value=None)):
                    app.loop.run_until_complete(app.choose_cloud_package())
                self.assertEqual(app.cloud_remote.value, 'Existing')
                self.assertFalse(app.cloud_import.enabled)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_oversized_zip_is_rejected_before_loading(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'oversized.zip'
            source.write_bytes(b'X' * (1024 * 1024 + 1))
            with self.assertRaises(ValueError):
                SelectedCredentialZIP(LocalDocuments(), source)
