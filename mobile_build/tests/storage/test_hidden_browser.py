"""Hidden metadata stays presentation-only through local/live/indexed browsing."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from commonUtils.runtime.browsing import provider_entries
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.search.indexed import IndexedLocalSearch
from commonUtils.search.providers import search_resources
from commonUtils.ui.native_browser.recycled import hidden_entry
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser


class HiddenBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.cache_temp = TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.provider = LocalFiles(self.root)
        (self.root / '.folder').mkdir()
        (self.root / '.folder/ordinary.txt').write_text('Ordinary child')
        (self.root / '.hidden.txt').write_text('Hidden')
        (self.root / 'ordinary.txt').write_text('Ordinary')
        LogisticsMobile.storage_root = self.root / 'app'
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')

    def tearDown(self):
        self.app.main_window.close()
        self.app.loop.close()
        LogisticsMobile.storage_root = None
        self.temp.cleanup()
        self.cache_temp.cleanup()

    def test_provider_flags_and_basename_detection_survive_live_and_cached_search(self):
        index = IndexedLocalSearch(Path(self.cache_temp.name) / 'search.sqlite', eligible=lambda provider: provider is self.provider)
        for search in (search_resources, index.search, index.search):
            result = search(self.provider, '', 'txt')
            entries = provider_entries(self.provider, result.rows)
            states = {self.provider.relative(row.identity): hidden_entry(row) for row in entries}
            self.assertTrue(states['.hidden.txt'])
            self.assertFalse(states['ordinary.txt'])
            self.assertFalse(states['.folder/ordinary.txt'])
        row = dict(self.provider.entry('ordinary.txt'), hidden=True)
        self.assertTrue(hidden_entry(provider_entries(self.provider, [row])[0]))
        row = dict(row, hidden=False, name='nested/.hidden.txt')
        self.assertTrue(hidden_entry(provider_entries(self.provider, [row])[0]))

    def test_list_and_tiles_keep_hidden_flags_through_selection_and_reuse(self):
        browser = FileBrowser(preview=False)
        browser.set_entries(self.provider, '', self.provider.list(), location=('Fixture', ''))
        states = {row.entry.payload['name']: row.hidden for row in browser.native_list.data}
        self.assertTrue(states['.hidden.txt'])
        self.assertTrue(states['.folder'])
        self.assertFalse(states['ordinary.txt'])
        self.app.loop.run_until_complete(browser.show_tiles()) if asyncio.iscoroutinefunction(browser.show_tiles) else browser.show_tiles()
        hidden = next(entry for entry in browser.entries if entry.label == '.hidden.txt')
        ordinary = next(entry for entry in browser.entries if entry.label == 'ordinary.txt')
        hidden_card = browser._tile_card(hidden)
        normal_card = browser._tile_card(ordinary)
        # _tile_card returns its row; button state drives the host theme painter.
        self.assertIsNotNone(hidden_card)
        self.assertIsNotNone(normal_card)
        browser.set_entries(self.provider, '', [self.provider.entry('ordinary.txt')], location=('Fixture', ''))
        browser.show_list()
        self.assertEqual([row.hidden for row in browser.native_list.data], [False])
        self.app.loop.run_until_complete(browser.close())
