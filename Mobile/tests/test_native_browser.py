import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser
import toga
from commonUtils.ui.native_browser import NativeBrowser


class NativeBrowserTests(unittest.TestCase):
    def test_mobile_large_folders_bound_native_rows_and_controls_precede_rows(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            browser = FileBrowser(bounded_pages=True)
            provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
            rows = [dict(path=f'{index}.txt', name=f'{index}.txt', directory=index % 2 == 0, size=index)
                    for index in range(41)]
            try:
                for mode in ('List', 'Tiles'):
                    browser.mode = mode
                    browser.set_entries(provider, '', rows[:40])
                    self.assertEqual(len(browser.buttons), 40)
                    self.assertNotIn(browser.paging, browser.widget.children)
                    self.assertEqual(browser.page_label.text, '')
                    browser.set_entries(provider, '', rows)
                    self.assertTrue(browser.next.enabled)
                    self.assertLess(browser.widget.children.index(browser.paging),
                                    browser.widget.children.index(browser.items))
                    browser.next_page()
                    self.assertEqual(len(browser.buttons), 1)
                    last = browser.entries[-1]
                    self.assertIn(last.identity, browser.buttons)
                    if mode == 'List':
                        controls = browser.items.children[0].children[0]
                        self.assertEqual([child for child in controls.children if isinstance(child, toga.Button)],
                                         [browser.buttons[last.identity]])
                        self.assertEqual(browser.items.children[0].children[0].children[1],
                                         browser.buttons[last.identity])
                    browser.previous_page()
                    self.assertEqual(len(browser.buttons), 40)
                for row in browser.items.children:
                    glyph = row.children[0].children[0]
                    self.assertIsInstance(glyph, toga.ImageView)
                    self.assertIn(glyph.browser_entry_kind, ('folder', 'file'))

            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                app.loop.close()

    def test_selection_highlight_survives_layout_and_paging_without_checkmark(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            browser = FileBrowser()
            provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
            rows = [dict(path=f'{index}.md', name=f'{index}.md', directory=False, size=index)
                    for index in range(501)]
            async def check():
                browser.set_entries(provider, '', rows)
                selected, other = browser.entries[:2]
                await browser.select(selected)
                for mode in ('List', 'Tiles'):
                    browser.mode = mode
                    browser.render()
                    self.assertEqual(browser.buttons[selected.identity].text, selected.label)
                    self.assertEqual(browser.entry_rows[selected.identity]._impl._surface_roles[0], 'hover')
                    self.assertEqual(browser.entry_rows[other.identity]._impl._surface_roles[0], 'surface')
                    browser.next_page()
                    browser.previous_page()
                    self.assertEqual(browser.entry_rows[selected.identity]._impl._surface_roles[0], 'hover')
                    await browser.select(other)
                    self.assertFalse(any(button.text.startswith('✓') for button in browser.buttons.values()))
                    self.assertEqual(browser.entry_rows[selected.identity]._impl._surface_roles[0], 'surface')
                    await browser.select(selected)
            try:
                app.loop.run_until_complete(check())
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                app.loop.close()

    def test_recursive_search_keeps_all_matches_beyond_ten_thousand(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            calls = []
            matches = [dict(path=f'sub/match-{i:05d}.txt', name=f'match-{i:05d}.txt', directory=False, size=1)
                       for i in range(10005)]
            def listing(folder, *, cancelled):
                calls.append(folder)
                return matches if folder == 'sub' else [dict(path='sub', name='sub', directory=True)]
            provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path, list=listing)
            opened = []
            browser = FileBrowser(open_file=opened.append)
            async def check():
                browser.set_entries(provider, '', listing('', cancelled=lambda: False))
                browser.search.value = 'match'
                await browser._search_subfolders(browser.search_epoch, browser.search_cancelled)
                self.assertEqual(len(browser.entries), 10005)
                self.assertIn('sub', calls)
                browser.page = (len(browser.entries) - 1) // browser.page_size
                browser.render()
                self.assertEqual(len(browser.buttons), 10_005 % browser.page_size)
                self.assertIn('/virtual/sub/match-10004.txt', [str(key) for key in browser.buttons])
                self.assertFalse(browser.next.enabled)
                for mode in ('List', 'Tiles'):
                    browser.mode = mode
                    browser.render()
                    button = browser.buttons[Path('/virtual/sub/match-10004.txt')]
                    self.assertEqual(button.text, 'match-10004.txt')
                    await button.on_press()
                    self.assertEqual(opened[-1]['path'], 'sub/match-10004.txt')
                    if mode == 'List':
                        self.assertFalse(any(isinstance(child, toga.Label)
                            for row in browser.items.children for child in row.children[0].children))
            try:
                app.loop.run_until_complete(check())
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                app.loop.close()

    def test_views_pagination_info_and_stale_thumbnail(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
            async def check():
                provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
                rows = [dict(path=f'{index}.txt', name=f'{index}.txt', directory=False, size=index) for index in range(30)]
                selected = []
                browser = NativeBrowser(selected=selected.append, details=lambda row, cancelled: [('Title', 'Shared provider title')])
                browser.set_entries(provider, '', rows)
                self.assertNotIn(browser.search_panel, browser.widget.children)
                browser.search_button.on_press()
                self.assertIn(browser.search_panel, browser.widget.children)
                self.assertEqual(browser.search_panel.children[0], browser.search)
                self.assertNotIn(browser.sort, browser.search_panel.children)
                browser.search.value = 'no-match'
                browser.close_search_button.on_press()
                self.assertEqual(browser.search.value, '')
                self.assertNotIn(browser.search_panel, browser.widget.children)
                self.assertEqual(len(browser.buttons), 24)
                browser.next_page()
                self.assertEqual(len(browser.buttons), 6)
                browser.show_tiles()
                self.assertEqual(len(browser.buttons), 16)
                await browser.buttons[browser.entries[0].identity].on_press()
                self.assertEqual(selected[-1]['path'], '0.txt')
                self.assertIn('Size: 0 B', [child.text for child in browser.info.children])
                self.assertIn('Title: Shared provider title', [child.text for child in browser.info.children])
                browser.icons[(Path('/virtual/0.txt'), None)] = b'outdated'
                browser.set_entries(provider, '', rows)
                self.assertEqual(browser.icons, {})
                gate = asyncio.Event()
                async def slow(entry, image, epoch, cancelled):
                    await gate.wait()
                    if epoch == browser.epoch and not cancelled.is_set():
                        browser.icons[(entry.identity, entry.revision)] = b'stale'
                browser._load_thumbnail = slow
                browser.thumbnail = lambda *args: b'fixture'
                browser.render()
                browser.stop()
                gate.set()
                await browser.close()
                self.assertFalse(browser.icons)
                self.assertFalse(browser.buttons)
                self.assertFalse(browser.tasks)
                self.assertFalse(browser.info.children)
            try:
                app.loop.run_until_complete(check())
            finally:
                app.main_window.close()
                app.loop.close()
