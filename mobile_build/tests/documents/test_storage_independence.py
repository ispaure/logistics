"""Local documents and alternate content providers do not require rclone I/O."""
import base64
from contextlib import contextmanager
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from services.documents.mobile_reading import DocumentReadCapabilities
from services.documents.provider_documents import ProviderDocuments


class StorageIndependenceTests(unittest.TestCase):
    def test_local_import_read_and_write_succeed_when_rclone_imports_are_forbidden(self):
        script = '''
import importlib.abc, sys
class BlockRclone(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'features.rclone' or fullname.startswith('features.rclone.'):
            raise AssertionError('Ordinary document imported rclone: ' + fullname)
sys.meta_path.insert(0, BlockRclone())
from pathlib import Path
from tempfile import TemporaryDirectory
from services.documents.locations import CollectionFiles
from services.documents.mobile_storage import document_source
from mobile.local_sources import device_files
from mobile.resource_imports import ResourceImports
with TemporaryDirectory() as folder:
    root = Path(folder)
    provider = CollectionFiles(root)
    (provider.root / 'note.txt').write_bytes(b'original')
    copies, key = document_source(provider, 'note.txt')
    reader = copies.open(key)
    saved = copies.save(reader, 'updated')
    assert (provider.root / 'note.txt').read_bytes() == b'updated'
    reader.source.close()
    saved.source.close()
    device_files(root).list()
    ResourceImports(root)
'''
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, '-c', script],
            env=dict(os.environ, PYTHONPATH=str(root / 'Python')), capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_other_private_provider_opens_and_saves_with_rclone_disabled(self):
        # Base64 is deliberately only a fixture codec, not an encryption claim.
        class EncodedFixture(LocalFiles):
            private = True
            document_capabilities = DocumentReadCapabilities(True, True, False, True)

            def content_source(self, path, *, password='', cancelled=lambda: False):
                raw = self._locate(path).read_bytes()
                class Decoder:
                    data = base64.b64decode(raw)
                    @contextmanager
                    def open(self, path):
                        with BytesIO(self.data) as stream:
                            yield stream
                    def close(self):
                        self.data = b''
                return Decoder()

            @contextmanager
            def open(self, path):
                source = self.content_source(path)
                try:
                    with source.open(path) as stream:
                        yield stream
                finally:
                    source.close()

            def replace_bytes(self, path, data, *, expected_revision, cancelled):
                if self.entry(path)['revision'] != expected_revision:
                    raise ValueError('Document changed')
                stage = self._locate(path).with_name('.fixture-staged')
                stage.write_bytes(base64.b64encode(data))
                os.replace(stage, self._locate(path))

        from mobile.app import LogisticsMobile
        with TemporaryDirectory() as folder:
            root = Path(folder)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            app.set_feature_enabled('rclone', False, refresh=False)
            data = root / 'alternate'
            data.mkdir()
            path = data / 'note.txt'
            path.write_bytes(base64.b64encode(b'private original'))
            copies = ProviderDocuments(EncodedFixture(data))
            with patch.object(app, 'show_cloud', side_effect=AssertionError('Local document started Cloud')):
                self.assertTrue(app.loop.run_until_complete(app.open_crypt(copies=copies, key='note.txt')))
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_text.value, 'private original')
                owner.crypt_text.value = 'private updated'
                app.loop.run_until_complete(owner.save_crypt())
                self.assertFalse(owner.private_dirty(), owner.crypt_title.text)
            self.assertEqual(base64.b64decode(path.read_bytes()), b'private updated')
            self.assertNotIn(b'private updated', path.read_bytes())
            app.private_sessions.clear(discard=True)
