"""Cooperative mobile row creation, complete search and visible-page ownership."""
import asyncio
import heapq
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import toga
from unittest.mock import patch

from logisticsmobile.app import LogisticsMobile
from logisticsmobile.browser_ui import FileBrowser, sync_browser_population
from commonUtils.ui.native_browser import query_entries


class PopulationClock:
    """Drive UI timers deterministically; ordinary async work uses the app loop."""
    def __init__(self, loop):
        self.create_task = loop.create_task
        self.now = 0
        self.events = []
        self.sequence = 0

    def time(self):
        return self.now

    def call_later(self, delay, callback):
        class Handle:
            cancelled_flag = False
            def cancel(self):
                self.cancelled_flag = True
            def cancelled(self):
                return self.cancelled_flag
            def when(self):
                return due
        due = self.now + delay
        handle = Handle()
        self.sequence += 1
        heapq.heappush(self.events, (due, self.sequence, handle, callback))
        return handle

    def tick(self):
        while self.events:
            due, _, handle, callback = heapq.heappop(self.events)
            if not handle.cancelled():
                self.now = max(self.now, due)
                callback()
                return True
        return False

    def drain(self):
        for _ in range(1000):
            if not self.tick():
                return
        raise AssertionError('Population did not finish')


class ProgressiveBrowserTests(unittest.TestCase):
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
        self.clock = PopulationClock(self.app.loop)
        self.browser._loop = self.clock
        timer = patch('logisticsmobile.browser_ui.monotonic', self.clock.time)
        timer.start()
        self.addCleanup(timer.stop)
        self.scroll = self.browser.scroll_container()
        self.app.routes.body().add(self.scroll)
        self.provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)

    def rows(self, count, prefix='file'):
        return [dict(path=f'{prefix}-{i:05d}.md', name=f'{prefix}-{i:05d}.md', directory=False)
                for i in range(count)]

    def near_bottom(self):
        self.scroll.vertical_position = self.scroll.max_vertical_position - 1

    def test_idle_population_yields_between_small_slices_without_sorting_or_rebuilding(self):
        browser = self.browser
        rows = self.rows(125)
        browser.set_entries(self.provider, '', rows)
        first_slots = list(browser._list_slots)
        self.assertEqual(len(first_slots), 40)
        self.assertEqual(len(browser.entries), 125)
        with patch('commonUtils.ui.native_browser.query_entries', wraps=query_entries) as query:
            self.assertTrue(self.clock.tick())  # No scroll needed.
            self.assertEqual(len(browser.buttons), 42)
            self.assertIsNotNone(browser._append_handle)
            self.assertGreater(browser._append_handle.when(), self.clock.now)
            self.assertEqual(browser._list_slots[:40], first_slots)
            self.clock.drain()
            self.assertEqual(len(browser.buttons), 125)
            query.assert_not_called()
        self.assertEqual(list(browser.buttons), [entry.identity for entry in browser.entries])
        self.app.loop.run_until_complete(list(browser.buttons.values())[-1].on_press())
        self.assertEqual(self.opened, [rows[-1]])

    def test_fast_scroll_uses_single_row_slices_and_preserves_scroll_and_controls(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(125))
        idle = browser._append_handle
        slots = list(browser._list_slots)
        self.near_bottom()
        pending = browser._append_handle
        self.assertTrue(idle.cancelled())
        self.near_bottom()
        self.assertIs(browser._append_handle, pending)
        self.clock.tick()
        self.assertEqual(len(browser.buttons), 41)
        self.assertEqual(browser._list_slots[:40], slots)
        self.assertEqual(self.scroll.vertical_position, self.scroll.max_vertical_position - 1)
        self.assertIs(self.scroll.content.children[0], browser.widget)
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 125)

    def test_scrolling_away_from_end_defers_idle_work_until_gesture_settles(self):
        self.browser.set_entries(self.provider, '', self.rows(100))
        self.near_bottom()
        self.scroll.vertical_position = 0
        self.clock.tick()
        self.assertEqual(len(self.browser.buttons), 40)
        self.clock.tick()
        self.assertGreater(len(self.browser.buttons), 40)

    def test_slow_native_slice_reduces_next_slice_and_leaves_more_ui_time(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100))
        populate = browser._populate_rows
        def expensive(*args, **kwargs):
            populate(*args, **kwargs)
            self.clock.now += .03  # Simulated native layout, not a timing threshold.
        with patch.object(browser, '_populate_rows', side_effect=expensive):
            self.clock.tick()
        self.assertEqual(browser._slice_size, 1)
        self.assertGreaterEqual(browser._append_handle.when() - self.clock.now, .06 - 1e-9)
        count = len(browser.buttons)
        self.clock.tick()
        self.assertEqual(len(browser.buttons), count + 1)

    def test_construction_budget_yields_after_one_expensive_row(self):
        from logisticsmobile.browser_ui import entry_icon
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100))
        def expensive_icon(*args, **kwargs):
            self.clock.now += .01
            return entry_icon(*args, **kwargs)
        with patch('logisticsmobile.browser_ui.entry_icon', side_effect=expensive_icon):
            self.clock.tick()
        self.assertEqual(len(browser.buttons), 41)

    def test_obsolete_provider_hold_does_not_stall_a_new_folder(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100, 'old'))
        with browser.population_paused():
            self.assertIsNone(browser._append_handle)
            # A newer read completes while an abandoned old read is still held.
            with browser.population_paused():
                browser.set_entries(self.provider, '', self.rows(100, 'new'))
            self.clock.drain()
            self.assertEqual(len(browser.buttons), 100)
            self.assertTrue(all(button.text.startswith('new') for button in browser.buttons.values()))

    def test_folder_activation_cancels_population_before_awaiting_new_listing(self):
        browser = self.browser
        browser.set_entries(self.provider, '', [
            dict(path='nested', name='nested', directory=True), *self.rows(100)])
        pending = browser._append_handle
        async def exercise():
            entered, release = asyncio.Event(), asyncio.Event()
            async def open_folder(row):
                entered.set()
                await release.wait()
                return False  # Failed navigation resumes the original folder.
            browser.on_open_folder = open_folder
            task = asyncio.ensure_future(next(iter(browser.buttons.values())).on_press())
            await entered.wait()
            try:
                self.assertTrue(pending.cancelled())
                self.clock.drain()
                self.assertEqual(len(browser.buttons), 40)
            finally:
                release.set()
                await task
            self.clock.drain()
            self.assertEqual(len(browser.buttons), 101)
        self.app.loop.run_until_complete(exercise())

    def test_render_sorts_and_filters_once_and_invalidates_for_new_query(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(101))
        for mode in ('List', 'Tiles'):
            browser.mode = mode
            with patch('commonUtils.ui.native_browser.query_entries', wraps=query_entries) as query:
                browser.render()
                self.assertEqual(query.call_count, 1)
        browser.mode = 'List'
        browser.render()
        pending = browser._append_handle
        browser.search.value = 'file-00100'
        self.assertTrue(pending.cancelled())
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 40)  # Old query cannot populate during debounce.
        browser.render()
        self.assertEqual([button.text for button in browser.buttons.values()], ['file-00100.md'])
        browser.search.value = ''
        browser.sort.value = 'Name Z–A'
        self.assertEqual(next(iter(browser.buttons.values())).text, 'file-00100.md')
        browser.folder_visible = lambda path, **kwargs: '00100' not in str(path)
        browser.render()
        self.assertEqual(next(iter(browser.buttons.values())).text, 'file-00099.md')

    def test_search_keeps_all_recursive_results_and_finds_an_unmounted_last_match(self):
        browser = self.browser
        matches = self.rows(10005, 'nested/match')
        def listing(folder, *, cancelled):
            return matches if folder == 'nested' else [dict(path='nested', name='nested', directory=True)]
        self.provider.list = listing
        browser.set_entries(self.provider, '', listing('', cancelled=lambda: False))
        browser.search.value = 'match'
        self.app.loop.run_until_complete(browser._search_subfolders(browser.search_epoch, browser.search_cancelled))
        self.assertEqual(len(browser.entries), 10005)
        self.assertLess(len(browser.buttons), 45)
        browser.search.value = 'match-10004'
        browser.render()
        self.assertEqual([button.text for button in browser.buttons.values()], ['match-10004.md'])
        self.app.loop.run_until_complete(next(iter(browser.buttons.values())).on_press())
        self.assertEqual(self.opened[-1]['path'], 'nested/match-10004.md')

    def test_pending_work_is_cancelled_on_navigation_stop_and_view_change(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100, 'private'), location=('Private', ''))
        pending = browser._append_handle
        old_slots = list(browser._list_slots)
        with browser.population_paused():
            self.assertTrue(pending.cancelled())
            self.clock.drain()
            self.assertEqual(len(browser.buttons), 40)
            browser.set_entries(self.provider, '', self.rows(1, 'new'), location=('Local', ''))
        self.clock.drain()
        self.assertEqual([button.text for button in browser.buttons.values()], ['new-00000.md'])
        self.assertTrue(all(slot[3].text == '' and slot[3].accessible_name == '' for slot in old_slots[1:]))
        browser.set_entries(self.provider, '', self.rows(100))
        pending = browser._append_handle
        browser.show_tiles()
        self.assertTrue(pending.cancelled())
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 100)
        browser.show_list()
        pending = browser._append_handle
        browser.stop()
        self.clock.drain()
        self.assertTrue(pending.cancelled())
        self.assertFalse(browser._list_entries)
        self.assertFalse(browser.buttons)
        self.assertFalse(browser.items.children)
        self.assertFalse(browser._list_slots)

    def test_tab_switch_and_back_pause_hidden_browser_and_resume_on_return(self):
        browser = self.browser
        self.app.show_view(toga.Box(children=[self.scroll]), destination='home', route='test-browser')
        browser.set_entries(self.provider, '', self.rows(100))
        pending = browser._append_handle
        self.app.select_destination('settings')
        self.app.native_host.activate('settings')
        self.assertTrue(pending.cancelled())
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 40)
        self.app.select_destination('home')
        self.app.native_host.activate('home')
        self.clock.tick()
        self.assertEqual(len(browser.buttons), 42)
        page = toga.Box()
        self.app.show_view(page, route='other', destination='home')
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 42)
        self.app.routes.back()
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 100)

    def test_inactive_app_and_detached_browser_do_not_populate(self):
        browser = self.browser
        browser.set_entries(self.provider, '', self.rows(100))
        browser._app.screen_privacy.inactive = True
        sync_browser_population(self.app)
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 40)
        browser._app.screen_privacy.inactive = False
        sync_browser_population(self.app)
        self.clock.tick()
        self.assertEqual(len(browser.buttons), 42)
        self.scroll.parent.remove(self.scroll)
        # The queued callback validates visibility even without a route hook.
        self.clock.drain()
        self.assertEqual(len(browser.buttons), 42)

    def test_local_browser_and_drawer_population_pauses_for_provider_reads(self):
        from logisticsmobile.workspace_navigation import FileDrawer
        self.app.loop.run_until_complete(self.app.show_files())
        drawer = FileDrawer(SimpleNamespace(app=self.app), 'files')
        self.addCleanup(drawer.browser.stop)
        self.addCleanup(self.app.file_browser.stop)
        for browser in (self.app.file_browser, drawer.browser):
            browser.set_entries(self.provider, '', self.rows(81))
            self.assertEqual(len(browser.buttons), 40)
            with browser.population_paused():
                self.assertIsNone(browser._append_handle)
                browser.set_entries(self.provider, '', self.rows(1))
            self.assertEqual(len(browser.buttons), 1)
