"""Library views keep document identity and release inactive decoder content."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderSessionTests(unittest.TestCase):
    def test_duplicate_open_switch_reopen_and_close(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_library()
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, comic = make_books(fixtures)
                first = app.library_store.import_book(LocalDocuments(), epub)
                second = app.library_store.import_book(LocalDocuments(), comic)
                app.loop.run_until_complete(app.open_book(first['id']))
                first_owner = app.readers.active
                first_session = first_owner.session.id
                app.loop.run_until_complete(app.next_book_page())
                app.loop.run_until_complete(app.open_book(first['id']))
                self.assertIs(app.readers.active, first_owner)
                app.loop.run_until_complete(app.open_book(second['id']))
                self.assertIsNone(first_owner.book_reader)
                self.assertEqual(list(first_owner.book_content.children), [])
                app.loop.run_until_complete(app.open_book(first['id']))
                self.assertEqual(app.book_record['position'], 1)
                self.assertEqual(app.readers.active.session.id, first_session)
                self.assertTrue(app.close_session(first_session))
                self.assertNotIn(first_session, app.readers.controllers)
                self.assertTrue(app.library_store.path(first['id'], '.epub').exists())
            finally:
                app.main_window.close()
                app.loop.close()
