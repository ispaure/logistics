"""Reader paging owns swipes while Workspaces retains the source folder."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.page_animation import page_direction, begin_page_slide, finish_page_slide
from Mobile.native_tests.tests.logisticsmobile.fixtures import make_books


class ReaderNavigationTests(unittest.TestCase):
    def test_documents_reselection_returns_to_list_but_switching_tabs_retains_reader(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                epub, _ = make_books(fixtures)
                from commonUtils.runtime.document_access import LocalDocuments

                def tap(destination):
                    host = app.native_host
                    host.root._impl._set_value('current_tab_index', host.destinations.index(destination))
                    host.root.on_select()

                async def exercise():
                    store = app.reader_manager().catalog.library_store
                    record = store.import_book(LocalDocuments(), epub)
                    app.show_home()
                    await app.open_book(record['id'])
                    owner = app.readers.active
                    panel = app.body
                    # Programmatic activation and a return from Home retain the reader.
                    app.native_host.activate('documents')
                    self.assertIs(app.body, panel)
                    tap('home')
                    tap('documents')
                    self.assertIs(app.body, panel)
                    with patch.object(app, 'checkpoint', return_value=False):
                        tap('documents')
                    self.assertIs(app.body, panel)
                    self.assertTrue(app.routes.screens['documents'])
                    # Reselect from a nested reader page goes straight to the list.
                    owner.show_reader_appearance()
                    tap('documents')
                    self.assertEqual(app.native_host.state.destination, 'documents')
                    self.assertIs(app.body, app.routes.roots['documents'])
                    self.assertFalse(app.routes.screens['documents'])
                    self.assertIn(owner.session.id, app.workspace.sessions)
                    await app.open_book(record['id'])
                    self.assertIs(app.readers.active, owner)
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_all_documents_from_home_reader_keeps_session_and_can_resume(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            LogisticsMobile.storage_root = root
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                fixtures = root / 'fixtures'
                fixtures.mkdir()
                paths = make_books(fixtures)
                from commonUtils.runtime.document_access import LocalDocuments

                async def exercise():
                    store = app.reader_manager().catalog.library_store
                    for path in paths:
                        record = store.import_book(LocalDocuments(), path)
                        app.show_home()
                        await app.open_book(record['id'])
                        owner = app.readers.active
                        key = owner.session.id
                        self.assertEqual(app.routes.origins['documents', 'reader:' + key], 'home')
                        owner.reader_actions.invoke(dict(owner.reader_actions.actions)['All documents'])
                        self.assertEqual(app.native_host.state.destination, 'documents')
                        self.assertFalse(app.routes.screens['documents'])
                        self.assertIs(app.body, app.routes.roots['documents'])
                        self.assertIn(key, app.workspace.sessions)
                        self.assertFalse(app.routes.origins)
                        await app.open_book(record['id'])
                        self.assertIs(app.readers.active, owner)
                        self.assertEqual(owner.session.id, key)
                    await app.readers.catalog.metadata_task
                    await app.readers.catalog.library_scan_task
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_folder_open_selects_documents_and_folder_tab_retains_browser(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                app.show_cloud(present=False)
                from features.rclone.mobile.storage_location import collection_path
                fixtures = collection_path(app.private_root) / 'fixtures'
                fixtures.mkdir(parents=True)
                epub, comic = make_books(fixtures)
                async def exercise():
                    for path in (comic, epub):
                        await app.show_files()
                        await app.browser_file_location(('Local files', 'fixtures'))
                        row = next(row for row in app.file_rows.values() if row['name'] == path.name)
                        app.browser_file_selected(row)
                        origin = app.body
                        file_path = app.file_path
                        with patch.object(app.native_host.chrome, 'set_page_swipes',
                                          wraps=app.native_host.chrome.set_page_swipes) as policy:
                            await app.read_managed_file()
                            self.assertEqual(app.native_host.state.destination, 'documents')
                            owner = app.readers.active
                            self.assertTrue(policy.call_args.args[0])
                            if path == comic:
                                with patch('logisticsmobile.page_animation.begin_page_slide') as begin, patch(
                                        'logisticsmobile.page_animation.finish_page_slide') as finish:
                                    for rtl in (False, True):
                                        owner.book_reader.right_to_left = rtl
                                        for index, expected in ((1, -1 if rtl else 1), (0, 1 if rtl else -1)):
                                            await owner.move_book_page(index)
                                            self.assertEqual(begin.call_args.args[1], expected)
                                            self.assertEqual(finish.call_args.args[1], expected)
                            owner.set_reading_mode(False)
                            app.adaptive.render()
                            self.assertTrue(policy.call_args.args[0])
                            owner.set_reading_mode(True)
                            app.adaptive.render()
                            self.assertTrue(policy.call_args.args[0])
                            self.assertTrue(app.select_destination('files'))
                            app.native_host.activate('files')
                            self.assertIs(app.body, origin)
                            self.assertEqual(app.file_path, file_path)
                            self.assertFalse(policy.call_args.args[0])
                            self.assertIn(owner.session.id, app.workspace.sessions)
                app.loop.run_until_complete(exercise())
            finally:
                app.main_window.close()
                app.loop.close()

    def test_slide_direction_tracks_page_order_and_manga(self):
        for rtl in (False, True):
            self.assertEqual(page_direction(None, 0, right_to_left=rtl), 0)
            self.assertEqual(page_direction(3, 3, right_to_left=rtl), 0)
            self.assertEqual(page_direction(2, 4, right_to_left=rtl), -1 if rtl else 1)
            self.assertEqual(page_direction(4, 2, right_to_left=rtl), 1 if rtl else -1)
        content = Mock()
        for direction, preferences in ((0, {}), (1, {'android_eink': 'true'})):
            begin_page_slide(content, direction, preferences)
            finish_page_slide(content, direction, preferences)
        self.assertEqual(content.mock_calls, [])
