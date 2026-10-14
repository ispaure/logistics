"""Native widget password retry/lock flow with an isolated archive callback."""
import base64
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile
from commonUtils.archives.zip_access import ArchivePasswordError
from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile


class ComicPasswordUITests(unittest.TestCase):
    def test_import_retry_unlock_cancel_and_lock_do_not_save_passwords(self):
        fixture = json.loads((Path(__file__).parents[1] / 'native_tests/tests/logisticsmobile/comic_fixture.json').read_text())
        class LocalArchiveClient:
            def request(self, action, **values):
                assert action == 'file_archive'
                if not values.get('member'):
                    with os.fdopen(os.dup(values['fd']), 'rb') as stream, ZipFile(stream) as archive:
                        return [dict(name=i.filename, size=i.file_size, crc=i.CRC, flags=i.flag_bits, directory=i.is_dir()) for i in archive.infolist()]
                if values['password'] != fixture['password']:
                    raise ArchivePasswordError('Wrong ZIP password')
                member = values['member']
                data = b'<ComicInfo />' if member == 'ComicInfo.xml' else base64.b64decode(fixture['page'])
                return dict(data=base64.b64encode(data).decode())
        with TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                source = root / 'protected.cbz'
                source.write_bytes(base64.b64decode(fixture['aes']))
                app.show_library()
                app.library_store.archive_client = LocalArchiveClient()
                record = app.library_store.import_book(LocalDocuments(), source)
                app.refresh_library()
                app.loop.run_until_complete(app.open_book(record['id']))
                self.assertIsNone(app.book_reader)
                self.assertEqual(app.book_pending_key, record['id'])
                app.book_password.value = 'wrong'
                app.loop.run_until_complete(app.unlock_book())
                self.assertEqual(app.book_password.value, '')
                self.assertIn('Try again', app.book_status.text)
                self.assertIn(app.book_unlock_panel, app.library_view.children)
                app.cancel_book_unlock()
                self.assertIsNone(app.book_pending_key)
                app.loop.run_until_complete(app.open_book(record['id']))
                app.book_password.value = fixture['password']
                app.loop.run_until_complete(app.unlock_book())
                self.assertIsNotNone(app.book_reader, app.book_status.text)
                self.assertNotIn(app.book_unlock_panel, app.library_view.children)
                raw_source = app.book_reader.document.source
                app.loop.run_until_complete(app.next_book_page())
                self.assertEqual(app.book_record['position'], 1)
                app.lock_book()
                self.assertIsNone(raw_source.password)
                self.assertEqual(raw_source.cache_bytes, 0)
                self.assertFalse(app.book_content.children)
                self.assertTrue(app.library_store.path(record['id'], '.cbz').exists())
            finally:
                app.main_window.close()
                app.loop.close()
