"""Disposable QA launcher for native recycling; never a production entry point."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback

import toga
from toga.style import Pack
from logisticsmobile.browser_ui import FileBrowser

# The locally built Logistics simulator launcher names this delegate explicitly.
if toga.platform.current_platform == 'iOS':
    from toga_iOS.app import PythonAppDelegate
    class LogisticsSceneAppDelegate(PythonAppDelegate):
        pass


class Probe(toga.App):
    def startup(self):
        from commonUtils.ui.native.event_loop import bind_cooperative_loop
        bind_cooperative_loop(self.loop)
        self.active_host = True
        self.opened = []
        self.browser = FileBrowser(open_file=self.opened.append)
        self.provider = SimpleNamespace(root=Path('/virtual'), relative=lambda path: path)
        self.rows = [dict(path=f'folder/file-{i:05d}.md', name=f'file-{i:05d}.md', directory=False)
                     for i in range(10005)]
        self.browser.set_entries(self.provider, '', self.rows)
        self.main_window = toga.MainWindow(title='Recycled list QA', content=self.browser.scroll_container())
        self.main_window.show()

    def on_running(self):
        if not getattr(self, 'probe_started', False):
            self.probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False, count=10005)
        output = Path(self.paths.cache) / 'recycled-list-result.json'
        try:
            await asyncio.sleep(1)
            browser = self.browser
            native = browser.native_list._impl.native
            android = browser.native_list.factory.DetailedList.__module__.startswith('toga_android.')
            result['platform'] = 'android' if android else 'ios'
            result['initial_visible'] = int(native.getChildCount()) if android else len(native.visibleCells)
            assert 0 < result['initial_visible'] < 100, result
            assert not browser.buttons and not browser.items.children
            browser.native_list.scroll_to_bottom()
            await asyncio.sleep(.7)
            if android:
                position = native.getLastVisiblePosition()
                cell = native.getChildAt(position - native.getFirstVisiblePosition())
                native.performItemClick(cell, position, position)
                result['created_rows'] = int(native.getCreatedRowCount())
                assert result['created_rows'] < 100, result
            else:
                from toga_iOS.libs import NSIndexPath
                path = NSIndexPath.indexPathForRow(10004, inSection=0)
                native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
                browser.native_list._impl.native_controller.tableView_didSelectRowAtIndexPath_(native, path)
                result['final_visible'] = len(native.visibleCells)
                assert result['final_visible'] < 100, result
            await asyncio.sleep(.1)
            assert self.opened[-1]['path'] == 'folder/file-10004.md', self.opened
            result['last_tap'] = self.opened[-1]['path']
            browser.search.value = 'file-09999'
            await asyncio.sleep(.7)
            assert len(browser.native_list.data) == 1
            assert browser.native_list.data[0].title == 'file-09999.md'
            result['search'] = True
            browser.close_search()
            await asyncio.sleep(.7)
            browser.sort.value = 'Name Z–A'
            assert browser.native_list.data[0].title == 'file-10004.md'
            old = browser.native_list.data[0]
            browser.set_entries(self.provider, '', [dict(path='New', name='New', directory=True)])
            await browser._activate_row(old)
            assert len(self.opened) == 1
            result['stale_tap_rejected'] = True
            await asyncio.sleep(.3)
            result['replacement_visible'] = int(native.getChildCount()) if android else len(native.visibleCells)
            from base64 import b64decode
            from logisticsmobile.hub_icons import ICONS
            fixture_image = b64decode(ICONS['documents'])
            browser.thumbnail = lambda *args: fixture_image
            browser.set_entries(self.provider, '', self.rows[:200])
            await asyncio.sleep(1)
            result['thumbnail_rows'] = sum(row.thumbnail for row in browser.native_list.data)
            assert 0 < result['thumbnail_rows'] <= 64, result
            browser.stop()
            await asyncio.sleep(.3)
            assert len(browser.native_list.data) == 0
            if android:
                assert native.getCount() == 0
                assert native.getChildCount() == 0
            else:
                assert native.numberOfRowsInSection(0) == 0
            result['cleared'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        output.write_text(json.dumps(result, indent=2))
        print('RECYCLED_LIST_RESULT=' + json.dumps(result), flush=True)


def main():
    return Probe('Recycled list QA', 'io.github.ispaure.logisticsmobile.listqa')
