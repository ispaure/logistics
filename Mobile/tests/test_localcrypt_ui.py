"""Official Toga dummy backend: encrypted copies never enter persistent editors."""
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logisticsmobile.app import LogisticsMobile


class LocalCryptUITests(unittest.TestCase):
    def test_download_read_close_and_forget_without_plaintext_documents(self):
        class Client:
            def request(self, action, **values):
                if action == 'crypt_fetch':
                    os.write(values['fd'], b'opaque ciphertext fixture')
                    return dict(remote='Secret', encrypted_path='encoded-name', identity='a' * 64)
                if action == 'crypt_describe':
                    return 'note.md'
                if action == 'crypt_encode':
                    self.data = base64.b64decode(values['data'])
                    os.write(values['fd'], b'updated opaque ciphertext')
                    return True
                if action == 'crypt_decode':
                    return dict(name='note.md', data=base64.b64encode(getattr(self, 'data', b'# private reader sentinel')).decode())
                raise AssertionError(action)
            def crypt_remotes(self):
                return ['Secret']
            def clear(self):
                pass
            def cancel(self):
                pass
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.loop.run_until_complete(app._load_crypt_remote_names())
                app.cloud_remote.items = ['Secret']
                self.assertFalse(app.cloud_download.enabled)
                self.assertTrue(app.crypt_download.enabled)
                app.cloud_open_remote = 'Secret'
                app.cloud_rows = {'note.md': dict(path='note.md', directory=False)}
                app.cloud_entries.items = ['note.md']
                app.loop.run_until_complete(app.download_crypt())
                self.assertEqual(len(app.crypt_labels), 1)
                app.loop.run_until_complete(app.open_crypt())
                self.assertIsNotNone(app.crypt_reader, app.cloud_status.value)
                self.assertEqual(app.crypt_text.value, '# private reader sentinel')
                app.crypt_text.value = '# edited private reader sentinel'
                app.close_crypt()
                self.assertIsNotNone(app.crypt_reader)
                self.assertFalse(app.exit_app(app))
                app.loop.run_until_complete(app.clear_cloud())
                self.assertIsNotNone(app.crypt_reader)
                self.assertEqual(app.crypt_text.value, '# edited private reader sentinel')
                app.loop.run_until_complete(app.save_crypt())
                self.assertIn('Saved encrypted', app.crypt_title.text)
                self.assertFalse(app.private_dirty())
                app.close_crypt()
                self.assertIsNone(app.crypt_reader)
                self.assertEqual(app.crypt_text.value, '')
                app.loop.run_until_complete(app.open_crypt())
                app.show_cloud()
                app.loop.run_until_complete(app.clear_cloud())
                self.assertIsNone(app.crypt_reader)
                self.assertEqual(app.crypt_text.value, '')
                for file in root.rglob('*'):
                    if file.is_file():
                        self.assertNotIn(b'private reader sentinel', file.read_bytes())
                self.assertEqual(len(list((root / 'LocalCrypt').glob('*/data'))), 1)
            finally:
                app.main_window.close()
                app.loop.close()

    def test_metadata_form_retains_failed_edits_and_clears_on_close(self):
        from io import BytesIO
        from zipfile import ZipFile
        from unittest.mock import patch
        from logisticsmobile.localcrypt import PrivateReader
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
        def reader(title):
            data = BytesIO()
            with ZipFile(data, 'w') as archive:
                archive.writestr('page.png', png)
                archive.writestr('ComicInfo.xml', f'<ComicInfo><Title>{title}</Title></ComicInfo>')
            return PrivateReader('comic.cbz', data.getvalue())
        class Client:
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.cloud_client = Client()
                app.show_cloud()
                app.crypt_labels = {'comic': 'a' * 32}
                app.crypt_selector.items = ['comic']
                with patch.object(app.crypt_copies, 'open', return_value=reader('Before')):
                    app.loop.run_until_complete(app.open_crypt())
                app.edit_crypt_metadata()
                app.crypt_metadata_fields['Title'].value = 'After'
                app.close_crypt()
                self.assertIsNotNone(app.crypt_reader)
                app.edit_crypt_metadata()
                with patch.object(app.crypt_copies, 'save_metadata', side_effect=ValueError('conflict')):
                    app.loop.run_until_complete(app.save_crypt_metadata())
                self.assertEqual(app.crypt_metadata_fields['Title'].value, 'After')
                self.assertIn('edits retained', app.crypt_metadata_status.text)
                with patch.object(app.crypt_copies, 'save_metadata', return_value=reader('After')):
                    app.loop.run_until_complete(app.save_crypt_metadata())
                self.assertFalse(app.private_dirty())
                app.close_crypt()
                self.assertEqual(app.crypt_metadata_initial, {})
                self.assertEqual(app.crypt_metadata_fields, {})
                self.assertIsNone(app.crypt_metadata_view.content)
            finally:
                app.main_window.close()
                app.loop.close()
