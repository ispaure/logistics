"""Every supported book format reaches its reader through each storage entry point."""
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
from features.rclone.mobile.storage_location import use_shared_local, _shared_local_roots
from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.test_library_catalog import CryptClient
from mobile_build.tests.test_pdf_reader import PDF, native_pdf


class ReaderClient(CryptClient):
    def crypt_remotes(self):
        return []

    def cancel(self):
        pass

    def request(self, action, **values):
        if action == 'crypt_decode':
            return dict(name=bytes.fromhex(values['path'].rsplit('/', 1)[-1]).decode(),
                        data=base64.b64encode(os.read(values['fd'], 1024 * 1024)[::-1]).decode())
        return super().request(action, **values)


class StorageReaderOpeningTests(unittest.TestCase):
    def test_formats_open_cold_from_local_shared_local_and_localcrypt(self):
        for storage in ('local', 'shared-local', 'localcrypt'):
            for suffix in ('.epub', '.pdf', '.cbz', '.zip'):
                for entry in ('direct', 'files', 'drawer'):
                    with self.subTest(storage=storage, suffix=suffix, entry=entry):
                        self.check_open(storage, suffix, entry)

    def check_open(self, storage, suffix, entry):
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            root = Path(directory).resolve()
            private = root / 'private'
            private.mkdir()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            data = PDF if suffix == '.pdf' else (epub if suffix == '.epub' else comic).read_bytes()
            filename = 'book' + suffix
            LogisticsMobile.storage_root = private
            app = None
            try:
                if storage == 'shared-local':
                    use_shared_local(private, root / 'Documents')
                    local = root / 'Documents/Local'
                else:
                    local = private / 'LocalFiles'
                local.mkdir(parents=True, exist_ok=True)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                client = app.cloud_client = ReaderClient()
                if storage == 'localcrypt':
                    provider = CryptFiles(private / 'LocalCryptFolders', client, 'Secret')
                    provider._physical(filename).write_bytes(data[::-1])
                else:
                    provider = LocalFiles(local)
                    (local / filename).write_bytes(data)
                self.assertFalse(hasattr(app, 'cloud_view'))
                async def open_file():
                    if entry == 'direct':
                        if storage == 'localcrypt':
                            return await app.open_crypt(copies=ManagedCopies(provider), key=filename)
                        return await app.open_download(path=local / filename)
                    app.show_cloud(present=False)
                    if entry == 'files':
                        await app.show_files()
                        app.file_provider = provider
                        app.file_rows = {'book': dict(name=filename, path=filename, directory=False)}
                        app.file_selection.items = ['book']
                        app.file_selection.value = 'book'
                        return await app.read_managed_file()
                    drawer = app.adaptive.browser('documents')
                    drawer.provider = provider
                    drawer.provider_client, drawer.provider_generation = client, client.generation
                    return await drawer.open_file(dict(path=filename, directory=False))
                self.assertTrue(app.loop.run_until_complete(open_file()), getattr(app, 'cloud_status', 'No status'))
                if storage != 'localcrypt' and suffix != '.pdf':
                    reader = app.readers.active.book_reader
                    self.assertIsNotNone(reader)
                    self.assertEqual(app.readers.active.book_record['kind'], 'epub' if suffix == '.epub' else 'comic')
                else:
                    reader = app.private_sessions.active.crypt_reader
                    self.assertEqual(reader.kind, suffix)
                    if suffix == '.epub':
                        self.assertIsNotNone(reader.book)
                    elif suffix == '.pdf':
                        self.assertEqual(reader.pdf.count, 3)
                    else:
                        self.assertEqual(len(reader.labels), 2)
                expected = 'documents' if entry == 'drawer' else 'files' if entry == 'files' else 'home'
                self.assertEqual(app.native_host.state.destination, expected)
                if storage == 'localcrypt':
                    for path in private.rglob('*'):
                        if path.is_file():
                            persisted = path.read_bytes()
                            self.assertNotIn(data, persisted)
                            if suffix == '.epub':
                                self.assertNotIn(b'Native EPUB first', persisted)
                            elif suffix == '.pdf':
                                self.assertNotIn(b'mobile-private-pdf-sentinel', persisted)
            finally:
                if app is not None:
                    app.main_window.close()
                    app.loop.close()
                LogisticsMobile.storage_root = None
                _shared_local_roots.pop(private, None)

    def test_failed_local_open_does_not_report_success_or_close_drawer(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory).resolve()
            app = None
            try:
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                app.show_cloud(present=False)
                app.show_documents(destination='documents')
                drawer = app.adaptive.browser('documents')
                local = app.private_root / 'LocalFiles'
                local.mkdir(exist_ok=True)
                (local / 'broken.epub').write_bytes(b'invalid archive fixture')
                drawer.provider = LocalFiles(local)
                app.adaptive.menu_open['documents'] = True
                self.assertFalse(app.loop.run_until_complete(drawer.open_file(dict(path='broken.epub'))))
                self.assertIn('Open failed:', drawer.status.value)
                self.assertEqual(app.native_host.state.destination, 'documents')
                self.assertTrue(app.adaptive.menu_open['documents'])
            finally:
                if app is not None:
                    app.main_window.close()
                    app.loop.close()
                LogisticsMobile.storage_root = None
