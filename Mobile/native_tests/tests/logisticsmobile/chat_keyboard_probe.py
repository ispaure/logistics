"""Isolated Android phone chat/IME geometry proof; no real server or account."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile


class ChatKeyboardProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('chat-keyboard-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_chat_probe_started', False):
            self._chat_probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        from android.content import Context
        from android.graphics import Rect
        from android.view.inputmethod import InputMethodManager
        from java import jarray, jint, jclass
        output = Path(self.paths.cache) / 'chat-keyboard-evidence'
        output.mkdir(exist_ok=True)
        result = {'success': False, 'samples': []}
        manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)

        def bounds(native):
            point = jarray(jint)(2)
            native.getLocationOnScreen(point)
            return [int(point[0]), int(point[1]), int(point[0] + native.getWidth()), int(point[1] + native.getHeight())]

        def sample(name):
            adapter = self.native_host.adapter
            visible = Rect()
            adapter.impl.native.getWindowVisibleDisplayFrame(visible)
            insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(adapter.impl.native)
            ime = bool(insets and insets.isVisible(jclass('androidx.core.view.WindowInsetsCompat$Type').ime()))
            data = {'name': name, 'keyboard_visible': ime, 'visible_bottom': int(visible.bottom),
                    'navigation': adapter.diagnostics()}
            for key in ('chat_header', 'chat_title', 'chat_header_actions', 'chat_transcript', 'chat_composer', 'chat_prompt', 'chat_send'):
                data[key] = bounds(getattr(self, key)._impl.native)
            data['bar'] = bounds(adapter.impl.native_navigationview)
            data['bar_padding_bottom'] = adapter.impl.native_navigationview.getPaddingBottom()
            data['bar_visible'] = adapter.impl.native_navigationview.getVisibility() == 0
            result['samples'].append(data)
            (output / 'result.json').write_text(json.dumps(result, indent=2))
            print('CHAT_KEYBOARD_SAMPLE=' + json.dumps(data), flush=True)
            return data

        try:
            await asyncio.sleep(1)
            self.show_chat()
            self.chat_url.value = 'http://127.0.0.1:1/v1'
            self.chat_model.value = 'Synthetic phone model with a long descriptive name'
            self.save_chat_configuration()
            self.chat_current['title'] = 'A long conversation title to check header bounds'
            self.update_chat_header()
            await asyncio.sleep(1)
            sample('closed')
            for cycle in range(2):
                self.chat_prompt.focus()
                manager.showSoftInput(self.chat_prompt._impl.native, InputMethodManager.SHOW_IMPLICIT)
                await asyncio.sleep(1)
                self.chat_prompt.value = 'Typing a message\nSecond line\nThird line'
                await asyncio.sleep(1)
                data = sample(f'open-{cycle}')
                assert data['keyboard_visible'], 'Android IME did not open'
                assert data['navigation']['content_height'] > 0, 'Navigation consumed the chat viewport'
                assert data['bar'][3] - data['bar'][1] <= 100 * self._impl.native.getResources().getDisplayMetrics().density, 'Navigation expanded with the IME'
                assert data['chat_header'][3] <= data['chat_composer'][1], 'Header overlaps composer'
                assert data['chat_prompt'][3] <= data['visible_bottom'], 'Composer hidden by keyboard'
                assert data['chat_send'][3] <= data['chat_composer'][3], 'Send escaped composer'
                assert data['chat_composer'][3] <= data['bar'][1], 'Composer overlaps navigation'
                assert data['chat_title'][2] <= data['chat_header_actions'][0], 'Title overlaps actions'
                assert data['chat_transcript'][3] <= data['chat_composer'][1], 'Transcript overlaps composer'
                assert data['chat_prompt'][2] <= data['chat_send'][0], 'Draft overlaps send'
                manager.hideSoftInputFromWindow(self.chat_prompt._impl.native.getWindowToken(), 0)
                self.chat_prompt._impl.native.clearFocus()
                await asyncio.sleep(1)
                sample(f'closed-{cycle}')
            assert self.chat_prompt.value.endswith('Third line')
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(result, indent=2))
        print('CHAT_KEYBOARD_PROBE=' + json.dumps(result), flush=True)
        if result['success']:
            self.chat_prompt.focus()
            manager.showSoftInput(self.chat_prompt._impl.native, InputMethodManager.SHOW_IMPLICIT)


def main():
    return ChatKeyboardProbe('Chat Keyboard Probe', 'io.github.ispaure.logisticschatprobe')
