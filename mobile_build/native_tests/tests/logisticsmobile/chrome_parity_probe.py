"""Disposable native header and visible-row-action acceptance probe."""
import asyncio
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticschromeparityqa'


class ChromeParityProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'synthetic-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def check(self):
        result = {'success': False}
        try:
            self.create_chosen_document('md')
            owner = self.editor_view
            owner.editor.value = '# Synthetic header\n\nReadable content.'
            await asyncio.sleep(1)
            android = type(self._impl).__module__.startswith('toga_android.')
            result['platform'] = 'android' if android else 'ios'
            if android:
                adapter = self.native_host.adapter
                bar = self._impl.native.getSupportActionBar()
                assert bar.isShowing()
                assert owner.toolbar.parent is None
                assert owner.save_button in adapter._reader_action_bar_buttons
                frame = getattr(owner.document_view, '_workspace_frame', None)
                assert frame is None or frame.header.parent is None
                assert str(adapter._reader_action_bar_title.getText()) == owner.document.name
                for _ in range(2):
                    owner.save_button._impl.native.performClick()
                    await asyncio.sleep(.3)
                    assert owner.save_button not in adapter._reader_action_bar_buttons
                    owner.editor.value += '\nAnother line.'
                    await asyncio.sleep(.2)
                    assert owner.save_button in adapter._reader_action_bar_buttons
                result['header_save_transitions'] = True
                self.screen_privacy.saved_content = self.main_window.content
                self.adaptive.render()
                assert not bar.isShowing()
                assert str(adapter._reader_action_bar_title.getText()) == ''
                self.screen_privacy.saved_content = None
                self.adaptive.render()
                await asyncio.sleep(.4)
                assert bar.isShowing()
                result['lock_hides_document_chrome'] = True
                from .compact_reading_probe import epub_bytes
                from commonUtils.runtime.resources.documents import LocalDocuments
                fixture = Path(self.paths.cache) / 'synthetic.epub'
                fixture.write_bytes(epub_bytes())
                record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), fixture)
                await self.open_book(record['id'])
                reader = self.readers.active
                await asyncio.sleep(.5)
                assert reader.reader_header.parent is None
                assert bar.isShowing()
                reader.set_reading_mode(True)
                await asyncio.sleep(.4)
                assert not bar.isShowing()
                reader.set_reading_mode(False)
                await asyncio.sleep(.4)
                assert bar.isShowing()
                reader.set_reading_mode(True)
                result['epub_fullscreen_restores_header'] = True
            await asyncio.sleep(2)
            from mobile.browser_ui import FileBrowser
            from types import SimpleNamespace
            opened, actions = [], []
            browser = FileBrowser(open_file=opened.append, item_actions=actions.append)
            provider = SimpleNamespace(root=Path('/synthetic'), relative=lambda path: path)
            rows = [dict(path=f'file-{i:03}.md', name=f'file-{i:03}.md', directory=False) for i in range(100)]
            browser.set_entries(provider, '', rows)
            self.show_view(browser.scroll_container(), destination='files', route='parity-browser', title='Row actions QA')
            await asyncio.sleep(1)
            if android:
                assert not bar.isShowing()
                assert not adapter._reader_action_bar_active
                native = browser.native_list._impl.native
                cell = native.getChildAt(0)
                button = cell.getChildAt(cell.getChildCount() - 1)
                assert button.getVisibility() == 0
                button.performClick()
            else:
                native = browser.native_list._impl.native
                cell = native.visibleCells[0]
                button = cell.accessoryView
                from mobile.screen_privacy import native_value
                assert button is not None and native_value(button, 'isEnabled')
                button.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.3)
            assert len(actions) == 1 and not opened, (actions, opened)
            result['visible_action_selects_without_opening'] = True
            if android:
                native.performItemClick(cell, 0, 0)
            else:
                path = native.indexPathForCell(cell)
                native.selectRowAtIndexPath(path, animated=False, scrollPosition=0)
                browser.native_list._impl.native_controller.tableView_didSelectRowAtIndexPath_(native, path)
            await asyncio.sleep(.3)
            assert len(opened) == 1
            result['row_tap_opens'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'chrome-parity-result.json').write_text(json.dumps(result, indent=2))
        print('CHROME_PARITY_RESULT=' + json.dumps(result), flush=True)


def main():
    return ChromeParityProbe('Chrome parity QA', BUNDLE)
