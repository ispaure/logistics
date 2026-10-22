"""Disposable iOS simulator proof of reusable native utilities using synthetic content."""
import asyncio
from io import BytesIO
import json
import sys
from pathlib import Path
import traceback
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.event_loop import bind_cooperative_loop
from commonUtils.ui.native.draw_ready import wait_for_draw
from commonUtils.ui.native.keyboard import install as install_keyboard
from commonUtils.runtime.progress import CoalescedProgress
from commonUtils.runtime.streams.progress import reading_stream
from commonUtils.ui.native.text_size import TextSizeBinding
from commonUtils.ui.native.transitions import begin_page_slide, finish_page_slide
from commonUtils.ui.native.sliders import style_slider
from commonUtils.ui.native.appearance import (
    SurfacePainter, SurfaceStyle, DynamicAppleColors, default_palette, accessible_name,
)

BUNDLE = 'io.github.ispaure.logisticsutilitiesqa'

if toga.platform.current_platform == 'iOS':
    from toga_iOS.app import PythonAppDelegate
    class LogisticsSceneAppDelegate(PythonAppDelegate):
        pass


class UtilitiesProbe(toga.App):
    def startup(self):
        bind_cooperative_loop(self.loop)
        self.editor = toga.MultilineTextInput(value='Synthetic unsaved draft', style=Pack(height=100))
        self.web = toga.WebView(style=Pack(flex=1))
        self.web.set_content('about:blank', '<html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><p id="kept">Synthetic document</p></body></html>')
        self.slider = toga.Slider(min=0, max=100, value=25)
        self.command = toga.Button('Synthetic command')
        self.label = toga.Label('Utilities QA')
        self.progress = toga.ProgressBar(max=131072)
        self.panel = toga.Box(children=[self.label, self.command, self.editor, self.web,
                                        self.slider, self.progress], style=Pack(direction=COLUMN, flex=1))
        self.main_window = toga.MainWindow(title='Reusable utilities QA', content=self.panel)
        self.main_window.show()

    def on_running(self):
        if not getattr(self, 'started', False):
            self.started = True
            self.loop.create_task(self.check())

    async def check(self):
        report = dict(success=False, cases=[], environment='ios-simulator', sys_platform=sys.platform, synthetic=True)
        resources = []
        try:
            await asyncio.sleep(.3)
            report['draw_acknowledged'] = await wait_for_draw(self.panel, timeout=2)
            assert report['draw_acknowledged'], 'Native draw was not acknowledged'
            report['cases'].append('draw_acknowledgement')
            keyboard = install_keyboard(self.main_window)
            resources.append(keyboard.dispose)
            assert keyboard.gesture is not None
            report['cases'].append('keyboard_installation')
            values = [20]
            text = TextSizeBinding(self.editor, loop=self.loop, get_size=lambda: values[0],
                                   save_size=lambda value: values.__setitem__(0, value))
            text.install()
            resources.append(text.dispose)
            text.gesture('begin')
            text.gesture('change', 1.2)
            text.gesture('end')
            assert values[0] == 24 and self.editor.value == 'Synthetic unsaved draft'
            report['cases'].append('native_text_pinch_binding')
            web = TextSizeBinding(self.web, loop=self.loop, get_size=lambda: 24, web=True)
            web.install()
            web.attach_load()
            resources.append(web.dispose)
            for _ in range(40):
                if await self.web.evaluate_javascript("document.getElementById('kept')?.textContent") == 'Synthetic document':
                    break
                await asyncio.sleep(.1)
            web.apply(24)
            await asyncio.sleep(.2)
            assert await self.web.evaluate_javascript("document.body.style.fontSize") == '24px'
            assert await self.web.evaluate_javascript("document.getElementById('kept').textContent") == 'Synthetic document'
            report['cases'].append('web_reflow_preserves_content')
            seen = []
            def updated(done, total):
                seen.append([done, total])
                if done is not None:
                    self.progress.value = done
            reporter = CoalescedProgress(self.loop, updated, interval=.01)
            resources.append(reporter.close)
            source = BytesIO(b'x' * 131072)
            with reading_stream(source, total=131072, progress=reporter.publish) as measured:
                await asyncio.to_thread(measured.read, 65536)
                await asyncio.sleep(.1)
                assert [65536, 131072] in seen
                await asyncio.to_thread(measured.read)
            await asyncio.sleep(.1)
            assert seen[-1] == [None, None]
            report['cases'].append('worker_progress_delivery')
            palette = DynamicAppleColors(default_palette)
            painter = SurfacePainter(apple_color=palette.color)
            with painter.batch():
                painter.paint(self.command._impl, SurfaceStyle(background='surface', foreground='text', content_inset=8))
                painter.paint(self.label._impl, SurfaceStyle(radius=0, background='transparent', foreground='muted'))
            accessible_name(self.command, 'Synthetic accessible command')
            assert str(self.command._impl.native.accessibilityLabel) == 'Synthetic accessible command'
            assert len(palette.blocks) >= 3
            report['cases'].append('native_surface_roles')
            style_slider(self.slider, apple_color=palette.color, force_ltr=True)
            assert self.slider.value == 25
            report['cases'].append('native_slider_painting')
            begin_page_slide(self.panel, 1)
            self.label.text = 'Validated utilities'
            finish_page_slide(self.panel, 1)
            await asyncio.sleep(.3)
            report['cases'].append('native_page_transition')
            for dispose in reversed(resources):
                dispose()
            resources.clear()
            assert text.closed and web.closed and keyboard.gesture is None and reporter.closed
            report['cases'].append('resource_disposal')
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            for dispose in reversed(resources):
                dispose()
            output = Path(self.paths.cache) / 'commonutils-utilities-result.json'
            output.write_text(json.dumps(report, indent=2)+'\n')
            print('COMMONUTILS_UTILITIES=' + json.dumps(report), flush=True)


def main():
    return UtilitiesProbe('Reusable utilities QA', BUNDLE)
