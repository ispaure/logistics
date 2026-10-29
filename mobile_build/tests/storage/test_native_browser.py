
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from mobile.app import LogisticsMobile
from mobile.browser_ui import FileBrowser
import toga
from commonUtils.ui.native_browser import NativeBrowser


class NativeBrowserTests(unittest.TestCase):
    def test_native_search_callback_recurses_without_running_loop_context(self):
        from services.documents.locations import CollectionFiles
        with TemporaryDirectory() as directory:
            LogisticsMobile.storage_root = Path(directory)
            self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            provider = CollectionFiles(Path(directory))
            (provider.root / 'nested' / 'deep').mkdir(parents=True)
            (provider.root / 'nested' / 'deep' / 'Needle.md').write_text('nested')
            browser = FileBrowser()
            try:
                browser.set_entries(provider, '', provider.list(), location=('Local files', ''))
                # Native synchronous callbacks can run between asyncio dispatches.
                browser.search.value = 'needle'
                async def finish():
                    for _ in range(100):
                        await asyncio.sleep(.01)
                        if any(entry.payload['path'].endswith('Needle.md') for entry in browser.entries):
                            return
                    self.fail('Typing in search did not discover the nested local file')
                app.loop.run_until_complete(finish())
                self.assertEqual([entry.payload['path'] for entry in browser.entries],
                                 ['nested/deep/Needle.md'])
                browser.close_search()
                app.loop.run_until_complete(asyncio.sleep(.45))
                self.assertEqual([entry.payload['path'] for entry in browser.entries], ['nested'])
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
