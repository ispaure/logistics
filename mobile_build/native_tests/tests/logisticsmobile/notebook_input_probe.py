"""Real Android history delivery, pressure, chrome and overview in isolated QA."""
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .notebook_input_checks import INPUT_CHECKS
from .notebook_chrome_checks import CHROME_CHECKS
from .web_checks import wait_for_text
from .fixtures import capture_window


class NotebookInputProbe(NotebookProbe):
    async def check(self, app):
        output = Path(self.paths.cache) / 'notebook-input'
        output.mkdir(exist_ok=True)
        result = dict(success=False, optical_latency_measured=False)
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            from features.notebooks.mobile.documents import open_notebook
            assert await open_notebook(app, name='Input and pages QA')
            panel = app.notebook_panel
            await wait_for_text(panel.web, 'Input and pages QA')
            await asyncio.sleep(.4)
            async def idle():
                for _ in range(300):
                    value = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length})'))
                    if not panel.busy and not value['busy'] and not value['queued']:
                        return
                    await asyncio.sleep(.05)
                raise AssertionError('Notebook bridge did not finish')
            result['input'] = json.loads(await panel.web.evaluate_javascript(INPUT_CHECKS))
            result['chrome'] = json.loads(await panel.web.evaluate_javascript(CHROME_CHECKS))
            assert await panel.web.evaluate_javascript('state.native_pen')
            native_preview = json.loads(panel.pen_input.nativeStatus())
            if native_preview.get('created'):
                # Exercise the production interface and automatic brush/menu
                # fallback, not the older standalone native-preview prototype.
                for tool in (17, 14, 13, 16, 12, 21, 18, 23, 15):
                    await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value='0';document.dispatchEvent(new Event('change'))")
                    await asyncio.sleep(.15)
                    status = json.loads(panel.pen_input.nativeStatus())
                    assert status['input'] == (tool in (15, 17)), (tool, status)
                from features.notebooks.brushes import PALETTE, PEN_COLORS
                from java import jclass
                styles = jclass('com.onyx.android.sdk.pen.TouchHelper')
                # Compare the vendor's documented Fountain companion renderer
                # with our Ballpoint widths at constant pressures. This is a
                # raster/profile diagnostic, not optical pen latency evidence.
                bitmap_type = jclass('android.graphics.Bitmap')
                bitmap_config = jclass('android.graphics.Bitmap$Config')
                wrapper = jclass('com.onyx.android.sdk.pen.NeoBrushPenWrapper')
                point_type = jclass('com.onyx.android.sdk.data.note.TouchPoint')
                jclass('com.onyx.android.sdk.base.utils.ResManager').INSTANCE.init(app._impl.native.getApplicationContext())
                curve = []
                for pressure in (.1, .25, .5, .75, 1.):
                    bitmap = bitmap_type.createBitmap(512, 128, bitmap_config.ARGB_8888)
                    paint = jclass('android.graphics.Paint')()
                    paint.setColor(-16777216)
                    paint.setAntiAlias(True)
                    paint.setStyle(jclass('android.graphics.Paint$Style').STROKE)
                    paint.setStrokeWidth(40.)
                    points = jclass('java.util.ArrayList')()
                    for x_ in range(10, 500, 5):
                        point = point_type(float(x_), 64.)
                        point.setPressure(float(pressure * native_preview['max_pressure']))
                        point.setTimestamp(x_ * 8)
                        points.add(point)
                    wrapper.drawStroke(jclass('android.graphics.Canvas')(bitmap), paint, points, 40., float(native_preview['max_pressure']), False)
                    rows = [y_ for y_ in range(128) if (int(bitmap.getPixel(250, y_)) >> 24) & 255 >= 128]
                    curve.append(dict(pressure=pressure, vendor_width=len(rows), canonical_width=40 * (.35 + .65 * pressure ** 1.2)))
                    bitmap.recycle()
                result['vendor_pressure_curve'] = curve
                device = jclass('com.onyx.android.sdk.device.Device').currentDevice()
                result['native_stroke_parameters'] = {
                    str(style): list(device.getStrokeParameters(style)) for style in range(9)
                }
                helper_class = jclass('java.lang.Class').forName('android.onyx.ViewUpdateHelper')
                result['firmware_handwriting_methods'] = [str(m) for m in helper_class.getDeclaredMethods()
                    if any(word in str(m).lower() for word in ('bitmap', 'stroke', 'scribble', 'handwriting'))]
                tested_colors = []
                for tool in (17, 15):
                    for grayscale in (False, True):
                        for color in PEN_COLORS:
                            await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value=" + repr(str(color)) + ";$('grayscale').checked=" + str(grayscale).lower() + ";document.dispatchEvent(new Event('change'))")
                            await asyncio.sleep(.1)
                            status = json.loads(panel.pen_input.nativeStatus())
                            rgb = [int(PALETTE[color][i:i + 2], 16) for i in (1, 3, 5)]
                            if grayscale:
                                import math
                                gray = math.floor(sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722))) + .5)
                                rgb = [gray] * 3
                            argb = 0xff000000 + (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]
                            assert status['input'] and status['preview_tool'] == tool, status
                            assert status['preview_style'] == styles.STROKE_STYLE_PENCIL, status
                            assert status['preview_argb'] == argb, (tool, color, grayscale, status, argb)
                            tested_colors.append(dict(tool=tool, color=color, grayscale=grayscale, argb=argb))
                await panel.web.evaluate_javascript("$('tool').value='17';$('tool').onchange();$('color').value='0';$('grayscale').checked=false;document.dispatchEvent(new Event('change'))")
                await asyncio.sleep(.15)
                await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
                await asyncio.sleep(.15)
                assert not json.loads(panel.pen_input.nativeStatus())['input']
                await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
                await asyncio.sleep(.15)
                assert json.loads(panel.pen_input.nativeStatus())['input']
                result['native_preview'] = dict(brush_fallback=True, menu_clipping=True, colors=tested_colors)
            await panel.web.evaluate_javascript("$('tool').value='12';$('tool').onchange()")
            await asyncio.sleep(.15)
            geometry = json.loads(await panel.web.evaluate_javascript("JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})"))
            native = panel.web._impl.native
            x = (geometry['r']['left'] + 40) * native.getWidth() / geometry['width']
            y = (geometry['r']['top'] + 140) * native.getHeight() / geometry['height']
            from java import jclass, jarray, jint
            jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks').stroke(native, x, y)
            for _ in range(200):
                if panel.editor.notebook.page(0).strokes:
                    break
                await asyncio.sleep(.05)
            await idle()
            ink = panel.editor.notebook.page(0).strokes
            result['history_strokes'] = [dict(tool=s.tool, color=s.color, points=len(s.points),
                                             first=s.points[0], last=s.points[-1]) for s in ink]
            assert len(ink) == 1, len(ink)
            stroke = ink[0]
            assert len(stroke.points) == 22, len(stroke.points)
            assert abs(stroke.points[0][2] - .2) < .01 and abs(stroke.points[-1][2] - .8) < .01
            assert stroke.points[0][3] < stroke.points[-1][3]
            result['native_history'] = dict(points=len(stroke.points), pressure=[stroke.points[0][2], stroke.points[-1][2]],
                                           widths=[stroke.points[0][3], stroke.points[-1][3]], duplicate_strokes=False)
            if native_preview.get('created'):
                await panel.web.evaluate_javascript("$('tool').value='17';$('tool').onchange();document.dispatchEvent(new Event('change'))")
                await asyncio.sleep(.2)
                assert json.loads(panel.pen_input.nativeStatus())['input']
                # Injected Android events bypass the physical raw reader. They
                # must replay exactly once when the SDK supplies no callbacks.
                jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks').stroke(native, x, y)
                for _ in range(200):
                    if len(panel.editor.notebook.page(0).strokes) == 2:
                        break
                    await asyncio.sleep(.05)
                await idle()
                assert len(panel.editor.notebook.page(0).strokes) == 2
                assert len(panel.editor.notebook.page(0).strokes[-1].points) == 22
                assert json.loads(panel.pen_input.nativeStatus())['closed']
                result['native_preview']['missing_callback_replay'] = True
                panel.mount_canvas()
                for _ in range(300):
                    try:
                        if await panel.web.evaluate_javascript("typeof window.logisticsNativePen==='function' && !!state.native_pen"):
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(.05)
                native = panel.web._impl.native
                geometry = json.loads(await panel.web.evaluate_javascript("JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})"))
                x = (geometry['r']['left'] + 40) * native.getWidth() / geometry['width']
                y = (geometry['r']['top'] + 140) * native.getHeight() / geometry['height']
                ballpoints = []
                for tool, color in ((15, 0), (15, 6), (15, 7)):
                    await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value=" + repr(str(color)) + ";document.dispatchEvent(new Event('change'))")
                    await asyncio.sleep(.15)
                    count = len(panel.editor.notebook.page(0).strokes)
                    jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks').rawBallpoint(panel.pen_input, native, x, y)
                    for _ in range(200):
                        if len(panel.editor.notebook.page(0).strokes) == count + 1:
                            break
                        await asyncio.sleep(.05)
                    await idle()
                    ink = panel.editor.notebook.page(0).strokes
                    assert len(ink) == count + 1, (len(ink), count)
                    stroke = ink[-1]
                    assert stroke.tool == tool and stroke.color == color and len(stroke.points) == 25
                    from features.notebooks.notebook import Notebook
                    reopened = Notebook.read(panel.editor.notebook.to_bytes())
                    after = reopened.page(0).strokes[-1]
                    assert [p[3] for p in stroke.points] == [p[3] for p in after.points]
                    expected = [float(jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks').ballpointWidth(p[2], 2.)) for p in stroke.points]
                    assert [p[3] for p in stroke.points] == expected, (stroke.points, expected)
                    assert abs(stroke.points[0][2] - .1) < .01 and abs(stroke.points[-1][2] - 1) < .01
                    status = json.loads(panel.pen_input.nativeStatus())
                    assert status['width_updates'] > 0 and not status['error'], status
                    ballpoints.append(dict(tool=tool, color=color, widths=[p[3] for p in stroke.points],
                        saved_widths=[p[3] for p in after.points], pressure=[p[2] for p in stroke.points], native=status))
                result['native_ballpoint_handoff'] = ballpoints
            location = jarray(jint)(2)
            native.getLocationOnScreen(location)
            decor = app._impl.native.getWindow().getDecorView()
            types = jclass('androidx.core.view.WindowInsetsCompat$Type')
            insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(decor)
            cutout = insets.getInsets(types.displayCutout()).top
            result['window'] = dict(top=int(location[1]), cutout=int(cutout), status_visible=bool(insets.isVisible(types.statusBars())))
            assert location[1] <= cutout + 2, result['window']
            await capture_window(app, output / 'canvas.png')
            for _ in range(2):
                await panel.web.evaluate_javascript("send({op:'add-page'})")
                await idle()
            await panel.web.evaluate_javascript("send({op:'page',index:0})")
            await idle()
            original_second = panel.editor.notebook.pages[1].id
            await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
            await asyncio.sleep(.3)
            await capture_window(app, output / 'dropdown.png')
            await panel.web.evaluate_javascript("document.querySelector('.menu-add-page').click()")
            await idle()
            assert panel.editor.index == 1 and panel.editor.notebook.pages[2].id == original_second
            await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();$('pagesToggle').click()")
            await idle()
            assert await panel.web.evaluate_javascript("document.querySelectorAll('.page-previews button').length") == 4
            await asyncio.sleep(.3)
            await capture_window(app, output / 'overview.png')
            await panel.web.evaluate_javascript("document.querySelector('.page-jump input').value='4';document.querySelector('.page-jump button').click()")
            await idle()
            assert panel.editor.index == 3
            result.update(success=True, thumbnails=4, go_to_page=True, insert_after_current=True)
            # Remounting must detach and destroy the retired native WebView,
            # not retain another set of Chromium/GPU buffers per open.
            remounts = []
            for _ in range(6):
                previous = panel.web._impl.native
                panel.mount_canvas()
                await wait_for_text(panel.web, 'Input and pages QA')
                await asyncio.sleep(.3)
                assert previous.getParent() is None
                memory = jclass('android.os.Debug$MemoryInfo')()
                jclass('android.os.Debug').getMemoryInfo(memory)
                remounts.append(memory.getTotalPss())
            result['retired_webview_remount_pss_kb'] = remounts
        except Exception:
            result['success'] = False
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-input-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookInputProbe('Notebook input QA', 'io.github.ispaure.logisticsnotebookqa')
