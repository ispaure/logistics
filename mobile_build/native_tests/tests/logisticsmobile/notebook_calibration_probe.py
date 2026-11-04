"""Focused packaged Android calibration check without test-only Java classes.

Uses production NotebookInput MotionEvents and reflected production Ballpoint
math in the real Android runtime. This is not the complete native input suite,
an Onyx driver attachment test, or physical pressure/latency acceptance.
"""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text

TEST_STAGE = TestStage.REGRESSION


class NotebookCalibrationProbe(NotebookProbe):
    async def check(self, app):
        result = dict(success=False, physical_stylus_measured=False,
                      full_notebook_input_suite=False, tests=[])
        panel = None
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            assert not self._startup_in_progress
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            app.set_feature_enabled('notebooks', True, refresh=False)
            from features.notebooks.mobile.documents import open_notebook
            assert await open_notebook(app, name='Synthetic native calibration QA')
            panel = app.notebook_panel
            await wait_for_text(panel.web, 'Synthetic native calibration QA')
            assert await panel.web.evaluate_javascript('!!state.native_pen')
            from java import jarray, jclass
            from android.os import SystemClock
            from android.view import MotionEvent, InputDevice
            from features.notebooks.brushes import BRUSHES, NATIVE_SCALES, native_color, stroke_points
            from features.notebooks.notebook import Notebook

            # Invoke the compiled application class in Android, never a host
            # reimplementation or the absent NotebookInputChecks QA helper.
            Class, Float, Object = (jclass('java.lang.' + name) for name in ('Class', 'Float', 'Object'))
            ballpoint = Class.forName('io.github.ispaure.logistics.notebooks.BooxBallpoint')
            methods = [ballpoint.getDeclaredMethod('width', jarray(Class)([Float.TYPE] * n)) for n in (2, 4)]
            for method in methods:
                method.setAccessible(True)
            brush = BRUSHES[15]
            checked = 0
            for width, base in enumerate(brush['widths'], 1):
                for p in range(256):
                    pressure = p / 255
                    expected = stroke_points([[20, 30, pressure]], 15, width)[0][3]
                    for method, extra in zip(methods, ([], [brush['pressure'], brush['exponent']])):
                        args = jarray(Object)([Float(value) for value in (pressure, base, *extra)])
                        value = method.invoke(None, args)
                        actual = float(value.floatValue() if hasattr(value, 'floatValue') else value)
                        assert actual == expected, (width, p, actual, expected)
                    checked += 1
            result['compiled_ballpoint'] = dict(pressures=256, widths=list(brush['widths']),
                cases=checked, both_default_and_explicit_curve=True,
                class_name=str(ballpoint.getName()))
            loader = app._impl.native.getClassLoader()
            sdk = Class.forName('com.onyx.android.sdk.pen.TouchHelper', False, loader)
            result['packaged_sdk'] = dict(class_name=str(sdk.getName()),
                scope='Class linked in Android; no physical Onyx SDK attachment claimed')
            result['tests'].append('compiled_android_default_and_explicit_ballpoint_math')

            async def idle():
                for _ in range(300):
                    ready = await panel.web.evaluate_javascript('!busy&&!queue.length&&active===null')
                    if not panel.busy and ready:
                        return
                    await asyncio.sleep(.05)
                raise TimeoutError('Calibration canvas did not acknowledge native input')

            native = panel.web._impl.native
            # Phones start in a cropped Move view. Establish the same fitted
            # full-page precondition as the shared input acceptance fixture.
            await panel.web.evaluate_javascript("paperView='pro';$('paperView').value=paperView;setZoom('page')")
            await asyncio.sleep(.2)
            props = jarray(MotionEvent.PointerProperties)(1)
            props[0] = MotionEvent.PointerProperties()
            props[0].id, props[0].toolType = 3, MotionEvent.TOOL_TYPE_STYLUS
            coords = jarray(MotionEvent.PointerCoords)(1)
            coords[0] = MotionEvent.PointerCoords()
            coords[0].size = 1
            rows = result['native_motion_events'] = []
            for tool, color, width in [(15, 0, 1), (15, 6, 2), (15, 7, 3), (18, 6, 1)]:
                await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool))
                    + ";$('tool').onchange();$('color').value=" + repr(str(color))
                    + ";$('width').value=" + repr(str(width)) + ";document.dispatchEvent(new Event('change'))")
                await idle()
                geometry = json.loads(await panel.web.evaluate_javascript(
                    'JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})'))
                rect, ratio = geometry['r'], native.getWidth() / geometry['width']
                x, y = (rect['left'] + rect['width'] * .2) * ratio, (rect['top'] + rect['height'] * .25) * ratio
                distance = rect['width'] * .3 * ratio
                hit = await panel.web.evaluate_javascript(
                    f'document.elementFromPoint({x / ratio},{y / ratio})===canvas')
                result['gesture_fixture'] = dict(geometry=geometry, native_width=native.getWidth(),
                    native_height=native.getHeight(), starts_on_canvas=hit, tool=tool)
                assert hit, result['gesture_fixture']
                assert 0 < x < x + distance < native.getWidth() and 0 < y < native.getHeight(), result['gesture_fixture']
                before = len(panel.editor.notebook.page(0).strokes)
                start = SystemClock.uptimeMillis()
                pressures = (.1, .25, .5, .75, 1, 1)
                for index, pressure in enumerate(pressures):
                    action = MotionEvent.ACTION_DOWN if index == 0 else MotionEvent.ACTION_UP if index == 5 else MotionEvent.ACTION_MOVE
                    coords[0].x, coords[0].y = x + distance * index / 5, y
                    coords[0].pressure = pressure
                    event = MotionEvent.obtain(start, start + index * 20, action, 1, props, coords,
                        0, 0, 1., 1., 0, 0, InputDevice.SOURCE_STYLUS, 0)
                    try:
                        native.dispatchTouchEvent(event)
                    finally:
                        event.recycle()
                    await asyncio.sleep(.03)
                for _ in range(200):
                    if len(panel.editor.notebook.page(0).strokes) == before + 1:
                        break
                    await asyncio.sleep(.05)
                await idle()
                assert len(panel.editor.notebook.page(0).strokes) == before + 1, dict(
                    before=before, after=len(panel.editor.notebook.page(0).strokes), fixture=result['gesture_fixture'])
                stroke = panel.editor.notebook.page(0).strokes[-1]
                assert stroke.tool == tool and stroke.color == native_color(tool, color)[0]
                assert len(stroke.points) >= 5
                assert min(p[2] for p in stroke.points) < .11 and max(p[2] for p in stroke.points) == 1
                expected = stroke_points([[p[0], p[1], p[2]] for p in stroke.points], tool, width)
                assert [p[3] for p in stroke.points] == [p[3] for p in expected]
                assert stroke.scale == NATIVE_SCALES[width - 1]
                reopened = Notebook.read(panel.editor.notebook.to_bytes()).page(0).strokes[-1]
                assert reopened.scale == stroke.scale and reopened.color == stroke.color
                assert len(reopened.points) == len(stroke.points)
                for saved, original in zip(reopened.points, stroke.points):
                    assert abs(saved[0] - original[0]) < .001 and abs(saved[1] - original[1]) < .001
                    assert saved[2] == round(original[2] * 255) / 255 and saved[3] == original[3]
                rows.append(dict(tool=tool, color=stroke.color, width_choice=width,
                    native_scale=stroke.scale, points=len(stroke.points),
                    pressures=[p[2] for p in stroke.points], widths=[p[3] for p in stroke.points]))
            result['native_motion_events'] = rows
            result['tests'].append('production_notebook_input_pressure_width_and_archive_roundtrip')
            palette = json.loads(await panel.web.evaluate_javascript('JSON.stringify({count:$("width").options.length,blue:swatchColor(18,6)})'))
            assert palette == dict(count=1, blue=[190, 234, 254]), palette
            result['tests'].append('fixed_highlighter_native_blue')
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if panel is not None:
                panel.dispose()
            (Path(self.paths.cache) / 'notebook-calibration-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookCalibrationProbe('Notebook calibration QA', 'io.github.ispaure.logisticsnotebookqa')
