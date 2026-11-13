"""Persistent local search shares desktop terms without persisting private names."""

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
from unittest.mock import patch

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

    def test_saved_page_is_displayed_before_later_validation_with_writer_held(self):
        browser, provider = self.browser, self.provider
        self.show_folder('')
        # The saved first page will contain a deleted entry.
        (provider.root / self.matches[0]).unlink()
        blocked, release = Event(), Event()
        entry = provider.entry

        def validate(path):
            if path == self.matches[50]:
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
                    self.assertEqual(self.visible_paths(), self.matches[1:50])
                    self.assertIn('Searching', browser.page_label.text)
                finally:
                    release.set()
                await wait_until(lambda: self.visible_paths() == self.matches[1:]
                                 and not browser.searching,
                                 message='Warm search did not finish while the writer was held')
                browser.close_search()
            await self.finish_tasks()

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
