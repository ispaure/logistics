"""Recycled mobile list contracts, complete search and stale-event ownership."""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch, AsyncMock

import toga
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser


class RecycledBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        LogisticsMobile.storage_root = Path(self.temp.name)
        self.addCleanup(setattr, LogisticsMobile, 'storage_root', None)
        self.app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
        self.addCleanup(self.app.loop.close)
        self.addCleanup(self.app.main_window.close)
        self.opened = []
        self.browser = FileBrowser(open_file=self.opened.append)
        self.addCleanup(lambda: self.app.loop.run_until_complete(self.browser.close()))
        self.provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)

    def rows(self, count, prefix='file'):
        return [dict(path=f'{prefix}-{i:05d}.md', name=f'{prefix}-{i:05d}.md', directory=False)
                for i in range(count)]

    def test_ten_thousand_entries_allocate_no_row_widgets_or_population_timers(self):
        browser = self.browser
        viewport = browser.scroll_container()
        with patch.object(browser._loop, 'call_later', wraps=browser._loop.call_later) as timer:
            browser.set_entries(self.provider, '', self.rows(10005))
            self.assertIs(viewport, browser.widget)
            self.assertIn(browser.native_list, viewport.children)
            self.assertEqual(len(browser.native_list.data), 10005)
            self.assertFalse(browser.buttons)
            self.assertFalse(browser.items.children)
            timer.assert_not_called()
        last = browser.native_list.data[-1]
        self.app.loop.run_until_complete(browser._activate_row(last))
        self.assertEqual(self.opened[-1]['path'], 'file-10004.md')

    def test_native_tap_captures_selection_and_rejects_replaced_snapshot(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(2))
        browser.native_list._impl.simulate_selection(1)
        # Source replacement happens before the asynchronous handler runs.
        old = browser.native_list.data[1]
        browser.set_entries(self.provider, '', self.rows(2, 'new'))
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertFalse(self.opened)
        self.app.loop.run_until_complete(browser._activate_row(old))
        self.assertFalse(self.opened)
        browser.native_list._impl.simulate_selection(1)
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(self.opened[-1]['name'], 'new-00001.md')

    def test_search_sort_empty_state_and_selection_keep_exact_payload(self):
        browser = self.browser
        rows = self.rows(50)
        rows[3]['display_name'] = 'Human title'
        browser.set_entries(self.provider, '', rows)
        self.assertEqual(browser.native_list.data[3].title, 'Human title')
        browser.sort.value = 'Name Z–A'
        self.assertEqual(browser.native_list.data[0].entry.payload['path'], rows[-1]['path'])
        browser.search.value = 'file-00003'
        self.app.loop.run_until_complete(asyncio.sleep(.45))
        self.assertEqual(len(browser.native_list.data), 1)
        row = browser.native_list.data[0]
        self.app.loop.run_until_complete(browser.select(row.entry))
        self.assertIs(browser.native_list.selection, row)
        self.assertEqual(row.title, 'Human title')
        self.assertFalse(browser.buttons)
        browser.search.value = 'absent'
        self.app.loop.run_until_complete(asyncio.sleep(.45))
        self.assertFalse(browser.native_list.data)
        self.assertIn(browser.empty_label, browser.widget.children)
        self.assertEqual(browser.empty_label.text, 'No matching items.')
        browser.close_search()
        self.app.loop.run_until_complete(asyncio.sleep(.45))
        self.assertEqual(len(browser.native_list.data), 50)
        self.assertIn(browser.native_list, browser.widget.children)

    def test_recursive_search_keeps_all_matches_and_full_path_identity(self):
        browser = self.browser
        matches = [dict(path=f'sub/match-{i:05d}.md', name=f'match-{i:05d}.md', directory=False)
                   for i in range(10005)]
        provider = self.provider
        provider.list = lambda folder, cancelled: matches if folder == 'sub' else [dict(path='sub', name='sub', directory=True)]
        browser.set_entries(provider, '', provider.list('', cancelled=lambda: False))
        browser.search.value = 'match'
        self.app.loop.run_until_complete(browser._search_subfolders(browser.search_epoch, browser.search_cancelled))
        self.assertEqual(len(browser.native_list.data), 10005)
        row = browser.native_list.data[-1]
        self.assertEqual(row.title, 'match-10004.md')
        self.app.loop.run_until_complete(browser._activate_row(row))
        self.assertEqual(self.opened[-1]['path'], 'sub/match-10004.md')

    def test_folder_taps_and_busy_guard_keep_existing_navigation(self):
        browser = self.browser
        opened = AsyncMock()
        browser.on_open_folder = opened
        row = dict(path='Shelf', name='Shelf', directory=True)
        browser.set_entries(self.provider, '', [row])
        self.assertTrue(browser.native_list.data[0].folder)
        browser.navigation_busy = True
        self.app.loop.run_until_complete(browser.activate_entry(browser.entries[0]))
        opened.assert_not_awaited()
        browser.navigation_busy = False
        self.app.loop.run_until_complete(browser.activate_entry(browser.entries[0]))
        opened.assert_awaited_once_with(row)

    def test_tiles_roundtrip_preserves_selection_and_uses_one_list_viewport(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(5))
        entry = browser.entries[2]
        self.app.loop.run_until_complete(browser.select(entry))
        for _ in range(2):
            browser.show_tiles()
            self.assertIn(browser._tile_scroll, browser.widget.children)
            self.assertFalse(browser.native_list.data)
            self.assertEqual(len(browser.buttons), 5)
            browser.show_list()
            self.assertIn(browser.native_list, browser.widget.children)
            self.assertNotIn(browser._tile_scroll, browser.widget.children)
            self.assertIs(browser.native_list.selection.entry, entry)
            self.assertFalse(browser.buttons)

    def test_thumbnails_are_requested_only_for_visible_rows_and_cannot_return_after_stop(self):
        browser = self.browser
        browser.thumbnail = lambda *args: b''
        browser.set_entries(self.provider, '', self.rows(500))
        gate = asyncio.Event()
        called = []
        async def load(entry, target, epoch, cancelled):
            called.append(entry.identity)
            await gate.wait()
            if not browser.closed and epoch == browser.epoch:
                target.image = toga.Image(src=b'fake')
        browser._load_thumbnail = load
        self.assertFalse(browser.tasks)
        row = browser.native_list.data[7]
        browser.native_list.row_visible(7)
        browser.native_list.row_visible(7)
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertEqual(called, [row.entry.identity])
        browser.stop()
        gate.set()
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertFalse(browser.native_list.data)
        self.assertFalse(browser.native_list.selection)
        self.assertFalse(browser.tree)
        self.assertFalse(browser.buttons)

    def test_cached_images_decode_only_when_visible_and_reuse_native_thumbnails(self):
        from base64 import b64decode
        from logisticsmobile.hub_icons import ICONS
        browser = self.browser
        browser.thumbnail = lambda *args: b''
        browser.set_entries(self.provider, '', self.rows(500))
        encoded = b64decode(ICONS['documents'])
        browser.icons.update(((entry.identity, entry.revision), encoded) for entry in browser.entries)
        with patch('logisticsmobile.browser_ui.toga.Image', wraps=toga.Image) as decode:
            browser.render()
            self.assertEqual(decode.call_count, 0)
            browser.native_list.row_visible(7)
            self.assertEqual(decode.call_count, 1)
            image = browser.native_list.data[7].icon
            browser.render()
            browser.native_list.row_visible(7)
            self.assertEqual(decode.call_count, 1)
            self.assertIs(browser.native_list.data[7].icon, image)
        browser.stop()
        self.assertFalse(browser._decoded_thumbnails)


    def test_ios_thumbnail_changes_update_one_cell_and_reject_retired_rows(self):
        import ast
        import sys
        from unittest.mock import Mock
        path = Path(__file__).parents[2] / 'Python/logisticsmobile/recycled_file_list_ios.py'
        source = ast.parse(path.read_text())
        owner = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'IOSFileList')
        method = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'source_change')
        namespace = {}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
        image = object()
        row = SimpleNamespace(index=0, icon=SimpleNamespace(_impl=SimpleNamespace(native=image)))
        cell = SimpleNamespace(imageView=SimpleNamespace(image=None), setNeedsLayout=Mock())
        native = Mock()
        native.cellForRowAtIndexPath.return_value = cell
        host = SimpleNamespace(interface=SimpleNamespace(data=[row]), native=native)
        libs = SimpleNamespace(NSIndexPath=SimpleNamespace(indexPathForRow=lambda *args, **kwargs: 0))
        with patch.dict(sys.modules, {'toga_iOS.libs': libs}):
            namespace['source_change'](host, item=row)
            self.assertIs(cell.imageView.image, image)
            native.reloadData.assert_not_called()
            native.reset_mock()
            host.interface.data = [object()]
            namespace['source_change'](host, item=row)
            native.cellForRowAtIndexPath.assert_not_called()


    def test_file_activation_skips_metadata_and_rechecks_navigation_after_callback(self):
        browser = self.browser
        browser.details = lambda *args: self.fail('Opening must not fetch metadata')
        browser.set_entries(self.provider, '', self.rows(2))
        old = browser.native_list.data[1]
        browser.on_selected = lambda payload: browser.set_entries(self.provider, '', self.rows(1, 'new')) if payload else None
        self.app.loop.run_until_complete(browser._activate_row(old))
        self.assertFalse(self.opened)

    def test_context_selection_does_not_open_and_rejects_old_rows(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(3))
        row = browser.native_list.data[2]
        browser.native_list.on_primary_action(row=row)
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertIs(browser.native_list.selection, row)
        self.assertFalse(self.opened)
        browser.set_entries(self.provider, '', self.rows(1, 'new'))
        browser.native_list.on_primary_action(row=row)
        self.app.loop.run_until_complete(asyncio.sleep(0))
        self.assertIsNone(browser.native_list.selection)

    def test_decoded_list_thumbnails_are_bounded_and_evictions_restore_shared_icons(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100))
        from logisticsmobile.recycled_file_list import file_list_icon
        from logisticsmobile.hub_icons import ICONS
        from base64 import b64decode
        for row in browser.native_list.data:
            browser._set_row_thumbnail(row, toga.Image(src=b64decode(ICONS['documents'])))
        self.assertEqual(len(browser._list_thumbnail_rows), 64)
        self.assertEqual(sum(row.thumbnail for row in browser.native_list.data), 64)
        for row in list(browser.native_list.data)[:36]:
            self.assertIs(row.icon, file_list_icon(False))
        browser.stop()
        self.assertFalse(browser._list_thumbnail_rows)
