"""Persistent local search shares desktop terms without persisting private names."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.event_loop import close_loop
from commonUtils.testing.stages import TestStage
from commonUtils.testing.waiting import wait_until

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, get_ident
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.operations import OperationCancelled
from mobile.local_search import LocalSearch


class LocalSearchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / 'files'
        (self.root / 'Books').mkdir(parents=True)
        for name in ('The End of Eternityla.epub', 'END_ETERNITY.pdf', 'Eternity End.md',
                     'Straße.txt', '100%_literal.txt'):
            (self.root / 'Books' / name).touch()
        self.provider = LocalFiles(self.root)
        self.database = base / 'cache' / 'index.sqlite3'
        self.search = LocalSearch(self.database)
        self.addCleanup(self.search.cache.close)

    def prepare(self):
        self.search.prepare(self.provider, '', cancelled=lambda: False)

    def names(self, query, directory=''):
        result = self.search.search(self.provider, directory, query)
        self.assertTrue(result.complete, result.errors)
        return {Path(row['path']).name for row in result.rows}

    def test_keyword_phrase_unicode_and_literal_rules_match_desktop(self):
        self.prepare()
        self.assertEqual(self.names('end ETERNITY'),
                         {'The End of Eternityla.epub', 'END_ETERNITY.pdf', 'Eternity End.md'})
        self.assertEqual(self.names('"end eternity"'), {'END_ETERNITY.pdf'})
        self.assertEqual(self.names('"end of eternity"'), {'The End of Eternityla.epub'})
        self.assertEqual(self.names('"end eternity'), {'END_ETERNITY.pdf'})
        self.assertEqual(self.names('STRASSE'), {'Straße.txt'})
        self.assertEqual(self.names('100%_literal'), {'100%_literal.txt'})
        self.assertEqual(self.names('100*'), set())

    def test_cold_progress_uses_live_names_and_loads_only_matching_metadata(self):
        updates = []
        with patch.object(self.search, '_prepare', side_effect=AssertionError('Cold search waited for index')), \
                patch.object(self.provider, 'entry', wraps=self.provider.entry) as load:
            result = self.search.search(self.provider, '', '"end eternity"', progress=updates.append)
        self.assertTrue(result.complete, result.errors)
        self.assertEqual([row['path'] for row in result.rows], ['Books/END_ETERNITY.pdf'])
        self.assertEqual(load.call_args_list[0].args, ('Books/END_ETERNITY.pdf',))
        self.assertEqual(load.call_count, 1)
        self.assertTrue(updates)
        self.assertFalse(updates[0].cached)
        self.assertEqual(updates[0].rows, result.rows)

    def test_device_files_search_is_scoped_and_only_loads_metadata_for_matches(self):
        from mobile.local_sources import PhoneFiles

        provider = PhoneFiles(self.root / 'app')
        for folder in ('Current/Nested', 'Sibling', 'LocalCrypt'):
            (provider.root / folder).mkdir(parents=True)
            (provider.root / folder / 'needle.txt').touch()
        (provider.root / 'Current' / 'other.txt').touch()

        with patch.object(provider, 'entry', wraps=provider.entry) as load:
            result = self.search.search(provider, 'Current', 'needle')
            self.assertTrue(result.complete, result.errors)
            self.assertEqual([row['path'] for row in result.rows], ['Current/Nested/needle.txt'])
            load.assert_called_once_with('Current/Nested/needle.txt')

        all_files = self.search.search(provider, '', 'needle')
        self.assertTrue(all_files.complete, all_files.errors)
        self.assertEqual({row['path'] for row in all_files.rows}, {
            'Current/Nested/needle.txt', 'Sibling/needle.txt',
        })
        from sqlite3 import connect
        with connect(self.database.parent / 'device-filenames.sqlite3') as connection:
            inventory = connection.execute('SELECT path, rows FROM folders').fetchall()
        self.assertNotIn('LocalCrypt', str(inventory))
        restarted = LocalSearch(self.database)
        self.addCleanup(restarted.cache.close)
        updates = []
        with patch.object(provider, 'list_names', side_effect=AssertionError('Unchanged folder was relisted')):
            warm = restarted.search(provider, '', 'needle', progress=updates.append)
        self.assertEqual(warm.rows, all_files.rows)
        self.assertEqual(updates[0].cache_phase, 'device_cached')

        (provider.root / 'Sibling' / 'needle.txt').unlink()
        self.assertEqual([row['path'] for row in restarted.search(provider, '', 'needle').rows],
                         ['Current/Nested/needle.txt'])
        with patch.object(provider, 'list_names', side_effect=AssertionError('Refreshed cache was discarded')):
            self.assertEqual([row['path'] for row in LocalSearch(self.database).search(provider, '', 'needle').rows],
                             ['Current/Nested/needle.txt'])

    def test_reopened_database_answers_without_directory_enumeration(self):
        self.prepare()
        restarted = LocalSearch(self.database)
        self.addCleanup(restarted.cache.close)
        with patch.object(restarted.cache, 'get', side_effect=AssertionError('Unexpected scan')), \
                patch.object(self.provider, 'list', side_effect=AssertionError('Unexpected traversal')):
            result = restarted.search(self.provider, 'Books', 'ETERNITY end')
        self.assertEqual(len(result.rows), 3)
        self.assertTrue(result.complete)
        self.assertTrue(all(row['path'].startswith('Books/') for row in result.rows))

    def test_refresh_removes_deleted_names_and_discovers_new_files(self):
        self.prepare()
        old = self.root / 'Books' / 'END_ETERNITY.pdf'
        old.rename(old.with_name('New End Eternity.pdf'))
        # Cached hits already reject missing files before the background refresh.
        self.assertNotIn('END_ETERNITY.pdf', self.names('end eternity'))
        self.prepare()
        self.assertIn('New End Eternity.pdf', self.names('end eternity'))
        self.assertNotIn('END_ETERNITY.pdf', self.names('end eternity'))

    def test_session_private_and_virtual_sources_never_create_database(self):
        for flag in ('private', 'session_only', 'remote_storage'):
            provider = LocalFiles(self.root)
            setattr(provider, flag, True)
            self.search.prepare(provider, '', cancelled=lambda: False)
            result = self.search.search(provider, '', 'end eternity')
            self.assertEqual(len(result.rows), 3)
            self.assertFalse(self.database.exists())
        provider = SimpleNamespace(root=self.root, relative=self.provider.relative,
                                   list=self.provider.list)
        self.assertEqual(len(self.search.search(provider, '', 'end eternity').rows), 3)
        self.assertFalse(self.database.exists())

    def test_cancellation_and_scope(self):
        self.prepare()
        with self.assertRaises(OperationCancelled):
            self.search.search(self.provider, '', 'end', cancelled=lambda: True)
        with self.assertRaises(ValueError):
            self.search.search(self.provider, '../', 'end')
        (self.root / 'Empty').mkdir()
        self.search.prepare(self.provider, 'Empty', cancelled=lambda: False)
        self.assertEqual(self.names('end', 'Empty'), set())


class BackgroundSearchTests(unittest.TestCase):
    def test_browser_prepares_off_ui_thread_and_cancels_on_stop(self):
        from mobile.app import LogisticsMobile
        from mobile.browser_ui import FileBrowser
        with TemporaryDirectory() as temporary:
            LogisticsMobile.storage_root = Path(temporary)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            started, release = Event(), Event()
            threads, cancellations = [], []
            class Index:
                supports = staticmethod(lambda provider: True)
                def prepare(self, provider, directory, *, cancelled):
                    threads.append(get_ident())
                    cancellations.append(cancelled)
                    started.set()
                    release.wait(5)
                def search(self, *args, **kwargs):
                    raise AssertionError('No query requested')
            browser = FileBrowser(local_search=Index())
            try:
                provider = SimpleNamespace(root=Path('/virtual'), relative=lambda value: value)
                ui_thread = get_ident()
                browser.set_entries(provider, '', [])
                browser.open_search()
                async def check():
                    while not started.is_set():
                        await asyncio.sleep(.01)
                    self.assertNotEqual(threads, [ui_thread])
                    browser.stop()
                    self.assertTrue(cancellations[0]())
                    release.set()
                    await browser.close()
                app.loop.run_until_complete(asyncio.wait_for(check(), 3))
            finally:
                release.set()
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                close_loop(app.loop)


class SavedSearchPublicationTests(unittest.TestCase):
    def setUp(self):
        from mobile.app import LogisticsMobile
        from mobile.browser_ui import FileBrowser

        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        LogisticsMobile.storage_root = base / 'app'
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.loop = self.app.loop
        self.addCleanup(close_loop, self.loop)
        self.addCleanup(self.app.main_window.close)

        root = base / 'files'
        (root / 'Books').mkdir(parents=True)
        (root / 'Other').mkdir()
        (root / 'Books' / 'Keep.md').touch()
        self.matches = [f'Books/Match-{index:02}.md' for index in range(60)]
        for path in self.matches:
            (root / path).touch()
        self.provider = LocalFiles(root)
        self.search = LocalSearch(base / 'cache' / 'index.sqlite3')
        self.addCleanup(self.search.cache.close)
        self.search.prepare(self.provider, '', cancelled=lambda: False)
        self.browser = FileBrowser(local_search=self.search)
        self.addCleanup(lambda: self.loop.run_until_complete(self.browser.close()))

    def show_folder(self, folder):
        self.browser.set_entries(self.provider, folder, self.provider.list(folder),
                                 location=('Local', folder))

    def visible_paths(self):
        return [row.entry.payload['path'] for row in self.browser.native_list.data]

    async def finish_tasks(self):
        while pending := tuple(task for task in self.browser.tasks if not task.done()):
            await asyncio.wait_for(asyncio.gather(*pending), 5)

    def test_typeahead_counts_elapsed_time_before_the_search_task_starts(self):
        from commonUtils.ui.native_browser import presentation

        browser = self.browser
        self.show_folder('')
        self.loop.run_until_complete(self.finish_tasks())
        sleep = AsyncMock()
        with patch.object(presentation, 'monotonic', return_value=10.5), \
                patch.object(presentation, 'asyncio', SimpleNamespace(sleep=sleep)):
            self.loop.run_until_complete(browser._apply_query(
                browser.search_epoch, browser.search_cancelled, 10.0, .3))
        sleep.assert_awaited_once_with(0)

    def test_index_completion_preserves_pending_typeahead_and_replays_submitted_text(self):
        from commonUtils.search.policy import SEARCH_DEBOUNCE_SECONDS

        browser = self.browser
        self.show_folder('')
        apply = AsyncMock()

        async def check():
            browser.search.value = 'Match'
            pending = browser.search_epoch
            await browser._prepare_local_search(self.provider, '', Event())
            self.assertEqual(browser.search_epoch, pending)
            await browser._search_subfolders(pending, browser.search_cancelled)
            await browser._prepare_local_search(self.provider, '', Event())
            await self.finish_tasks()
            self.assertEqual(browser.search_epoch, pending + 1)
            self.assertEqual([call.args[-1] for call in apply.await_args_list],
                             [SEARCH_DEBOUNCE_SECONDS, 0])

        with patch.object(browser, '_apply_query', apply):
            self.loop.run_until_complete(check())

    def test_saved_page_is_displayed_before_later_validation_with_writer_held(self):
        browser, provider = self.browser, self.provider
        self.show_folder('')
        # The saved first page will contain a deleted entry.
        (provider.root / self.matches[0]).unlink()
        blocked, release = Event(), Event()
        entry = provider.entry

        def validate(path):
            if path == self.matches[0]:
                blocked.set()
                if not release.wait(5):
                    raise AssertionError('The test did not release later validations')
            return entry(path)

        async def check():
            # Exercise the actual WAL reader while another cache owns the file lock.
            writer = LocalSearch(self.search.cache.database)
            with writer.cache._writer(lambda: False):
                browser.open_search()
                browser.search.value = 'Match'
                try:
                    await wait_until(lambda: blocked.is_set() and bool(self.visible_paths()),
                                     message='Saved results did not publish before later validation')
                    self.assertEqual(self.visible_paths(), self.matches)
                    self.assertIn('Checking', browser.page_label.text)
                    browser.selected = provider.root / self.matches[20]
                finally:
                    release.set()
                await wait_until(lambda: self.visible_paths() == self.matches[1:]
                                 and not browser.searching,
                                 message='Warm search did not finish while the writer was held')
                self.assertEqual(browser.selected, provider.root / self.matches[20])
                browser.close_search()
            await self.finish_tasks()

        with patch.object(provider, 'entry', side_effect=validate), \
                patch('commonUtils.search.indexed.monotonic', return_value=0):
            self.loop.run_until_complete(check())

    def test_cached_click_validates_independently_of_the_blocked_background_pass(self):
        browser, provider = self.browser, self.provider
        self.show_folder('')
        blocked, release = Event(), Event()
        entry = provider.entry
        (provider.root / self.matches[0]).unlink()
        opened = []
        browser.on_open_file = lambda row: opened.append(dict(row))

        def validate(path):
            if path == self.matches[0] and not blocked.is_set():
                blocked.set()
                if not release.wait(5):
                    raise AssertionError('Later validation was not released')
            return entry(path)

        async def check():
            browser.search.value = 'Match'
            try:
                await wait_until(lambda: blocked.is_set() and bool(self.visible_paths()),
                                 message='Slow cached hits waited for a full page')
                self.assertEqual(self.visible_paths(), self.matches)
                self.assertTrue(browser.searching)
                await browser.activate_entry(browser.tree.entries[provider.root / self.matches[0]])
                self.assertEqual(opened, [])
                self.assertNotIn(self.matches[0], self.visible_paths())
                self.assertIn('no longer available', browser.page_label.text)
                await browser.activate_entry(browser.tree.entries[provider.root / self.matches[1]])
                self.assertEqual([row['path'] for row in opened], [self.matches[1]])
                self.assertNotIn('cached', opened[0])
                self.assertTrue(browser.searching)
            finally:
                release.set()
            await self.finish_tasks()
            self.assertEqual(self.visible_paths(), self.matches[1:])

        with patch.object(provider, 'entry', side_effect=validate):
            self.loop.run_until_complete(check())

    def test_queued_saved_page_cannot_publish_after_query_location_or_close_changes(self):
        browser = self.browser
        for action in ('query', 'location', 'close'):
            with self.subTest(action=action):
                self.show_folder('')

                async def check():
                    delivered = self.loop.create_future()
                    current_tree = None

                    def invalidate():
                        nonlocal current_tree
                        if action == 'query':
                            browser.search.value = 'Keep'
                        elif action == 'location':
                            self.show_folder('Other')
                        else:
                            browser.stop()
                        current_tree = browser.tree

                    def search(provider, directory, query, *, cancelled, progress):
                        first = True

                        def publish(result):
                            nonlocal first
                            if query == 'Match' and first:
                                first = False
                                # Run the real queued UI callback immediately after invalidation.
                                self.loop.call_soon_threadsafe(invalidate)
                                progress(result)
                                self.loop.call_soon_threadsafe(
                                    lambda: delivered.set_result(browser.tree is current_tree))
                            else:
                                progress(result)

                        return self.search.search(provider, directory, query, cancelled=cancelled,
                                                  progress=publish)

                    browser.search.value = 'Match'
                    with patch.object(browser, 'resource_search', side_effect=search):
                        self.assertTrue(await asyncio.wait_for(delivered, 5))
                        await self.finish_tasks()
                    self.assertEqual(self.visible_paths(), ['Books/Keep.md'] if action == 'query' else [])

                self.loop.run_until_complete(check())

    def test_cached_link_or_changed_type_cannot_reach_context_actions(self):
        browser, provider = self.browser, self.provider
        path = self.matches[0]
        file = provider.root / path
        actions = []
        browser.on_item_actions = lambda row: actions.append(row)
        for replacement in ('link', 'folder'):
            with self.subTest(replacement=replacement):
                if file.is_dir():
                    file.rmdir()
                else:
                    file.unlink(missing_ok=True)
                file.write_text('original')
                row = dict(provider.entry(path), cached=True)
                file.unlink()
                if replacement == 'folder':
                    file.mkdir()
                else:
                    try:
                        file.symlink_to(provider.root / self.matches[1])
                    except OSError as error:
                        self.skipTest(str(error))
                browser.set_entries(provider, 'Books', [row], location=('Local', 'Books'))
                self.loop.run_until_complete(browser._select_row(browser.native_list.data[0]))
                self.assertEqual(actions, [])
                self.assertNotIn(path, self.visible_paths())

    def test_same_location_refresh_replays_recursive_search_without_an_index(self):
        from commonUtils.runtime.resources.selection import ResourceSelection

        provider = ResourceSelection(self.provider)
        self.assertFalse(self.search.supports(provider))

        def refresh():
            self.browser.set_entries(provider, '', provider.list(''), location=('Local', ''))

        async def check():
            refresh()
            self.browser.open_search()
            self.browser.search.value = 'Match'
            await self.finish_tasks()
            self.assertEqual(self.visible_paths(), self.matches)
            (self.provider.root / self.matches[0]).unlink()
            refresh()
            await self.finish_tasks()
            self.assertEqual(self.browser.search.value, 'Match')
            self.assertEqual(self.visible_paths(), self.matches[1:])

        self.loop.run_until_complete(check())
