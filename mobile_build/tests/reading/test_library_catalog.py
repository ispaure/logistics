"""Configured collection folders, including encrypted and pulled copies."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mobile.library_ui import discover_libraries


class CryptClient:
    generation = 1
    identity = 'a' * 64
    connection = 'b' * 64

    def connection_identity(self, remote):
        return self.connection

    def request(self, action, **values):
        if action == 'crypt_paths':
            return [self.request('crypt_path', **dict(values, **entry, decode=True))['path']
                    for entry in values['entries']]
        if action == 'crypt_path':
            parts = values['path'].split('/') if values['path'] else []
            parts = ([bytes.fromhex(part).decode() for part in parts] if values.get('decode')
                     else [part.encode().hex() for part in parts])
            return dict(identity=self.identity, path='/'.join(parts))
        if action == 'crypt_raw_read':
            data = os.read(values['fd'], 256 * 1024)
            return dict(data=base64.b64encode(data[::-1]).decode())
        raise AssertionError(action)


class LibraryCatalogTests(unittest.TestCase):
    def test_local_configuration_order_dedup_missing_and_invalid_names(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            collection = root / 'LocalFiles' / 'Collection'
            collection.mkdir(parents=True)
            config = collection / 'remoteConfig.ini'
            config.write_text('[LogisticsComics]\nlibraries=Missing,Mangas,Comics,Mangas\n')
            for name in ('Comics', 'Mangas', 'Unconfigured'):
                (collection / name).mkdir()
            (collection / 'loose.cbz').write_bytes(b'not a library')
            jobs = [dict(crypt=False, remote='Collection', target='Collection')]
            records, failures = discover_libraries(root, jobs)
            self.assertEqual(failures, 0)
            self.assertEqual([row['name'] for row in records], ['Mangas', 'Comics'])
            self.assertEqual([row['folder'] for row in records], ['Collection/Mangas', 'Collection/Comics'])
            config.write_text('[LogisticsComics]\nlibraries=../outside\n')
            self.assertEqual(discover_libraries(root, jobs), ([], 1))
            config.unlink()
            self.assertEqual(discover_libraries(root, jobs), ([], 0))

    def test_crypt_configuration_uses_provider_and_pulled_namespace(self):
        from features.rclone.localcrypt.mobile.resources import CryptFiles
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client = CryptClient()
            namespace = root / 'LocalCryptFolders' / client.connection
            folder = 'Collection'.encode().hex()
            library = 'Comics'.encode().hex()
            (namespace / folder / library).mkdir(parents=True)
            config = namespace / folder / 'remoteConfig.ini'.encode().hex()
            config.write_bytes(b'[LogisticsComics]\nlibraries=Comics\n'[::-1])
            job = dict(crypt=True, remote='Remote', identity=client.connection, prefix=folder)
            records, failures = discover_libraries(root, [job], client, ['Remote'])
            self.assertEqual(failures, 0)
            self.assertEqual([(row['name'], row['folder'], row['source']) for row in records],
                             [('Comics', 'Collection/Comics', 'LocalCrypt: Remote')])
            self.assertIsInstance(records[0]['provider'], CryptFiles)
            self.assertEqual(records[0]['provider'].root, namespace)
            self.assertEqual(discover_libraries(root, [job]), ([], 0))
            client.connection = 'c' * 64
            self.assertEqual(discover_libraries(root, [job], client, ['Remote']), ([], 0))

    def test_catalog_shows_folder_and_opens_its_browser(self):
        from mobile.app import LogisticsMobile
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            collection = app.private_root / 'LocalFiles' / 'Collection'
            (collection / 'Comics').mkdir(parents=True)
            (collection / 'remoteConfig.ini').write_text('[LogisticsComics]\nlibraries=Comics\n')
            app.show_library()
            catalog = app.readers.catalog

            async def exercise():
                await catalog.library_scan_task
                self.assertEqual([button.text for button in catalog.library_row_buttons], ['Comics'])
                listing = catalog.library_folder_list
                listing.select_index(0)
                opened = catalog._select_library_row(listing)
                self.assertIsNone(listing.selection)
                await opened
                self.assertEqual(app.file_path, 'Collection/Comics')
                self.assertEqual(app.file_provider.root, app.private_root / 'LocalFiles')
                from features.rclone.localcrypt.mobile.resources import CryptFiles
                private = object.__new__(CryptFiles)
                catalog.library_records.append(dict(name='Private Comics', folder='Comics',
                    source='LocalCrypt', provider=private, client=app.cloud_client,
                    generation=getattr(app.cloud_client, 'generation', None)))
                catalog.filter_library()
                stale = catalog.library_row_buttons[-1].on_press
                app.clear_private_catalog()
                self.assertEqual([row['name'] for row in catalog.library_records], ['Comics'])
                self.assertEqual([button.text for button in catalog.library_row_buttons], ['Comics'])
                await stale()
            app.loop.run_until_complete(exercise())
