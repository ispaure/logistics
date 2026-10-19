import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser
import toga
from commonUtils.ui.native_browser import NativeBrowser


class NativeBrowserTests(unittest.TestCase):
    def test_reused_rows_update_actions_icons_and_scrub_private_names(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            self.addCleanup(app.loop.close)
            self.addCleanup(app.main_window.close)
            opened = []
            browser = FileBrowser(open_file=opened.append, open_folder=opened.append)
            self.addCleanup(browser.stop)
            provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
            rows = [dict(path=f'private-{i:02d}.md', name=f'private-{i:02d}.md', directory=False)
                    for i in range(45)]
            browser.set_entries(provider, '', rows, location=('Private', ''))
            slots = list(browser._list_slots)
            self.assertEqual(len(slots), 45)
            old = browser.entries[0]
            browser.set_entries(provider, '', rows[40:], location=('Private', 'next'))
            self.assertEqual(browser._list_slots, slots[:5])
            button = next(iter(browser.buttons.values()))
            app.loop.run_until_complete(button.on_press())
            self.assertEqual(opened, [rows[40]])
            self.assertTrue(all(slot[3].text == '' and slot[3].accessible_name == ''
                                for slot in slots[5:]))
            fresh = dict(path='new-folder', name='new-folder', directory=True)
            browser.set_entries(provider, '', [fresh], location=('Other', ''))
            self.assertIs(browser._list_slots[0][0], slots[0][0])
            self.assertEqual(slots[0][2].browser_entry_kind, 'folder')
            self.assertIn(slots[0][4], slots[0][1].children)
            app.loop.run_until_complete(browser._select_pressed(old, slots[0][3]))
            self.assertEqual(opened, [rows[40]])  # A delayed old entry cannot activate.
            app.loop.run_until_complete(slots[0][3].on_press())
            self.assertEqual(opened[-1], fresh)
            for mode in ('Tiles', 'List', 'Tiles', 'List'):
                browser.mode = mode
                browser.render()
                self.assertEqual(len(browser.items.children), 1)
            browser.stop()
            self.assertFalse(browser._list_slots)
            self.assertFalse(browser.entry_rows)
            self.assertTrue(all(slot[3].text == '' and slot[3].accessible_name == '' for slot in slots))

    def test_mobile_list_and_tiles_show_every_item_without_paging(self):
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            browser = FileBrowser()
            provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
            rows = [dict(path=f'{index}.txt', name=f'{index}.txt', directory=index % 2 == 0, size=index)
                    for index in range(301)]
            try:
                for mode in ('List', 'Tiles', 'List'):
                    browser.mode = mode
                    browser.set_entries(provider, '', rows)
                    self.assertEqual(len(browser.buttons), len(rows))
                    self.assertEqual(set(browser.buttons), {entry.identity for entry in browser.entries})
                    self.assertFalse(browser.previous.enabled)
                    self.assertFalse(browser.next.enabled)
                    self.assertNotIn(browser.paging, browser.widget.children)
                    self.assertEqual(browser.page_label.text, '')
                    if mode == 'List':
                        self.assertEqual(len(browser.items.children), len(rows))
                        controls = browser.items.children[0].children[0]
                        first = browser.buttons[browser.entries[0].identity]
                        self.assertEqual(controls.children[1], first)
                browser.set_entries(provider, '', [])
                self.assertFalse(browser.buttons)
                self.assertFalse(browser._list_slots)
                self.assertEqual(browser.page_size, 1)  # Empty folders do not divide by zero.
            finally:
                app.loop.run_until_complete(browser.close())
                app.main_window.close()
                app.loop.close()

    def test_selection_highlight_survives_layout_without_checkmark(self):
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
                    browser.render()
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
                # Separate the recursive-search completeness contract from the
                # full-folder rendering check above, without allocating 10k UI rows.
                with patch.object(browser, 'render'):
                    await browser._search_subfolders(browser.search_epoch, browser.search_cancelled)
                self.assertEqual(len(browser.entries), 10005)
                self.assertIn('sub', calls)
                self.assertEqual(browser.page_size, 10005)
                browser.search.value = 'match-10004'
                browser.render()
                self.assertEqual(len(browser.buttons), 1)
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
