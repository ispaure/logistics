"""Library views keep document identity and release inactive decoder content."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from logisticsmobile.access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderSessionTests(unittest.TestCase):
    def test_disabled_restore_keeps_reader_available_without_selecting_it(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            restored = None
            try:
                app.show_library()
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                record = app.library_store.import_book(LocalDocuments(), epub)
                app.loop.run_until_complete(app.open_book(record['id']))
                app.loop.run_until_complete(app.next_book_page())
                reader_session = app.workspace.active
                app.preferences.save(restore_last_document='false')
                app.checkpoint()
                restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                self.assertIsNone(restored.pending_reader_restore)
                self.assertNotEqual(restored.workspace.active, reader_session)
                self.assertIn(reader_session, restored.workspace.sessions)
                restored.native_host.root.current_tab = 2
                import asyncio
                restored.loop.run_until_complete(asyncio.sleep(.05))
                self.assertIsNone(getattr(restored, 'book_reader', None))
                restored.session_opener(reader_session)()
                async def wait_reader():
                    for _ in range(100):
                        if getattr(restored, 'book_reader', None) is not None:
                            return
                        await asyncio.sleep(.01)
                    self.fail('Explicit reader reopening did not finish')
                restored.loop.run_until_complete(wait_reader())
                self.assertEqual(restored.book_record['position'], 1)
                self.assertEqual(restored.workspace.active, reader_session)
            finally:
                hosts = [app, *([restored] if restored is not None else [])]
                for host in hosts:
                    host.main_window.close()
                for loop in {host.loop for host in hosts}:
                    if not loop.is_closed():
                        loop.close()

    def test_cold_workspace_keeps_reader_selection_until_documents_are_opened(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            app.show_library()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            record = app.library_store.import_book(LocalDocuments(), epub)
            app.loop.run_until_complete(app.open_book(record['id']))
            app.loop.run_until_complete(app.next_book_page())
            selected = app.workspace.active
            app.show_settings()
            app.checkpoint()
            restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.assertEqual(restored.workspace.active, selected)
            self.assertEqual(restored.pending_reader_restore, selected)
            restored.native_host.root.current_tab = 2
            import asyncio
            async def wait_reader():
                for _ in range(100):
                    if getattr(restored, 'book_reader', None) is not None:
                        break
                    await asyncio.sleep(.01)
            restored.loop.run_until_complete(wait_reader())
            self.assertIsNotNone(restored.book_reader)
            self.assertEqual(restored.book_record['position'], 1)
            self.assertEqual(restored.workspace.active, selected)
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

    def test_compact_controls_and_appearance_preserve_chapter(self):
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
                record = app.library_store.import_book(LocalDocuments(), epub)
                app.loop.run_until_complete(app.open_book(record['id']))
                owner = app.readers.active
                app.loop.run_until_complete(app.next_book_page())
                owner.toggle_reading_mode()
                self.assertTrue(owner.reader_immersive)
                self.assertEqual(len(owner.library_view.children), 2)
                owner.toggle_reading_mode()
                owner.show_reader_appearance()
                owner.reader_font.value, owner.reader_margin.value, owner.reader_theme.value = '20', '24', 'dark'
                with patch.object(owner.epub_view, 'set_content', wraps=owner.epub_view.set_content) as content:
                    app.loop.run_until_complete(owner.apply_reader_appearance())
                self.assertIn('margin:24px', content.call_args.args[1])
                self.assertEqual(owner.book_record['position'], 1)
                self.assertEqual(app.preferences.values['reading_theme'], 'dark')
            finally:
                app.main_window.close()
                app.loop.close()
