"""Disposable QA launcher for native recycling; never a production entry point."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback

import toga
from toga.style import Pack
from mobile.browser_ui import FileBrowser

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
            if android:
                assert native.getDivider() is not None
                assert native.getDividerHeight() > 0
                from mobile.palette import android_palette, argb
                colors = android_palette(native.getResources().getConfiguration().uiMode & 0x30 == 0x20)
                assert native.getDivider().getDrawable().getColor() == argb(colors['border'])
            result['platform'] = 'android' if android else 'ios'
            result['initial_visible'] = int(native.getChildCount()) if android else len(native.visibleCells)
            assert 0 < result['initial_visible'] < 100, result
            assert not browser.buttons and not browser.items.children
            browser.native_list.scroll_to_bottom()
            await asyncio.sleep(.7)
            if android:
                first = native.getFirstVisiblePosition()
                top = native.getChildAt(0).getTop()
                native.setVerticalPosition(native.getVerticalPosition())
                await asyncio.sleep(.3)
                assert native.getFirstVisiblePosition() == first
                assert native.getChildAt(0).getTop() == top
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
            from mobile.hub_icons import ICONS
            fixture_image = b64decode(ICONS['documents'])
            browser.thumbnail = lambda *args: fixture_image
            browser.set_entries(self.provider, '', self.rows[:200])
            await asyncio.sleep(1)
            result['thumbnail_rows'] = sum(row.thumbnail for row in browser.native_list.data)
            assert 0 < result['thumbnail_rows'] <= 64, result
            # The resume lock replaces the entire window root and later
            # restores it. UIKit may retain cells rather than request them anew.
            browser.thumbnail = None
            browser.set_entries(self.provider, '', [dict(path=f'Folder-{i:03d}',
                name=f'Folder-{i:03d}', directory=True) for i in range(100)])
            await asyncio.sleep(.3)
            snapshot = browser.native_list.data
            for _ in range(3):
                content = self.main_window.content
                self.main_window.content = toga.Box(children=[toga.Label('Synthetic lock screen')], style=Pack(flex=1))
                await asyncio.sleep(.2)
                self.main_window.content = content
                await asyncio.sleep(.3)
                assert browser.native_list.data is snapshot
                if android:
                    assert native.getCount() == 100
                else:
                    assert len(native.visibleCells) > 0
                    for cell in native.visibleCells:
                        path = native.indexPathForCell(cell)
                        assert cell.textLabel.text == browser.native_list.data[path.row].title
                        assert cell.imageView.image is not None
                        assert cell.accessibilityLabel
            result['retained_root_restore'] = True
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
