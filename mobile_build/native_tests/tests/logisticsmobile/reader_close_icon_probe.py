"""Native Close artwork, accessibility and unsaved-edit acceptance checks."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import inspect
import json
from pathlib import Path
import traceback

from mobile.app import LogisticsMobile

BUNDLE = 'io.github.ispaure.logisticscloseiconqa'


class ReaderCloseIconProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'synthetic-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.check())

    async def press(self, button):
        if self.android:
            button._impl.native.performClick()
        else:
            button._impl.native.sendActionsForControlEvents(1 << 6)
        await asyncio.sleep(.5)

    async def choose(self, text):
        def walk(view):
            yield view
            for child in view.children:
                yield from walk(child)
        button = next(view for view in walk(self.body) if getattr(view, 'text', None) == text)
        # The exit control is tapped natively; invoke prompt actions and await
        # their asynchronous save handlers before asserting persistence.
        operation = button.on_press()
        if inspect.isawaitable(operation):
            await operation
        await asyncio.sleep(.4)

    def assert_close(self, view):
        button = view._reader_close_button
        assert button.control_icon == 'close'
        assert button.accessible_name == 'Close document'
        if self.android:
            assert self.native_host.adapter.impl.native_navigationview.getVisibility() == 8
            assert self.native_host.adapter._reader_action_bar_buttons[0] is button
            assert str(button._impl.native.getContentDescription()) == 'Close document'
            assert button._impl.native.getVisibility() == 0
        else:
            assert self.native_host.adapter.tabs_hidden()
            nav = self.native_host.adapter.navigation[self.native_host.destinations.index(self.native_host.state.destination)]
            assert nav.topViewController.navigationItem.hidesBackButton
            assert nav.topViewController.navigationItem.leadingItemGroups[0].barButtonItems[0] == button._native_reader_close_item
            assert button._native_reader_close_item.accessibilityLabel == 'Close document'
            assert button._impl.native.accessibilityLabel == 'Close document'
            assert button._impl.native.imageForState(0) is not None
        return button

    async def capture_stage(self, stage):
        (Path(self.paths.cache) / 'close-icon-stage.json').write_text(json.dumps({'stage': stage}))
        print('CLOSE_ICON_STAGE=' + stage, flush=True)
        await asyncio.sleep(12)

    async def check(self):
        result = {'success': False}
        try:
            self.android = type(self._impl).__module__.startswith('toga_android.')
            result['platform'] = 'android' if self.android else 'ios'
            await self.show_files()
            origin = self.body
            from commonUtils.runtime.resources.local import LocalFiles
            from features.text_editor.resources import LocalTextCopies
            path = self.private_root / 'Synthetic close safety.txt'
            path.write_text('Original saved text')
            copies = LocalTextCopies(LocalFiles(path.parent))
            assert await self.open_crypt(copies=copies, key=path.name)
            await asyncio.sleep(.8)
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Unsaved change to preserve'
            button = self.assert_close(owner.crypt_view)
            await self.capture_stage('edited-text')
            await self.press(button)
            assert owner.session.id in self.workspace.sessions
            assert path.read_text() == 'Original saved text'
            await self.choose('Keep editing')
            assert self.visible_reader() == owner.session.id
            assert owner.crypt_text.value == 'Unsaved change to preserve'
            result['x_prompts_and_keep_editing_retains_draft'] = True

            await self.press(self.assert_close(owner.crypt_view))
            await self.choose('Save and close')
            assert owner.session.id not in self.workspace.sessions
            assert path.read_text() == 'Unsaved change to preserve'
            assert self.body is origin
            result['x_save_commits_edits_and_returns_to_folder'] = True

            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Discard this edit'
            await self.press(self.assert_close(owner.crypt_view))
            await self.choose('Discard and close')
            assert owner.session.id not in self.workspace.sessions
            assert path.read_text() == 'Unsaved change to preserve'
            assert self.body is origin
            result['x_discard_preserves_saved_file'] = True

            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Retain after save conflict'
            path.write_text('External modification')
            await self.press(self.assert_close(owner.crypt_view))
            await self.choose('Save and close')
            assert owner.session.id in self.workspace.sessions
            assert owner.crypt_text.value == 'Retain after save conflict'
            assert path.read_text() == 'External modification'
            await self.choose('Keep editing')
            result['failed_save_keeps_document_and_edits'] = True
            await self.press(self.assert_close(owner.crypt_view))
            await self.choose('Discard and close')

            self.create_chosen_document('md')
            owner = self.editor_view
            owner.editor.value = '# Managed unsaved edit'
            await asyncio.sleep(.4)
            await self.press(self.assert_close(owner.document_view))
            await self.choose('Keep editing')
            assert owner.editor.value == '# Managed unsaved edit'
            await self.press(self.assert_close(owner.document_view))
            await self.choose('Save and close')
            assert owner.session.id not in self.workspace.sessions
            assert owner.document.snapshot.path.read_text() == '# Managed unsaved edit'
            result['managed_markdown_x_preserves_cancel_and_saves'] = True

            from .fixtures import make_books
            fixtures = self.private_root / 'close-fixtures'
            fixtures.mkdir(exist_ok=True)
            _, comic = make_books(fixtures)
            assert await self.open_download(path=comic)
            owner = self.readers.active
            owner.set_reading_mode(False)
            await asyncio.sleep(1)
            button = self.assert_close(owner.library_view)
            await self.capture_stage('comic')
            await self.press(button)
            assert owner.session.id not in self.workspace.sessions
            assert not self._document_tabs_hidden
            result['comic_x_closes_and_restores_navigation'] = True
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'close-icon-result.json').write_text(json.dumps(result, indent=2))
        print('CLOSE_ICON_RESULT=' + json.dumps(result), flush=True)


def main():
    return ReaderCloseIconProbe('Close Icon QA', BUNDLE)
