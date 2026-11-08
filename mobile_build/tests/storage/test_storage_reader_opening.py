"""Every supported book format reaches its reader through each storage entry point."""

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
from services.documents.locations import use_shared_local, _shared_local_roots
from mobile.app import LogisticsMobile
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.support.localcrypt import ReaderClient
from mobile_build.tests.support.pdf import PDF, native_pdf


class StorageReaderOpeningTests(unittest.TestCase):
    def test_formats_open_cold_from_local_shared_local_and_localcrypt(self):
        for storage in ('local', 'shared-local', 'localcrypt'):
            for suffix in ('.epub', '.pdf', '.cbz', '.zip'):
                for entry in ('direct', 'files', 'drawer'):
                    with self.subTest(storage=storage, suffix=suffix, entry=entry):
                        self.check_open(storage, suffix, entry)

    def test_localcrypt_formats_keep_nested_source_paths(self):
        for suffix in ('.epub', '.pdf', '.cbz', '.zip'):
            with self.subTest(suffix=suffix):
                self.check_open('localcrypt', suffix, 'direct', nested=True)

    def test_shared_local_epub_shows_workspaces_breadcrumb(self):
        self.check_open('shared-local', '.epub', 'direct', nested=True)

    def check_open(self, storage, suffix, entry, *, nested=False):
        with TemporaryDirectory() as directory, patch('features.pdf.document.PDFDocument.open', native_pdf):
            root = Path(directory).resolve()
            private = root / 'private'
            private.mkdir()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, comic = make_books(fixtures)
            data = PDF if suffix == '.pdf' else (epub if suffix == '.epub' else comic).read_bytes()
            filename = ('Shelf/book' if nested else 'book') + suffix
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
                    provider._physical(filename).parent.mkdir(parents=True, exist_ok=True)
                    provider._physical(filename).write_bytes(data[::-1])
                else:
                    provider = LocalFiles(local)
                    (local / filename).parent.mkdir(parents=True, exist_ok=True)
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
                owner = app.private_sessions.active
                reader = owner.crypt_reader
                if storage != 'localcrypt':
                    expected_path = ' → '.join(('Workspaces', 'Local', *Path(filename).parts))
                    self.assertEqual(owner.crypt_view._document_path(), expected_path)
                self.assertEqual(reader.kind, suffix)
                if suffix == '.epub':
                    self.assertIsNotNone(reader.book)
                elif suffix == '.pdf':
                    self.assertEqual(reader.pdf.count, 3)
                else:
                    self.assertEqual(len(reader.labels), 2)
                self.assertEqual(app.reader_manager().catalog.library_store.stored_files()[0], [])
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
                    close_loop(app.loop)
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
                from unittest.mock import AsyncMock, patch
                with patch.object(app.main_window, 'dialog', AsyncMock()):
                    self.assertFalse(app.loop.run_until_complete(drawer.open_file(dict(path='broken.epub'))))
                self.assertIn('Document opening failed:', drawer.status.value)
                self.assertEqual(app.native_host.state.destination, 'documents')
                self.assertTrue(app.adaptive.menu_open['documents'])
            finally:
                if app is not None:
                    app.main_window.close()
                    close_loop(app.loop)
                LogisticsMobile.storage_root = None
