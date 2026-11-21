"""Exercise the app clipboard on disposable devices using generated text."""
import asyncio
from ctypes import c_bool
import json
from pathlib import Path
import traceback

import toga
from commonUtils.testing.stages import TestStage
from toga.style import Pack
from commonUtils.testing.waiting import wait_until
from commonUtils.ui.native.inline_html import set_inline_html
from mobile.app import LogisticsMobile
from mobile.clipboard import KEY, controller
from services.session_auth import ResumePassword

TEST_STAGE = TestStage.REGRESSION

MARKER = 'clipboard QA text'
OTHER = 'unrelated QA text'
RESULT = 'clipboard-result.json'


class ClipboardProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'clipboard-workspace'
        super().startup()

    def on_running(self):
        self.loop.create_task(self.exercise())

    def clipboard_empty(self):
        if not self.policy.android:
            from rubicon.objc import ObjCClass
            return ObjCClass('UIPasteboard').generalPasteboard.numberOfItems == 0
        from android.content import Context
        board = self._impl.native.getSystemService(Context.CLIPBOARD_SERVICE)
        return not board.hasPrimaryClip()

    def access(self):
        if not self.policy.android:
            from rubicon.objc import ObjCClass
            board = ObjCClass('UIPasteboard').generalPasteboard
            return str(board.string) if board.hasStrings else ''
        from android.content import Context
        board = self._impl.native.getSystemService(Context.CLIPBOARD_SERVICE)
        return str(board.getPrimaryClip().getItemAt(0).getText()) if board.hasPrimaryClip() else ''

    def seed(self, text):
        if self.policy.android:
            from mobile.native.android_clipboard import copy_text
        else:
            from mobile.native.ios_clipboard import copy_text
        copy_text(text)

    def select(self, field):
        native = field._impl.native
        field.focus()
        if self.policy.android:
            native.setSelection(0, len(MARKER))
        else:
            native.selectAll(None)

    def menu(self, native, operation):
        if self.policy.android:
            from java import jclass
            return native.onTextContextMenuItem(getattr(jclass('android.R$id'), operation))
        from rubicon.objc import SEL, objc_id, send_message
        action = SEL(operation + ':')
        enabled = native.canPerformAction(action, withSender=None)
        send_message(native, action, None, restype=None, argtypes=[objc_id])
        return bool(enabled)

    def shortcut(self, native, operation):
        if self.policy.android:
            from android.view import KeyEvent
            key = getattr(KeyEvent, 'KEYCODE_' + dict(copy='C', cut='X', paste='V')[operation])
            event = KeyEvent(0, 0, KeyEvent.ACTION_DOWN, key, 0, KeyEvent.META_CTRL_ON)
            native.onKeyShortcut(key, event)
        else:
            from rubicon.objc import ObjCClass, SEL, objc_id, send_message
            send_message(ObjCClass('UIApplication').sharedApplication, 'sendAction:to:from:forEvent:',
                         SEL(operation + ':'), None, None, None,
                         restype=c_bool, argtypes=[SEL, objc_id, objc_id, objc_id])

    async def check_text(self, field, invoke, restricted):
        for operation in ('copy', 'cut', 'paste'):
            self.seed(OTHER)
            field.value = MARKER
            self.select(field)
            await asyncio.sleep(.15)
            invoke(field._impl.native, operation)
            await asyncio.sleep(.15)
            expected_board = OTHER if restricted or operation == 'paste' else MARKER
            expected_text = MARKER if restricted or operation == 'copy' else (OTHER if operation == 'paste' else '')
            assert self.access() == expected_board, (operation, 'clipboard', restricted)
            assert field.value == expected_text, (operation, 'field', restricted)

    async def check_web(self, web, restricted):
        for operation in ('copy', 'cut', 'paste'):
            self.seed(OTHER)
            await web.evaluate_javascript(
                "(() => {const t=document.querySelector('textarea');"
                f"t.value={json.dumps(MARKER)}; t.focus(); t.select(); return true;}})()")
            await asyncio.sleep(.3)
            native = web._impl.native
            if self.policy.android:
                from android.view import KeyEvent
                key = getattr(KeyEvent, 'KEYCODE_' + dict(copy='C', cut='X', paste='V')[operation])
                for action in (KeyEvent.ACTION_DOWN, KeyEvent.ACTION_UP):
                    native.dispatchKeyEvent(KeyEvent(0, 0, action, key, 0, KeyEvent.META_CTRL_ON))
            else:
                from rubicon.objc import SEL
                action = SEL(operation + ':')
                # Use the public WKWebView responder command, as invoked by UIKit.
                assert bool(native.canPerformAction(action, withSender=None)) != restricted, operation
                getattr(native, operation)(None)
            await asyncio.sleep(.4)
            expected_board = OTHER if restricted or operation == 'paste' else MARKER
            expected_text = MARKER if restricted or operation == 'copy' else (OTHER if operation == 'paste' else '')
            assert self.access() == expected_board, (operation, 'web clipboard', restricted)
            assert await web.evaluate_javascript("document.querySelector('textarea').value") == expected_text, (
                operation, 'web text', restricted)

    async def check_chat(self, restricted):
        self.seed(OTHER)
        web = self.chat_transcript
        assert await web.evaluate_javascript("""(() => {
            const copy = document.querySelector('article.assistant button.copy');
            if (!copy) return false;
            copy.click();
            return true;
        })()""")
        expected = 'Clipboard unavailable' if restricted else 'Copied'
        for _ in range(20):
            status = await web.evaluate_javascript("document.getElementById('copy-status').textContent")
            if status == expected:
                break
            await asyncio.sleep(.1)
        assert status == expected, (status, expected)
        assert self.access() == (OTHER if restricted else MARKER)

    async def check_scenes(self):
        manager = self.scene_manager
        assert manager.new_window(), manager.error
        child = None
        try:
            await wait_until(lambda: any(host is not self and getattr(host, 'scene_active', False) and
                                         not getattr(host, '_startup_in_progress', False) for host in manager.owners.hosts.values()),
                             timeout=25, message='Second iPad scene did not settle')
            child = next(host for host in manager.owners.hosts.values() if host is not self)
            assert child.native_scene != self.native_scene
            assert child.clipboard is self.clipboard
            child.show_documents()
            field = child.editor
            await self.check_text(field, self.menu, False)
            release = self.protection.register(object(), lambda: (), protected=lambda: True)
            try:
                await self.check_text(field, self.menu, True)
            finally:
                release()
            await self.check_text(field, self.menu, False)
        finally:
            child = child or next((host for host in manager.owners.hosts.values() if host is not self), None)
            if child is not None:
                assert manager.close_window(child), manager.error
                await wait_until(lambda: len(manager.owners.hosts) == 1,
                                 timeout=20, message='Second iPad scene did not close')

    async def exercise(self):
        report = dict(success=False, cases=[])
        try:
            await wait_until(lambda: getattr(self, 'screen_privacy', None) is not None,
                             timeout=60, message='Clipboard workspace did not start')
            self.policy = controller(self)
            assert self.policy is not None
            assert self.clipboard_empty(), 'QA clipboard was already populated'
            self.policy.preferences.save(**{KEY: 'true'})
            self.policy.publish()
            single = toga.TextInput()
            multi = toga.MultilineTextInput()
            loaded = asyncio.Event()
            web = toga.WebView(on_webview_load=lambda widget: loaded.set(), style=Pack(flex=1))
            navigation = self.main_window.content
            self.main_window.content = toga.Box(children=[single, multi, web], style=Pack(flex=1))
            set_inline_html(web, 'https://logistics.invalid/clipboard-test/', '<textarea></textarea>')
            await asyncio.wait_for(loaded.wait(), timeout=25)

            await self.check_text(single, self.menu, False)
            await self.check_text(multi, self.shortcut, False)
            await self.check_web(web, False)
            report['cases'].append('ordinary text context commands, focused shortcuts and web editing')
            scope = self.policy.process
            gate = ResumePassword('synthetic QA password')
            credentials = [gate]
            remove_credentials = scope.register_credentials(object(), lambda: tuple(credentials))
            secondary = scope.window()
            release = secondary.register(object(), lambda: (), protected=lambda: True)
            try:
                await self.check_text(single, self.menu, True)
                await self.check_text(multi, self.shortcut, True)
                await self.check_web(web, True)
                report['cases'].append('active session blocked without deleting selection or changing clipboard')
                gate.lock()
                assert gate.locked and self.policy.restricted()
                await self.check_text(single, self.menu, True)
                assert gate.authorize(gate.revision) and self.policy.restricted()
                report['cases'].append('manual lock retains clipboard restriction')
                credentials.clear()
                scope.changed()
                assert self.policy.restricted()
                await self.check_text(single, self.menu, True)
                report['cases'].append('retained owner in second window scope after credential removal')
                release()
                assert not self.policy.restricted()
                await self.check_text(single, self.menu, False)
                report['cases'].append('final release restores clipboard commands')
            finally:
                remove_credentials()
                secondary.dispose()
            self.main_window.content = navigation
            self.show_chat()
            from features.lm.domain import message
            from .web_checks import wait_for_text
            await wait_until(lambda: self.chat_current is not None, timeout=15,
                             message='Synthetic chat did not open')
            self.chat_current['messages'] = [message('assistant', MARKER)]
            self.update_chat_transcript()
            await wait_for_text(self.chat_transcript, MARKER)
            await self.check_chat(False)
            release = scope.register_credentials(object(), lambda: (gate,))
            try:
                await self.check_chat(True)
            finally:
                release()
            report['cases'].append('in-page chat Copy routes through native clipboard protection')
            if not self.policy.android and self.scene_manager.supported:
                await self.check_scenes()
                report['cases'].append('retained protection in the primary scene applies to the secondary UIKit editor')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            (Path(self.paths.cache) / RESULT).write_text(json.dumps(report, indent=2))


def main():
    return ClipboardProbe()
