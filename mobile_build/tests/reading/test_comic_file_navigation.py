"""Adjacent volumes remain readable across storage and session handoffs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from mobile.app import LogisticsMobile
from features.rclone.localcrypt.mobile.resources import CryptFiles, ManagedCopies
from features.rclone.mobile.remote_resources import NativeRemoteResources
from features.rclone.remote_access import NativeRemoteLocation
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from mobile_build.tests.storage.test_storage_reader_opening import ReaderClient
from mobile_build.tests.reading.test_remote_readers import RemoteClient


class ComicFileNavigationTests(unittest.TestCase):
    def test_localcrypt_can_navigate_more_than_four_volumes_and_back(self):
        self.exercise('localcrypt')

    def test_cloud_read_only_comics_can_navigate_neighbors(self):
        self.exercise('cloud')

    def test_imported_comics_navigate_in_natural_order(self):
        from commonUtils.runtime.resources.documents import LocalDocuments
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            _, comic = make_books(fixtures)
            LogisticsMobile.storage_root = root / 'private'
            app = None
            try:
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                store = app.reader_manager().catalog.library_store
                records = []
                for number in (1, 2, 10):
                    path = fixtures / f'Volume {number}.cbz'
                    path.write_bytes(comic.read_bytes())
                    records.append(store.import_book(LocalDocuments(), path))
                async def check():
                    await app.open_book(records[0]['id'])
                    for record in records[1:]:
                        owner = app.readers.active
                        self.assertTrue(owner.comic_header.following.enabled)
                        await owner.next_comic_file()
                        self.assertEqual(app.readers.active.book_record['id'], record['id'])
                    for record in reversed(records[:-1]):
                        await app.readers.active.previous_comic_file()
                        self.assertEqual(app.readers.active.book_record['id'], record['id'])
                app.loop.run_until_complete(check())
            finally:
                if app is not None:
                    app.main_window.close()
                    app.loop.close()
                LogisticsMobile.storage_root = None

    def exercise(self, storage):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            _, comic = make_books(fixtures)
            data = comic.read_bytes()
            LogisticsMobile.storage_root = root / 'private'
            app = None
            try:
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                names = ['Series/Volume ' + str(i) + ('.ZIP' if i == 10 else '.cbz')
                         for i in (1, 2, 3, 4, 10, 11)]
                if storage == 'localcrypt':
                    client = app.cloud_client = ReaderClient()
                    provider = CryptFiles(app.private_root / 'LocalCryptFolders', client, 'Secret')
                    provider._physical('Series', directory=True).mkdir()
                    for name in names:
                        provider._physical(name).write_bytes(data[::-1])
                else:
                    client = app.cloud_client = RemoteClient()
                    client.files = dict.fromkeys(names, data)
                    client.entries = lambda remote, path='': [
                        dict(path=name, directory=False, size=len(data)) for name in names]
                    provider = NativeRemoteResources(client, NativeRemoteLocation('Files'))
                copies = provider.document_readers() if storage == 'cloud' else ManagedCopies(provider)
                async def check():
                    self.assertTrue(await app.open_crypt(copies=copies, key=names[0]))
                    for name in names[1:]:
                        owner = app.private_sessions.active
                        self.assertTrue(owner.comic_header.following.enabled)
                        await owner.next_provider_comic_file()
                        self.assertEqual(len(app.private_sessions.controllers), 1)
                        self.assertEqual(app.private_sessions.active.crypt_reader.key, name,
                                         getattr(app, 'document_status', None))
                    self.assertFalse(app.private_sessions.active.comic_header.following.enabled)
                    for name in reversed(names[:-1]):
                        await app.private_sessions.active.previous_provider_comic_file()
                        self.assertEqual(app.private_sessions.active.crypt_reader.key, name)
                    self.assertFalse(app.private_sessions.active.comic_header.previous.enabled)
                    owner = app.private_sessions.active
                    if owner.crypt_immersive:
                        owner.toggle_private_reading_mode()
                    await owner.next_provider_comic_file()
                    owner = app.private_sessions.active
                    self.assertFalse(owner.crypt_immersive)
                    # A corrupt next volume must preserve the current reader and page.
                    await owner.move_private_page(1)
                    if storage == 'localcrypt':
                        provider._physical(names[2]).write_bytes(b'bad archive')
                    else:
                        client.files[names[2]] = b'bad archive'
                    with patch.object(app.main_window, 'dialog', new_callable=AsyncMock):
                        await owner.comic_header.following.on_press()
                    self.assertIs(app.private_sessions.active, owner)
                    self.assertEqual(owner.crypt_reader.key, names[1])
                    self.assertEqual(owner.crypt_page.value, owner.crypt_reader.labels[1])
                    self.assertTrue(owner.comic_header.following.enabled)
                    self.assertEqual(len(app.private_sessions.controllers), 1)
                    await owner.previous_provider_comic_file()
                    await app.private_sessions.active.next_provider_comic_file()
                    restored = app.private_sessions.active
                    self.assertEqual(restored.crypt_page.value, restored.crypt_reader.labels[1])
                    if storage == 'cloud':
                        self.assertEqual(len(client.cached), 1)
                app.loop.run_until_complete(check())
            finally:
                if app is not None:
                    app.main_window.close()
                    app.loop.close()
                LogisticsMobile.storage_root = None
