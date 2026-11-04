"""Focused native hover/contact plumbing with synthetic events, never hardware.

Android must be compiled with the production OnHoverListener implementation.
iPad checks the real UIKit observer installation/lifecycle and browser fallback;
simulator event injection cannot prove physical Pencil hover or palm rejection.
"""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


class NotebookPalmProbe(NotebookProbe):
    async def idle(self, panel):
        for _ in range(200):
            if not panel.busy and await panel.web.evaluate_javascript('!busy&&!queue.length&&active===null'):
                return
            await asyncio.sleep(.05)
        raise TimeoutError('Notebook palm probe did not acknowledge input')

    async def snapshot(self, panel):
        return json.loads(await panel.web.evaluate_javascript(
            'JSON.stringify({blocked:penTouchBlocked(),hover:[...penHoverSources],'
            'contact:penContactActive,active,touches:touchContacts.size,pan:!!pan,'
            'pinch:!!touchPinch,x:$("viewport").scrollLeft,y:$("viewport").scrollTop})'))

    async def check(self, app):
        result = dict(success=False, physical_stylus_measured=False,
                      optical_latency_measured=False, observations=[], tests=[])
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
            assert await open_notebook(app, name='Synthetic native palm QA')
            panel = app.notebook_panel
            await wait_for_text(panel.web, 'Synthetic native palm QA')
            await panel.web.evaluate_javascript("resetPenRejection();paperView='pro';$('paperView').value=paperView;"
                "setZoom('page');$('tool').value='17';$('tool').onchange();$('finger').checked=false")
            await asyncio.sleep(.2)
            geometry = json.loads(await panel.web.evaluate_javascript(r'''(()=>{
              const r=canvas.getBoundingClientRect(),v=$('viewport').getBoundingClientRect();
              const x=(Math.max(r.left,v.left)+Math.min(r.right,v.right))/2,
                y=(Math.max(r.top,v.top)+Math.min(r.bottom,v.bottom))/2;
              return JSON.stringify({x,y,width:innerWidth,height:innerHeight,
                hit:document.elementFromPoint(x,y)===canvas,canvas:r.toJSON()})
            })()'''))
            assert geometry['hit'], geometry
            result['geometry'] = geometry
            backend = type(panel.web._impl).__module__
            result['backend'] = backend
            if backend.startswith('toga_android.'):
                await self.android(panel, geometry, result)
            elif backend.startswith('toga_iOS.'):
                await self.ios(panel, geometry, result)
            else:
                raise AssertionError('Native Android/iOS backend required: ' + backend)
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if panel is not None:
                try:
                    result['final_guard'] = await self.snapshot(panel)
                except Exception:
                    result['final_guard_error'] = traceback.format_exc()
                finally:
                    panel.dispose()
            (Path(self.paths.cache) / 'notebook-palm-result.json').write_text(json.dumps(result, indent=2))

    async def android(self, panel, geometry, result):
        from java import jarray
        from android.os import SystemClock
        from android.view import MotionEvent, InputDevice
        native = panel.web._impl.native
        assert panel.pen_input is not None
        assert await panel.web.evaluate_javascript('state.native_pen===true')
        ratio = native.getWidth() / geometry['width']
        x, y = geometry['x'] * ratio, geometry['y'] * ratio
        assert 0 < x < x + 40 * ratio < native.getWidth() and 0 < y < native.getHeight()
        result['native_view'] = dict(width=native.getWidth(), height=native.getHeight())
        result['native_status'] = json.loads(panel.pen_input.nativeStatus())
        before = len(panel.editor.notebook.page(0).strokes)
        start, tick = SystemClock.uptimeMillis(), 0

        async def deliver(action, pointers, *, hover=False, flags=0):
            nonlocal tick
            props = jarray(MotionEvent.PointerProperties)(len(pointers))
            coords = jarray(MotionEvent.PointerCoords)(len(pointers))
            for index, (identity, tool, dx, dy) in enumerate(pointers):
                props[index] = MotionEvent.PointerProperties()
                props[index].id, props[index].toolType = identity, tool
                coords[index] = MotionEvent.PointerCoords()
                coords[index].x, coords[index].y = x + dx * ratio, y + dy * ratio
                coords[index].pressure = .6 if tool == MotionEvent.TOOL_TYPE_STYLUS and not hover else .5
                coords[index].size = 1
            source = InputDevice.SOURCE_STYLUS if pointers[0][1] == MotionEvent.TOOL_TYPE_STYLUS else InputDevice.SOURCE_TOUCHSCREEN
            event = MotionEvent.obtain(start, start + tick, action, len(pointers), props, coords,
                0, 0, 1., 1., 0, 0, source, flags)
            tick += 20
            try:
                handled = bool(native.dispatchGenericMotionEvent(event) if hover else native.dispatchTouchEvent(event))
            finally:
                event.recycle()
            await asyncio.sleep(.08)
            result['observations'].append(dict(action=int(action), hover=hover, flags=flags,
                handled=handled, guard=await self.snapshot(panel)))

        pen = lambda dx=0: (3, MotionEvent.TOOL_TYPE_STYLUS, dx, 0)
        finger = lambda dx=0: (7, MotionEvent.TOOL_TYPE_FINGER, dx, 15)
        def no_finger(value):
            assert not value['touches'] and not value['pan'] and not value['pinch'], value

        # Requiring the native source proves production OnHoverListener delivery;
        # Chromium's separate pen PointerEvents alone cannot satisfy this check.
        await deliver(MotionEvent.ACTION_HOVER_ENTER, [pen()], hover=True)
        value = await self.snapshot(panel)
        assert value['blocked'] and 'native' in value['hover'], value
        await deliver(MotionEvent.ACTION_HOVER_MOVE, [pen(2)], hover=True)
        await deliver(MotionEvent.ACTION_DOWN, [finger()])
        no_finger(await self.snapshot(panel))
        await deliver(MotionEvent.ACTION_MOVE, [finger(20)])
        no_finger(await self.snapshot(panel))
        await deliver(MotionEvent.ACTION_UP, [finger(20)])
        await deliver(MotionEvent.ACTION_HOVER_EXIT, [pen(2)], hover=True)
        assert (await self.snapshot(panel))['blocked'], 'Hover-exit grace missing'
        await asyncio.sleep(.4)
        assert not (await self.snapshot(panel))['blocked'], await self.snapshot(panel)
        result['tests'].append('production_android_stylus_hover_and_touch_suppression')

        await deliver(MotionEvent.ACTION_DOWN, [pen()])
        value = await self.snapshot(panel)
        assert value['active'] == 100003 and value['contact'] and value['blocked'], value
        # Android simultaneous pointers share one MotionEvent stream. An
        # unrelated second ACTION_DOWN would be an invalid multitouch fixture.
        await deliver(MotionEvent.ACTION_POINTER_DOWN | (1 << 8), [pen(), finger()])
        no_finger(await self.snapshot(panel))
        await deliver(MotionEvent.ACTION_MOVE, [pen(10), finger(20)])
        no_finger(await self.snapshot(panel))
        await deliver(MotionEvent.ACTION_POINTER_UP | (1 << 8), [pen(10), finger(20)])
        await deliver(MotionEvent.ACTION_UP, [pen(20)])
        assert result['observations'][-1]['guard']['blocked'], 'Pen-up grace missing'
        await self.idle(panel)
        assert len(panel.editor.notebook.page(0).strokes) == before + 1
        result['tests'].append('production_android_contact_rejects_multitouch_palm')

        for action, flags in [(MotionEvent.ACTION_CANCEL, 0), (MotionEvent.ACTION_UP, 0x20)]:
            await deliver(MotionEvent.ACTION_DOWN, [pen()])
            await deliver(MotionEvent.ACTION_MOVE, [pen(10)])
            await deliver(action, [pen(20)], flags=flags)  # FLAG_CANCELED on API 33+
            assert result['observations'][-1]['guard']['blocked'], 'Cancelled pen grace missing'
            await self.idle(panel)
            value = await self.snapshot(panel)
            assert value['active'] is None and not value['contact'], value
            assert len(panel.editor.notebook.page(0).strokes) == before + 1
        result['tests'].append('production_android_cancel_and_flag_canceled_discard_ink')

        await asyncio.sleep(.4)
        assert not (await self.snapshot(panel))['blocked']
        await deliver(MotionEvent.ACTION_DOWN, [finger()])
        value = await self.snapshot(panel)
        assert value['touches'] == 1 and value['pan'], value
        await deliver(MotionEvent.ACTION_CANCEL, [finger()])
        result['tests'].append('android_finger_gesture_recovery_after_grace')

    async def ios(self, panel, geometry, result):
        from rubicon.objc import ObjCClass, py_from_ns
        assert int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1, 'iPad simulator required for UIKit hover acceptance'
        observer = panel.pencil_hover
        assert observer is not None and not observer.closed
        gesture = observer.gesture
        assert list(py_from_ns(gesture.allowedTouchTypes)) == [2]
        assert bool(gesture.requiresExclusiveTouchType)
        assert not gesture.cancelsTouchesInView and not gesture.delaysTouchesBegan and not gesture.delaysTouchesEnded
        assert gesture.view == panel.web._impl.native and gesture.delegate == observer.target
        native = panel.web._impl.native
        size = native.bounds.size
        observer.emit(True, geometry['x'] * float(size.width) / geometry['width'],
                      geometry['y'] * float(size.height) / geometry['height'])
        await asyncio.sleep(.1)
        value = await self.snapshot(panel)
        assert value['blocked'] and 'native' in value['hover'], value
        observer.close()
        observer.close()
        assert observer.closed and gesture.view is None and gesture.delegate is None
        await asyncio.sleep(.4)
        assert not (await self.snapshot(panel))['blocked']
        result['tests'].append('uikit_pencil_only_hover_observer_install_bridge_and_close')
        result['uikit_hover_scope'] = 'Actual recognizer/bridge lifecycle; no simulator Pencil-hover hardware event claim'

        # Browser contact remains the production iOS path. Only OS pointer
        # capture allocation is stubbed for these DOM-synthetic pointer IDs.
        before = len(panel.editor.notebook.page(0).strokes)
        await panel.web.evaluate_javascript('window.palmCapture=canvas.setPointerCapture;canvas.setPointerCapture=()=>{}')
        try:
            await panel.web.evaluate_javascript(r'''(()=>{
              const r=canvas.getBoundingClientRect(),v=$('viewport').getBoundingClientRect(),
                x=(Math.max(r.left,v.left)+Math.min(r.right,v.right))/2,
                y=(Math.max(r.top,v.top)+Math.min(r.bottom,v.bottom))/2;
              const event=(type,dx)=>new PointerEvent(type,{bubbles:true,cancelable:true,pointerType:'pen',
                pointerId:73,clientX:x+dx,clientY:y,pressure:.6,buttons:type==='pointerup'?0:1});
              canvas.dispatchEvent(event('pointerdown',0));
              if(!penContactActive||!penTouchBlocked())throw Error('Browser Pencil contact did not reject palm');
              canvas.dispatchEvent(event('pointermove',10));canvas.dispatchEvent(event('pointerup',20));
              if(!penTouchBlocked())throw Error('Browser Pencil-up grace missing');
            })()''')
            await self.idle(panel)
            assert len(panel.editor.notebook.page(0).strokes) == before + 1
            await asyncio.sleep(.4)
            assert not (await self.snapshot(panel))['blocked']
        finally:
            await panel.web.evaluate_javascript('canvas.setPointerCapture=window.palmCapture;delete window.palmCapture;resetPenRejection()')
        result['tests'].append('ios_browser_pen_contact_fallback_and_grace')


def main():
    return NotebookPalmProbe('Notebook palm QA', BUNDLE)
