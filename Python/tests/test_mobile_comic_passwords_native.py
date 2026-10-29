"""Real native standalone AES/ZipCrypto CBZ reads with no remote credentials."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from commonUtils.archives.zip_access import ArchivePasswordError
from commonUtils.runtime.resources.documents import LocalDocuments
from features.rclone.mobile.cloud import CloudClient
from mobile.library import LibraryStore


@unittest.skipUnless(os.environ.get('LOGISTICS_MOBILE_BRIDGE'), 'Host native bridge required')
class StandaloneComicNativeTests(unittest.TestCase):
    def test_password_retry_page_navigation_lock_and_restart_preserve_encryption(self):
        fixture = json.loads((Path(__file__).parents[2] / 'mobile_build/native_tests/tests/logisticsmobile/comic_fixture.json').read_text())
        client = CloudClient(library=os.environ['LOGISTICS_MOBILE_BRIDGE'])
        client.request('clear')
        for kind in ('aes', 'legacy'):
            with self.subTest(kind=kind), TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / (kind + '.cbz')
                original = base64.b64decode(fixture[kind])
                source.write_bytes(original)
                store = LibraryStore(root / 'Library', archive_client=client)
                record = store.import_book(LocalDocuments(), source)
                for password in (None, 'wrong password'):
                    with self.assertRaises(ArchivePasswordError):
                        store.open(record['id'], password=password)
                record, reader = store.open(record['id'], password=fixture['password'])
                self.assertEqual(reader.pages, ['page2.png', 'page10.png'])
                self.assertTrue(reader.right_to_left)
                self.assertEqual(reader.read_page(1)[0], base64.b64decode(fixture['page']))
                record = store.progress(record, 1, bookmark=True)
                self.assertEqual(store.path(record['id'], '.cbz').read_bytes(), original)
                self.assertNotIn(fixture['password'].encode(), store.path(record['id'], '.json').read_bytes())
                reader.document.source.close()
                self.assertEqual(reader.document.source.cache_bytes, 0)
                self.assertIsNone(reader.document.source.password)
                with self.assertRaises(ArchivePasswordError):
                    LibraryStore(store.root, archive_client=client).open(record['id'])
                reopened, reader = store.open(record['id'], password=fixture['password'])
                self.assertEqual(reopened['bookmarks'], [1])
                reader.document.source.close()
                self.assertEqual(client.crypt_remotes(), [])
                self.assertEqual(source.read_bytes(), original)
