"""Disposable native speech-control geometry check using a silent fixture engine."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import traceback
from uuid import uuid4
import toga
from toga.style import Pack
from logisticsmobile.app import LogisticsMobile
from features.books.mobile.speech_view import ReadAloudPanel
from .fixtures import capture_window


class SilentEngine:
    ready, error, default_voice = True, '', 'Fixture'
    voices = {'Fixture': None}
    def speak(self, *args):
        pass
    def stop(self):
        pass
    def close(self):
        pass


class SpeechControlsProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('speech-controls-' + uuid4().hex)
        super().startup()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        report = dict(success=False, silent_fixture_engine=True)
        output = Path(self.paths.cache) / 'speech-controls-probe'
        output.mkdir(exist_ok=True)
        panel = None
        try:
            await asyncio.sleep(1)
            self.show_documents()
            self.name.value = 'Read aloud preview.md'
            self.editor.value = '# A quieter reading companion\n\n' + ('Your book stays in view while you adjust playback.\n\n' * 8)
            self.show_preview()
            await asyncio.sleep(.5)
            async def source():
                return SimpleNamespace(text='A synthetic speech controls passage.'), 0, None
            panel = ReadAloudPanel(loop=self.loop, source=source, on_range=lambda *a: None,
                close=lambda: None, app=self, engine=SilentEngine())
            panel.show_over(self.body.children[0])
            await panel.ready_task
            await asyncio.sleep(.3)
            await capture_window(self, output / 'timer-off.png')
            panel.timer_choice.value = '15 min'
            panel.speed_choice.value = 1.38
            assert panel.speed_choice.value == 1.5
            assert panel.speed_value.text == '150%'
            panel.timer.remaining = 863
            panel.show_remaining(863)
            await asyncio.sleep(.3)
            await capture_window(self, output / 'timer-active.png')
            native = panel.overlay.container.native
            frame = native.bounds
            report['controls'] = []
            for widget in (panel.speed_choice, panel.speed_minimum, panel.speed_maximum,
                    panel.timer_choice, panel.reset_timer_button, panel.timer_remaining,
                    *panel.playback_controls.children, panel.status):
                control = widget._impl.native
                rect = control.convertRect(control.bounds, toView=native)
                entry = dict(control=getattr(widget, 'accessible_name', None) or getattr(widget, 'text', type(widget).__name__),
                    x=float(rect.origin.x), y=float(rect.origin.y), width=float(rect.size.width), height=float(rect.size.height))
                report['controls'].append(entry)
                if isinstance(widget, toga.Button):
                    assert rect.size.width >= 44 and rect.size.height >= 44, entry
                assert rect.origin.x >= 0 and rect.origin.y >= 0, entry
                assert rect.origin.x + rect.size.width <= frame.size.width + 1, entry
                assert rect.origin.y + rect.size.height <= frame.size.height + 1, entry
            for mode, value in (('light', 1), ('dark', 2)):
                self.main_window._impl.native.overrideUserInterfaceStyle = value
                await asyncio.sleep(.2)
                await capture_window(self, output / ('timer-active-' + mode + '.png'))
            self.main_window._impl.native.overrideUserInterfaceStyle = 0
            panel.reset_timer_button.on_press()
            assert panel.timer_remaining.text == 'Time remaining: 15:00'
            panel.set_status('Could not read this passage. Try reopening the document.')
            await asyncio.sleep(.2)
            await capture_window(self, output / 'wrapped-status.png')
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('SPEECH_CONTROLS_RESULT=' + json.dumps(report), flush=True)


def main():
    return SpeechControlsProbe('Speech Controls Preview', 'io.github.ispaure.logisticsspeechcontrols')
