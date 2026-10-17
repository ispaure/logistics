"""Official Toga dummy backend: encrypted copies never enter persistent editors."""
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from logisticsmobile.app import LogisticsMobile


def seed_offline_copy(copies, data=b'opaque-original'):
    """Seed a pre-existing offline record without a remote download API."""
    import json
    from uuid import uuid4
    key = uuid4().hex
    folder = copies.root / key
    folder.mkdir()
    (folder / 'data').write_bytes(data)
    (folder / 'record.json').write_text(json.dumps(dict(
        remote='Secret', encrypted_path='encoded', identity='a' * 64)))
    return key


class LocalCryptUITests(unittest.TestCase):
    def test_ini_opens_edits_and_saves_without_plaintext_history(self):
        class Client:
            generation = 0
            data = b'[Settings]\r\nvalue=private-ini-sentinel\r\n'
            def request(self, action, **values):
                if action == 'crypt_decode':
                    return dict(name='settings.ini', data=base64.b64encode(self.data).decode())
                if action == 'crypt_encode':
                    self.data = base64.b64decode(values['data'])
                    os.write(values['fd'], b'new opaque ini ciphertext')
                    return True
                raise AssertionError(action)
            def crypt_remotes(self): return []
            def cancel(self): pass
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.cloud_client = Client()
            app.show_cloud(present=False)
            key = seed_offline_copy(app.crypt_copies)
            self.assertTrue(app.loop.run_until_complete(app.open_crypt(copies=app.crypt_copies, key=key)), app.cloud_status.value)
            owner = app.private_sessions.active
            self.assertIn('value=private-ini-sentinel', owner.crypt_text.value)
            owner.crypt_text.value = '[Settings]\nvalue=edited-private-ini-sentinel\n'
            app.loop.run_until_complete(owner.save_crypt())
            self.assertFalse(owner.private_dirty(), owner.crypt_title.text)
            self.assertEqual(app.cloud_client.data, b'[Settings]\r\nvalue=edited-private-ini-sentinel\r\n')
            # Another native client/scene replacing credentials must also retire
            # already displayed plaintext, not merely reject future range reads.
            app.cloud_client.generation += 1
            app.screen_privacy.retire_stale()
            self.assertEqual(owner.crypt_text.value, '')
            self.assertIsNone(owner.crypt_reader)
            self.assertFalse(app.private_sessions.controllers)
            app.close_crypt()
            for path in root.rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'private-ini-sentinel', path.read_bytes())

    def test_existing_offline_copy_read_close_and_forget_without_plaintext_documents(self):
        class Client:
            def request(self, action, **values):
                if action == 'crypt_path':
                    return dict(identity='b' * 64, path=values.get('path', ''))
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
                app.cloud_open_remote = 'Secret'
                app.cloud_rows = {'note.md': dict(path='note.md', directory=False)}
                app.cloud_entries.items = ['note.md']
                key = seed_offline_copy(app.crypt_copies)
                app.loop.run_until_complete(app.refresh_crypt())
                app.crypt_selector.value = next(label for label, value in app.crypt_labels.items() if value == key)
                self.assertEqual(len(app.crypt_labels), 1)
                app.loop.run_until_complete(app.open_crypt())
                owner = app.provider_sessions().active
                self.assertIsNotNone(owner, app.cloud_status.value)
                self.assertIsNotNone(owner.crypt_reader)
                self.assertEqual(owner.crypt_text.value, '# private reader sentinel')
                owner.crypt_text.value = '# edited private reader sentinel'
                app.close_crypt()
                self.assertIsNotNone(owner.crypt_reader)
                self.assertFalse(app.exit_app(app))
                app.loop.run_until_complete(app.clear_cloud())
                self.assertIsNotNone(owner.crypt_reader)
                self.assertEqual(owner.crypt_text.value, '# edited private reader sentinel')
                app.loop.run_until_complete(app.save_crypt())
                self.assertIn('Saved encrypted', owner.crypt_title.text)
                self.assertFalse(app.private_dirty())
                app.close_crypt()
                self.assertIsNone(app.provider_sessions().active)
                self.assertIsNone(owner.crypt_reader)
                self.assertEqual(owner.crypt_text.value, '')
                app.loop.run_until_complete(app.open_crypt())
                owner = app.provider_sessions().active
                app.show_cloud()
                app.loop.run_until_complete(app.clear_cloud())
                self.assertIsNone(app.provider_sessions().active)
                self.assertEqual(owner.crypt_text.value, '')
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
        from services.document_readers import PrivateReader
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
                owner = app.provider_sessions().active
                app.edit_crypt_metadata()
                owner.crypt_metadata_fields['Title'].value = 'After'
                app.close_crypt()
                self.assertIsNotNone(owner.crypt_reader)
                app.edit_crypt_metadata()
                with patch.object(app.crypt_copies, 'save_metadata', side_effect=ValueError('conflict')):
                    app.loop.run_until_complete(app.save_crypt_metadata())
                self.assertEqual(owner.crypt_metadata_fields['Title'].value, 'After')
                self.assertIn('edits retained', owner.crypt_metadata_status.text)
                with patch.object(app.crypt_copies, 'save_metadata', return_value=reader('After')):
                    app.loop.run_until_complete(app.save_crypt_metadata())
                self.assertFalse(app.private_dirty())
                app.close_crypt()
                self.assertEqual(owner.crypt_metadata_initial, {})
                self.assertEqual(owner.crypt_metadata_fields, {})
                self.assertIsNone(owner.crypt_metadata_view.content)
            finally:
                app.main_window.close()
                app.loop.close()
