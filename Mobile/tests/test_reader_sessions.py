"""Library views keep document identity and release inactive decoder content."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from commonUtils.runtime.document_access import LocalDocuments
from logisticsmobile.app import LogisticsMobile
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderSessionTests(unittest.TestCase):
    def test_reopening_loaded_epub_reloads_content_and_preserves_passage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)

                async def exercise():
                    self.assertTrue(await app.open_book(record['id']))
                    owner = app.readers.active
                    reader = owner.book_reader
                    offset = min(5, owner.epub_text.length)
                    owner.epub_event(reader, owner.book_epoch, 0, 'position', offset)
                    owner.request_position_flush()
                    await owner._epub_location_task
                    old_bridge = owner.epub_view._chapter_bridge
                    app.show_documents_hub()
                    with patch.object(owner.epub_view, 'set_content', wraps=owner.epub_view.set_content) as reload:
                        self.assertTrue(await app.open_book(record['id']))
                    reload.assert_called_once()
                    self.assertIs(owner.book_reader, reader)
                    self.assertTrue(old_bridge.closed)
                    self.assertIsNot(owner.epub_view._chapter_bridge, old_bridge)
                    self.assertEqual(owner.epub_offset, offset)
                    self.assertEqual(len(app.workspace.sessions), 1)
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task

                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_comic_page_focus_swipes_boundaries_and_manga_direction(self):
        import asyncio
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_library()
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                _, comic = make_books(fixtures)
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
                policy_patch = patch.object(app.native_host.chrome, 'set_page_swipes',
                                            wraps=app.native_host.chrome.set_page_swipes)
                page_policy = policy_patch.start()
                self.addCleanup(policy_patch.stop)
                async def exercise():
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    self.assertTrue(owner.reader_immersive)
                    self.assertTrue(page_policy.call_args.args[0])
                    self.assertNotIn(owner.reader_header, owner.library_view.children)
                    self.assertEqual(owner.library_view.style.margin_top, 0)
                    view = owner.book_content.children[0]
                    from toga.style.pack import NONE
                    self.assertEqual(view.style.width, NONE)
                    self.assertTrue(view.magnifier_enabled)
                    view.toggle_controls()
                    self.assertFalse(view.magnifier_enabled)
                    self.assertFalse(owner.reader_immersive)
                    self.assertEqual(view.style.width, NONE)
                    self.assertTrue(page_policy.call_args.args[0])
                    self.assertTrue(view.page_swipes_at_edges)
                    view.toggle_controls()
                    self.assertTrue(owner.reader_immersive)
                    self.assertTrue(view.magnifier_enabled)
                    view.page(-1)
                    await asyncio.sleep(.02)
                    self.assertEqual(owner.book_record['position'], 0)
                    view.page(1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.book_record['position'], 1)
                    self.assertFalse(view.magnifier_enabled)  # retired canvas
                    self.assertTrue(owner.book_content.children[0].magnifier_enabled)
                    owner.set_reading_mode(False)
                    await owner.move_book_page(0)
                    self.assertFalse(owner.book_content.children[0].magnifier_enabled)
                    owner.set_reading_mode(True)
                    await owner.move_book_page(1)
                    owner.book_reader.right_to_left = True
                    owner.book_content.children[0].page(1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.book_record['position'], 0)
                    owner.book_content.children[0].page(-1)
                    await owner._comic_swipe_task
                    self.assertEqual(owner.book_record['position'], 1)
                    self.assertEqual(owner.book_status.text.count('Cannot'), 0)
                    app.show_home()
                    self.assertFalse(app._comic_chrome_hidden)
                    self.assertFalse(page_policy.call_args.args[0])
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_late_password_prompt_does_not_focus_a_hidden_or_superseded_reader(self):
        import asyncio
        from threading import Event
        from commonUtils.archives.zip_access import ArchivePasswordError
        for replaced in (False, True):
            with self.subTest(replaced=replaced), TemporaryDirectory() as directory:
                root = Path(directory)
                LogisticsMobile.storage_root = root
                self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
                app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                replacement = None
                app.show_library()
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                _, comic = make_books(fixtures)
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
                started, release = Event(), Event()
                def delayed(*args, **kwargs):
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Password fixture was not released')
                    raise ArchivePasswordError('Protected archive')
                async def exercise():
                    nonlocal replacement
                    with patch.object(app.reader_manager().catalog.library_store, 'open', side_effect=delayed):
                        task = asyncio.create_task(app.open_book(record['id']))
                        try:
                            for _ in range(100):
                                if started.is_set():
                                    break
                                await asyncio.sleep(.01)
                            self.assertTrue(started.is_set())
                            owner = app.readers.active
                            with patch.object(owner.book_password, 'focus') as focus:
                                if replaced:
                                    replacement = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                                    current = replacement
                                else:
                                    app.show_settings()
                                    current = app
                                body, selected = current.body, current.workspace.active
                                release.set()
                                await task
                                focus.assert_not_called()
                                self.assertIs(current.body, body)
                                self.assertEqual(current.workspace.active, selected)
                                self.assertEqual(owner.book_pending_key, None if replaced else record['id'])
                        finally:
                            release.set()
                            await task
                try:
                    app.loop.run_until_complete(exercise())
                finally:
                    hosts = [app, *([replacement] if replacement is not None else [])]
                    for host in hosts:
                        host.main_window.close()
                    for loop in {host.loop for host in hosts}:
                        if not loop.is_closed():
                            loop.close()

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
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
                app.loop.run_until_complete(app.open_book(record['id']))
                app.loop.run_until_complete(app.next_book_page())
                reader_session = app.workspace.active
                app.preferences.save(restore_last_document='false', clear_unmodified_documents_on_restart='false')
                app.checkpoint()
                restored = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
                self.assertIsNone(restored.pending_reader_restore)
                self.assertNotEqual(restored.workspace.active, reader_session)
                self.assertIn(reader_session, restored.workspace.sessions)
                restored.native_host.root.current_tab = 2
                import asyncio
                restored.loop.run_until_complete(asyncio.sleep(.05))
                self.assertIsNone(getattr(getattr(getattr(restored, 'readers', None), 'active', None), 'book_reader', None))
                restored.session_opener(reader_session)()
                async def wait_reader():
                    for _ in range(100):
                        if getattr(getattr(getattr(restored, 'readers', None), 'active', None), 'book_reader', None) is not None:
                            return
                        await asyncio.sleep(.01)
                    self.fail('Explicit reader reopening did not finish')
                restored.loop.run_until_complete(wait_reader())
                self.assertEqual(restored.readers.active.book_record['position'], 1)
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
            app.preferences.save(clear_unmodified_documents_on_restart='false')
            app.show_library()
            fixtures = root / 'fixtures'
            fixtures.mkdir()
            epub, _ = make_books(fixtures)
            record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
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
                    owner = getattr(getattr(restored, 'readers', None), 'active', None)
                    if getattr(owner, 'book_reader', None) is not None and not owner.book_busy:
                        break
                    await asyncio.sleep(.01)
            restored.loop.run_until_complete(wait_reader())
            self.assertIsNotNone(restored.readers.active.book_reader)
            self.assertEqual(restored.readers.active.book_record['position'], 1)
            self.assertEqual(restored.workspace.active, selected)
            for host in (app, restored):
                host.loop.run_until_complete(host.readers.catalog.metadata_task)
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
                first = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
                second = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
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
                self.assertEqual(app.reader_manager().active.book_record['position'], 1)
                self.assertEqual(app.readers.active.session.id, first_session)
                self.assertTrue(app.close_session(first_session))
                self.assertNotIn(first_session, app.readers.controllers)
                self.assertTrue(app.reader_manager().catalog.library_store.path(first['id'], '.epub').exists())
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
                record = app.reader_manager().catalog.library_store.import_book(LocalDocuments(), epub)
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
                self.assertIn('padding:24px', content.call_args.args[1])
                self.assertEqual(owner.book_record['position'], 1)
                self.assertEqual(app.preferences.values['reading_theme'], 'dark')
            finally:
                app.main_window.close()
                app.loop.close()
