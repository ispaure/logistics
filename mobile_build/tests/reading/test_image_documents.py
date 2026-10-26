"""Images remain provider documents across navigation and failed replacement."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from services.documents.mobile_storage import open_provider_document
from features.rclone.localcrypt.mobile.resources import CryptFiles
from mobile_build.tests.storage.test_storage_reader_opening import ReaderClient
from mobile_build.native_tests.tests.logisticsmobile.fixtures import make_books
from zipfile import ZipFile


class ImageDocumentTests(unittest.TestCase):
    def test_images_open_and_navigate_for_local_localcrypt_and_remote(self):
        for storage in ('local', 'localcrypt', 'remote'):
            with self.subTest(storage=storage), TemporaryDirectory() as directory:
                root = Path(directory)
                _, comic = make_books(root)
                with ZipFile(comic) as archive:
                    data = archive.read(next(name for name in archive.namelist() if name.endswith('.png')))
                LogisticsMobile.storage_root = root / 'app'
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                try:
                    app.cloud_client = ReaderClient()
                    if storage == 'localcrypt':
                        provider = CryptFiles(root / 'encrypted', app.cloud_client, 'Secret')
                    else:
                        folder = root / 'images'
                        folder.mkdir()
                        provider = LocalFiles(folder)
                        if storage == 'remote':
                            provider.remote_storage = True
                    for name, content in [('pic2.png', data), ('pic10.png', data), ('pic11.png', b'broken')]:
                        path = provider._physical(name)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(content[::-1] if storage == 'localcrypt' else content)
                    self.assertTrue(app.loop.run_until_complete(open_provider_document(app, provider, 'pic2.png')))
                    owner = app.private_sessions.active
                    self.assertTrue(owner.crypt_reader.image_document)
                    self.assertFalse(owner.image_file_buttons[0].enabled)
                    self.assertTrue(owner.image_file_buttons[1].enabled)
                    self.assertIn('(Read-Only)', owner.crypt_view._document_storage_status)
                    app.loop.run_until_complete(owner.image_file_buttons[1].on_press())
                    owner = app.private_sessions.active
                    self.assertEqual(owner.crypt_reader.key, 'pic10.png')
                    self.assertEqual(len(app.private_sessions.controllers), 1)
                    app.loop.run_until_complete(owner.image_file_buttons[1].on_press())
                    self.assertIs(app.private_sessions.active, owner)
                    self.assertEqual(owner.crypt_reader.key, 'pic10.png')
                finally:
                    app.main_window.close()
                    app.loop.close()
                    LogisticsMobile.storage_root = None

    def test_home_server_image_navigation_is_read_only_and_session_only(self):
        from mobile_build.tests.reading.test_remote_readers import RemoteClient
        from features.rclone.mobile.remote_readers import RemoteReaders
        class ServerClient(RemoteClient):
            package_records = [dict(package_name='Session network shares', remotes=['Photos'], saved=False)]
            def entries(self, remote, path=''):
                return [dict(path=name, directory=False, size=len(data)) for name, data in self.files.items()]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _, comic = make_books(root)
            with ZipFile(comic) as archive:
                data = archive.read(next(name for name in archive.namelist() if name.endswith('.png')))
            LogisticsMobile.storage_root = root / 'app'
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                client = app.cloud_client = ServerClient()
                client.files = {'image2.png': data, 'image10.png': data}
                copies = RemoteReaders(client, 'Photos')
                self.assertTrue(app.loop.run_until_complete(app.open_crypt(copies=copies, key='image2.png')))
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_view._document_storage_status,
                                 'Home Server · 🕵️ Session-Only · (Read-Only)')
                self.assertEqual(owner.crypt_view._native_reader_title(), 'image2.png (🕵️ Session-Only)')
                app.loop.run_until_complete(owner.image_file_buttons[1].on_press())
                owner = app.private_sessions.active
                self.assertEqual(owner.crypt_reader.key, 'image10.png')
                self.assertTrue(owner.crypt_reader.read_only)
                self.assertFalse(owner.image_file_buttons[1].enabled)
                self.assertEqual(len(app.private_sessions.controllers), 1)
            finally:
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
