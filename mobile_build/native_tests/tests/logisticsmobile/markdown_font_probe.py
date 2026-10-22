"""Compare loaded WebView font metrics with native Android labels in three faces.

Run as a separate probe app; no user documents or preferences are accessed.
"""
import asyncio
import json
from pathlib import Path
import traceback
from unittest.mock import patch

import toga
from toga.style import Pack

SAMPLE = 'Hamburgefontsiv 0123456789 WWW iii'


async def evaluate(view, script):
    async def run():
        return await view.evaluate_javascript(script)
    task = asyncio.create_task(run())
    done, _ = await asyncio.wait([task], timeout=15)
    if not done:
        task.cancel()
        raise AssertionError('Native JavaScript evaluation timed out')
    return await task


class MarkdownFontProbe(toga.App):
    def startup(self):
        from mobile.appearance import install_appearance
        install_appearance(self)
        self.label = toga.Label(SAMPLE)
        self.web = toga.WebView(style=Pack(flex=1))
        self.main_window = toga.MainWindow(title='Markdown native font verification')
        self.main_window.content = toga.Box(children=[self.label, self.web], style=Pack(direction='column', flex=1))
        self.main_window.show()

    def on_running(self):
        self.loop.create_task(self.probe())

    async def probe(self):
        from android.graphics import Paint, Typeface
        from android.graphics.text import TextRunShaper
        from mobile import android_markdown_font as bridge
        from mobile.preview import markdown_preview
        from features.text_editor.mobile.markdown_editor import editor_html
        from features.books.mobile.private_view import PrivateWebView
        report = dict(success=False, samples=[])
        result = Path(self.paths.cache) / 'markdown-font-result.json'
        result.write_text(json.dumps(dict(success=False, running=True)))
        try:
            for family in (None, 'serif', 'monospace'):
                if family is not None:
                    self.label._impl.native.setTypeface(Typeface.create(family, Typeface.NORMAL))
                paint = Paint(self.label._impl.native.getPaint())
                # Normalize a large native measurement to CSS pixels. Measuring
                # at 16 native pixels rounds each monospace advance to an integer.
                paint.setTextSize(1600.0)
                paint.setSubpixelText(True)
                expected = float(paint.measureText(SAMPLE)) / 100
                native_font = TextRunShaper.shapeTextRun('A', 0, 1, 0, 1, 0.0, 0.0, False, paint).getFont(0)
                # Simulate a customized label Typeface without changing the
                # device-wide font setting. The same bridge runs for all faces.
                bridge._cached = None
                with patch('toga.Label', return_value=self.label):
                    font_data = bridge.native_font()
                assert font_data[0].startswith(b'wOFF')
                with patch.object(bridge, 'native_font', return_value=font_data):
                    for mode in ('preview', 'formatted', 'private'):
                        print('FONT_CASE=' + str((family, mode)), flush=True)
                        view = PrivateWebView(style=Pack(flex=1)) if mode == 'private' else self.web
                        if mode == 'private':
                            self.main_window.content.remove(self.web)
                            self.main_window.content.add(view)
                        html = (editor_html(SAMPLE + ' `code`', 'logistics-editor://probe/')
                                if mode == 'formatted' else markdown_preview(SAMPLE + ' `code`'))
                        if mode == 'private':
                            html = html.replace('</body>', '<!--' + 'x' * (1024 * 1024) + '--></body>')
                        loaded = asyncio.Event()
                        view.on_webview_load = lambda widget, **kwargs: loaded.set()
                        view.set_content('https://logistics.invalid/font-probe/', html)
                        waiting = asyncio.create_task(loaded.wait())
                        done, _ = await asyncio.wait([waiting], timeout=15)
                        if not done:
                            waiting.cancel()
                            raise AssertionError('Native Markdown page did not finish loading')
                        for _ in range(100):
                            value = await evaluate(view, 'JSON.stringify({loaded:Array.from(document.fonts).some(f=>f.family==="LogisticsNative"&&f.status==="loaded"),family:document.body&&getComputedStyle(document.body).fontFamily})')
                            status = json.loads(value)
                            if status['loaded'] and 'LogisticsNative' in (status.get('family') or ''):
                                break
                            await asyncio.sleep(.1)
                        assert status['loaded'], status
                        width = await evaluate(view, '(()=>{const c=document.createElement("canvas").getContext("2d");c.font="16px LogisticsNative";return c.measureText(' + json.dumps(SAMPLE) + ').width})()')
                        # Skia native hinting and Chromium's fractional glyph
                        # positioning can differ by a fraction of one pixel.
                        assert abs(float(width) - expected) < max(1.0, expected * .005), (family, mode, width, expected)
                        assert await evaluate(view, 'getComputedStyle(document.querySelector("code")).fontFamily') == 'monospace'
                        report['samples'].append(dict(family=family or 'device', mode=mode, expected=expected,
                            actual=float(width), native_file=str(native_font.getFile()), status=status,
                            font_bytes=len(font_data[0])))
                        if mode == 'private':
                            assert not view._impl._large_content_dir.exists()
                            view.clear_private_content()
                            self.main_window.content.remove(view)
                            self.main_window.content.add(self.web)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        result.write_text(json.dumps(report, indent=2))
        print('MARKDOWN_FONT_RESULT=' + json.dumps(report), flush=True)


def main():
    return MarkdownFontProbe('Markdown Font Probe', 'io.github.ispaure.logisticsfontprobe')
