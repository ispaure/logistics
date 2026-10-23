"""Persistent local search shares desktop terms without persisting private names."""
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
                app.loop.close()
