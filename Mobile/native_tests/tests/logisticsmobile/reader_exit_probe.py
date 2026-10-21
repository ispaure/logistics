"""Disposable native acceptance for the shared reader Close action."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from commonUtils.runtime.local_files import LocalFiles
from features.text_editor.resources import LocalTextCopies

BUNDLE = 'io.github.ispaure.logisticsreaderexitqa'


class ReaderExitProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('synthetic-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_exit_probe_started', False):
            self._exit_probe_started = True
            self.loop.create_task(self.check())

    async def check(self):
        result = dict(success=False)
        try:
            await self.show_files()
            origin = self.body
            path = self.private_root / 'Synthetic note.txt'
            path.write_text('Synthetic saved text')
            copies = LocalTextCopies(LocalFiles(path.parent))
            assert await self.open_crypt(copies=copies, key=path.name)
            await asyncio.sleep(.6)
            owner = self.private_sessions.active
            button = owner.crypt_view._reader_close_button
            assert button.control_icon == 'close'
            assert button.accessible_name == 'Close document'
            android = type(self._impl).__module__.startswith('toga_android.')
            result['platform'] = 'android' if android else 'ios'
            if android:
                assert self.native_host.adapter.impl.native_navigationview.getVisibility() == 8
                assert self.native_host.adapter._reader_action_bar_buttons[0] is button
                assert str(button._impl.native.getContentDescription()) == 'Close document'
                button._impl.native.performClick()
            else:
                assert self.native_host.adapter.tabs_hidden()
                controller = self.native_host.adapter.navigation[self.native_host.destinations.index('files')].topViewController
                assert controller.navigationItem.hidesBackButton
                assert controller.navigationItem.leadingItemGroups[0].barButtonItems[0] == button._native_reader_close_item
                assert button._native_reader_close_item.accessibilityLabel == 'Close document'
                assert button._impl.native.accessibilityLabel == 'Close document'
                button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.3)
            assert owner.session.id not in self.workspace.sessions
            assert self.body is origin
            if android:
                assert self.native_host.adapter.impl.native_navigationview.getVisibility() == 0
            else:
                assert not self.native_host.adapter.tabs_hidden()
            result['native_close_returns_to_folder_and_releases_slot'] = True
            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Synthetic unsaved change'
            self.routes.system_back()
            await asyncio.sleep(.2)
            assert owner.session.id in self.workspace.sessions
            assert self.body is not origin
            if android:
                self.routes.system_back()
            else:
                navigation = self.native_host.adapter.navigation[self.native_host.destinations.index('files')]
                navigation.popViewControllerAnimated(False)
                await asyncio.sleep(.2)
            assert owner.session.id not in self._reader_closing
            assert self.visible_reader() == owner.session.id
            assert owner.crypt_text.value == 'Synthetic unsaved change'
            result['back_prompts_and_cancelling_retains_draft'] = True
            owner.crypt_text.value = 'Synthetic saved text'
            self.routes.system_back()
            assert owner.session.id not in self.workspace.sessions
            assert self.body is origin
            result['back_closes_clean_reader'] = True
            from logisticsmobile.reader_lifecycle import scroll_position, restore_scroll
            path.write_text('\n'.join(f'Synthetic paragraph {i}' for i in range(200)))
            assert await self.open_crypt(copies=copies, key=path.name)
            await asyncio.sleep(.6)
            owner = self.private_sessions.active
            restore_scroll(owner.crypt_text, (0, 400))
            await asyncio.sleep(.2)
            assert scroll_position(owner.crypt_text)[1] >= 350
            self.routes.system_back()
            assert owner.session.id not in self.workspace.sessions
            assert await self.open_crypt(copies=copies, key=path.name)
            await asyncio.sleep(.5)
            assert scroll_position(self.private_sessions.active.crypt_text)[1] >= 350
            result['text_scroll_resumes_after_close'] = True
            self.routes.system_back()
            markdown = self.private_root / 'Synthetic reading.md'
            markdown.write_text('# Synthetic reading\n\n' + '\n\n'.join(
                f'Paragraph {i}. A synthetic passage for scroll restoration.' for i in range(200)))
            assert await self.open_crypt(copies=copies, key=markdown.name)
            await asyncio.sleep(.8)
            owner = self.private_sessions.active
            restore_scroll(owner.crypt_preview, (0, 400))
            await asyncio.sleep(.2)
            assert scroll_position(owner.crypt_preview)[1] >= 350
            self.routes.system_back()
            assert owner.session.id not in self.workspace.sessions
            result['markdown_saved_position'] = self.private_sessions.positions.get(owner.session.resource)
            restore_position = self.private_sessions.restore_text_position
            async def trace_restore(reader, position):
                result['markdown_restore_input'] = dict(position)
                await restore_position(reader, position)
                result['markdown_search_ready_on_restore'] = reader.crypt_preview_search.ready
                result['markdown_after_restore'] = scroll_position(reader.crypt_preview)
            self.private_sessions.restore_text_position = trace_restore
            assert await self.open_crypt(copies=copies, key=markdown.name)
            await asyncio.sleep(.8)
            owner = self.private_sessions.active
            result['markdown_restored_scroll'] = scroll_position(owner.crypt_preview)
            result['markdown_search_ready_final'] = owner.crypt_preview_search.ready
            result['markdown_dom'] = await owner.crypt_preview.evaluate_javascript(
                'JSON.stringify({y:window.scrollY,height:document.body.scrollHeight,ready:document.readyState})')
            assert scroll_position(owner.crypt_preview)[1] >= 350
            assert owner.crypt_preview_search.ready
            result['markdown_scroll_and_search_resume_after_close'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'reader-exit-result.json').write_text(json.dumps(result, indent=2))
        print('READER_EXIT_RESULT=' + json.dumps(result), flush=True)


def main():
    return ReaderExitProbe('Reader exit QA', BUNDLE)
