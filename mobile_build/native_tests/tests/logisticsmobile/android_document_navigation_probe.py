"""Disposable Android navigation acceptance, driven by real adb Back events."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from features.text_editor.resources import LocalTextCopies
from mobile.app import LogisticsMobile


BUNDLE = 'io.github.ispaure.logisticsdocumenttabsqa'


class AndroidDocumentNavigationProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('synthetic-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_navigation_probe_started', False):
            self._navigation_probe_started = True
            self.loop.create_task(self.check())

    async def wait_until(self, predicate, message, timeout=12):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(.1)
        assert predicate(), message

    def ime_visible(self):
        from java import jclass
        insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(self._impl.native.getWindow().getDecorView())
        return bool(insets and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))

    def hide_keyboard(self):
        from android.content import Context
        activity = self._impl.native
        focused = activity.getCurrentFocus()
        if focused is not None:
            focused.clearFocus()
        decor = activity.getWindow().getDecorView()
        decor.setFocusableInTouchMode(True)
        decor.requestFocus()
        manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
        manager.hideSoftInputFromWindow(decor.getWindowToken(), 0)

    async def settle_keyboard(self):
        # An IME show/hide request can precede its WindowInsets notification.
        # Clean-document Back checks must start after that native transition.
        self.hide_keyboard()
        await asyncio.sleep(.4)
        self.hide_keyboard()
        await self.wait_until(lambda: not self.ime_visible(), 'IME did not hide')
        await asyncio.sleep(.4)

    async def action(self, name, action='back'):
        """The external driver injects OS input, then acknowledges this token."""
        self.sequence += 1
        self.state.update(sequence=self.sequence, phase=name, action=action)
        self.publish()
        command = Path(self.paths.cache) / 'document-navigation-command'
        async with asyncio.timeout(90):
            while not command.exists() or command.read_text().strip() != str(self.sequence):
                await asyncio.sleep(.1)
        await asyncio.sleep(.5)

    def publish(self):
        (Path(self.paths.cache) / 'document-navigation-state.json').write_text(json.dumps(self.state, indent=2))

    def assert_tabs(self, hidden):
        adapter = self.native_host.adapter
        assert adapter.impl.native_navigationview.getVisibility() == (8 if hidden else 0)
        assert self._document_tabs_hidden == hidden

    async def assert_compact_keyboard(self):
        adapter = self.native_host.adapter
        await self.wait_until(lambda: adapter.keyboard_chrome is not None,
                              'Compact keyboard suppression was not activated')
        self.adaptive.render()
        await asyncio.sleep(.3)
        assert self.ime_visible()
        assert not self._impl.native.getSupportActionBar().isShowing()
        assert adapter.impl.native_navigationview.getVisibility() == 8
        assert adapter.keyboard_chrome[3], 'Reader bar must be restored after keyboard dismissal'
        from android.graphics import Rect
        visible = Rect()
        adapter.impl.native.getWindowVisibleDisplayFrame(visible)
        self.state['compact_keyboard_visible_height_dp'] = adapter.impl.scale_out(visible.height())
        assert self.state['compact_keyboard_visible_height_dp'] < 400
        self.state.setdefault('compact_keyboard_samples', []).append(dict(
            window_dp=[self.main_window.size.width, self.main_window.size.height],
            visible_height_dp=self.state['compact_keyboard_visible_height_dp'],
            navigation_presentation=adapter.mode))

    async def check(self):
        self.sequence = 0
        self.state = dict(success=False, checks={}, phase='initializing', sequence=0, action='wait')
        self.publish()
        try:
            from android.content import Context
            from android.os import Build
            self.state['android_version'] = str(Build.VERSION.RELEASE)
            self.state['device_model'] = str(Build.MODEL)
            require_compact = (Path(self.paths.cache) / 'document-navigation-require-suppression').exists()
            self.state['require_compact_suppression'] = require_compact
            self.state['back_events'] = []
            system_back = self.routes.system_back
            def traced_back():
                event = dict(phase=self.state['phase'], destination=self.native_host.state.destination,
                             ime=self.ime_visible(), reader=self.visible_reader())
                handled = system_back()
                event['handled'] = handled
                event['routes_after'] = [route for route, *_ in self.routes.screens[self.native_host.state.destination]]
                self.state['back_events'].append(event)
                self.publish()
                return handled
            self.routes.system_back = traced_back
            presentation = Path(self.paths.cache) / 'document-navigation-presentation'
            adapter = self.native_host.adapter
            if presentation.exists() and presentation.read_text().strip() == 'bottom':
                # Exercise the native phone bar on a tablet without changing
                # device display settings or the production responsive policy.
                set_mode = adapter.set_mode
                adapter.set_mode = lambda mode: set_mode('bottom')
                adapter.set_mode('bottom')
            self.state['navigation_presentation'] = adapter.mode
            self.state['window_dp'] = [self.main_window.size.width, self.main_window.size.height]
            self.show_cloud(present=False)
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            path = self.private_root / 'Synthetic note.txt'
            path.write_text('Synthetic saved text')
            copies = LocalTextCopies(LocalFiles(path.parent))
            for destination in ('home', 'files', 'documents'):
                if destination == 'home':
                    self.show_home()
                elif destination == 'files':
                    await self.show_files()
                else:
                    self.show_documents_hub()
                await asyncio.sleep(.3)
                origin = self.body
                self.assert_tabs(False)
                assert await self.open_crypt(copies=copies, key=path.name)
                await asyncio.sleep(.5)
                owner = self.private_sessions.active
                await self.settle_keyboard()
                self.assert_tabs(True)
                adapter = self.native_host.adapter
                assert adapter._reader_action_bar_buttons[0] is owner.crypt_view._reader_close_button
                assert self._impl.native.getSupportActionBar().isShowing()
                await self.action('clean-back-' + destination)
                await self.wait_until(lambda: owner.session.id not in self.workspace.sessions,
                                      'System Back did not close the clean document', timeout=4)
                assert self.body is origin
                assert self.native_host.state.destination == destination
                self.assert_tabs(False)
                self.state['checks']['system_back_returns_to_' + destination] = True

            await self.show_files()
            origin = self.body
            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            owner.crypt_text.value = 'Synthetic unsaved draft'
            await self.settle_keyboard()
            await self.action('dirty-back-opens-prompt')
            assert self.routes.screens['files'][-1][0] == 'private-close:' + owner.session.id
            self.assert_tabs(True)
            await self.action('dirty-prompt-back-keeps-editing')
            assert self.visible_reader() == owner.session.id
            assert owner.session.id not in self._reader_closing
            assert owner.crypt_text.value == 'Synthetic unsaved draft'
            self.assert_tabs(True)
            owner.crypt_text.value = 'Synthetic saved text'
            await self.settle_keyboard()
            await self.action('clean-back-after-keep-editing')
            assert self.body is origin
            self.state['checks']['dirty_back_prompts_and_prompt_back_retains_draft'] = True

            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            native = owner.crypt_text._impl.native
            native.requestFocus()
            manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)
            manager.showSoftInput(native, 1)
            await self.wait_until(self.ime_visible, 'Keyboard did not appear')
            self.assert_tabs(True)
            self.state['keyboard_override_active'] = self.native_host.adapter.keyboard_chrome is not None
            if require_compact:
                await self.assert_compact_keyboard()
                self.state['keyboard_override_active'] = True
                self.state['checks']['compact_keyboard_hides_reader_bar_and_destinations'] = True
                from android.content.pm import ActivityInfo
                self._impl.native.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)
                await self.wait_until(lambda: self.main_window.size.width > self.main_window.size.height,
                                      'Landscape rotation did not resize the app')
                native.requestFocus()
                manager.showSoftInput(native, 1)
                await self.wait_until(self.ime_visible, 'Keyboard did not survive rotation')
                await self.assert_compact_keyboard()
                self.assert_tabs(True)
                # Display cutouts can keep the usable landscape width below
                # the production rail breakpoint even on a 640 dp display.
                expected_mode = 'rail' if self.main_window.size.width >= 600 else 'bottom'
                assert self.native_host.adapter.mode == expected_mode
                for mode in ('rail', 'bottom'):
                    self.native_host.adapter.set_mode(mode)
                    adapter = self.native_host.adapter
                    assert adapter.keyboard_chrome[0] == adapter.impl.native_navigationview
                    assert adapter.keyboard_chrome[1] == 8
                    assert adapter.keyboard_chrome[3]
                    self.assert_tabs(True)
                # Remounting native navigation can dismiss the IME. Allow the
                # platform layout to settle, then explicitly resume editing.
                await asyncio.sleep(.5)
                native.requestFocus()
                manager.showSoftInput(native, 1)
                await self.wait_until(self.ime_visible, 'Keyboard did not resume after bar remount')
                await self.assert_compact_keyboard()
                self.state['checks']['keyboard_snapshot_transfers_between_native_bars'] = True
                self.state['checks']['rotation_with_keyboard_preserves_reader_and_suppression'] = True
            await self.action('back-dismisses-keyboard')
            assert not self.ime_visible()
            assert not any(event['phase'] == 'back-dismisses-keyboard' for event in self.state['back_events'])
            assert self.visible_reader() == owner.session.id
            assert owner.session.id in self.workspace.sessions
            self.assert_tabs(True)
            assert self._impl.native.getSupportActionBar().isShowing()
            assert self.native_host.adapter.keyboard_chrome is None
            self.state['checks']['first_back_dismisses_keyboard_without_closing_document'] = True
            if require_compact:
                self._impl.native.setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_PORTRAIT)
                await self.wait_until(lambda: self.main_window.size.width < self.main_window.size.height,
                                      'Portrait rotation did not resize the app')
                await self.settle_keyboard()
                assert self.native_host.adapter.mode == 'bottom'
                assert self.visible_reader() == owner.session.id
                self.assert_tabs(True)
            await self.action('second-back-closes-document')
            assert self.body is origin
            self.assert_tabs(False)
            self.state['checks']['second_back_closes_document_and_restores_tab'] = True

            assert await self.open_crypt(copies=copies, key=path.name)
            owner = self.private_sessions.active
            native = owner.crypt_text._impl.native
            native.requestFocus()
            manager.showSoftInput(native, 1)
            await self.wait_until(self.ime_visible, 'Keyboard did not reappear')
            if require_compact:
                await self.assert_compact_keyboard()
                # The toolbar is intentionally unavailable in the short pane.
                # Exercise document retirement while its keyboard snapshot lives.
                self.request_reader_close(owner.session.id)
            else:
                owner.crypt_view._reader_close_button._impl.native.performClick()
            await asyncio.sleep(.5)
            assert owner.session.id not in self.workspace.sessions
            assert self.body is origin
            if self.ime_visible():
                await self.action('dismiss-keyboard-after-toolbar-back')
            assert not self.ime_visible()
            assert self.body is origin
            assert not self._impl.native.getSupportActionBar().isShowing()
            self.assert_tabs(False)
            close_check = ('close_while_compact_keyboard_active_does_not_restore_retired_bar'
                           if require_compact else 'toolbar_back_with_keyboard_does_not_restore_retired_bar')
            self.state['checks'][close_check] = True

            folder = self.private_root / 'LocalFiles' / 'Synthetic navigation'
            folder.mkdir(parents=True)
            for index in range(120):
                (folder / f'Retained {index:03}.txt').write_text('Synthetic local text')
            await self.show_files()
            await self.browser_file_location(('Local files', folder.name))
            browser = self.file_browser
            browser.search.value = 'Retained'
            await asyncio.sleep(.4)
            browser.selected = browser.entries[10].identity
            await self.action('swipe-filtered-folder', action='swipe')
            before = browser.vertical_position
            self.state['folder_scroll_before_open'] = before
            assert before >= 350, 'Native swipe did not scroll the folder'
            selected, tree, origin = browser.selected, browser.tree, self.body
            assert await self.open_download(path=folder / 'Retained 010.txt')
            owner = self.editor_view
            await self.settle_keyboard()
            await self.action('back-restores-filtered-scrolled-folder')
            assert owner.session.id not in self.workspace.sessions
            assert self.native_host.state.destination == 'files'
            assert self.body is origin
            assert browser.tree is tree
            assert self.file_path == folder.name
            assert browser.search.value == 'Retained'
            assert browser.selected == selected
            after = browser.vertical_position
            self.state['folder_scroll'] = dict(before=before, after=after)
            assert abs(before - after) <= 2, 'Folder scroll position shifted'
            self.assert_tabs(False)
            self.state['checks']['folder_query_selection_and_scroll_restored'] = True
            if require_compact:
                browser.open_search()
                search = browser.search._impl.native
                search.requestFocus()
                manager.showSoftInput(search, 1)
                await self.wait_until(self.ime_visible, 'Folder search keyboard did not appear')
                await self.wait_until(lambda: self.native_host.adapter.keyboard_chrome is not None,
                                      'Folder search did not suppress compact chrome')
                self.adaptive.render()
                await asyncio.sleep(.3)
                assert not self._document_tabs_hidden
                assert not self._impl.native.getSupportActionBar().isShowing()
                assert self.native_host.adapter.impl.native_navigationview.getVisibility() == 8
                await self.action('back-dismisses-folder-search-keyboard')
                assert not self.ime_visible()
                assert not any(event['phase'] == 'back-dismisses-folder-search-keyboard'
                               for event in self.state['back_events'])
                assert self.native_host.adapter.keyboard_chrome is None
                assert not self._impl.native.getSupportActionBar().isShowing()
                self.assert_tabs(False)
                assert browser.search.value == 'Retained'
                assert browser.selected == selected
                assert abs(before - browser.vertical_position) <= 2
                self.state['checks']['folder_search_keyboard_restores_tabs_without_reader_bar'] = True
            self.state.update(success=True, phase='complete', action='complete')
        except Exception:
            self.state.update(error=traceback.format_exc(), phase='failed', action='complete')
        self.publish()
        print('ANDROID_DOCUMENT_NAVIGATION=' + json.dumps(self.state), flush=True)


def main():
    return AndroidDocumentNavigationProbe('Document Navigation QA', BUNDLE)
