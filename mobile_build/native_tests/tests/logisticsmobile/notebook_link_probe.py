"""Internal PDF links through native taps and the real notebook WebView bridge."""
import asyncio
import base64
from io import BytesIO
import json
from pathlib import Path
import traceback
from commonUtils.testing.stages import TestStage
from .notebook_probe import NotebookProbe
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


def fixture():
    from pypdf import PdfWriter
    from pypdf.annotations import Link
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(300, 600)
    writer.add_annotation(0, Link(rect=(30, 330, 150, 450), target_page_index=2))
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class Probe(NotebookProbe):
    async def wait(self, predicate, message):
        for _ in range(160):
            if predicate():
                return
            await asyncio.sleep(.05)
        raise AssertionError(message)

    async def ios_touch(self, point, end=None):
        cache = Path(self.paths.cache)
        done = cache / 'notes-touch-done'
        done.unlink(missing_ok=True)
        request = dict(action='tap' if end is None else 'swipe', points=list(point) if end is None else [*point, *end])
        (cache / 'notes-touch-request.json').write_text(json.dumps(request))
        await self.wait(done.exists, 'Simulator touch driver did not acknowledge request')
        done.unlink()
        await asyncio.sleep(.15)

    async def android_gesture(self, native, point, *, end=None, tool=1, cancel=False, moved_back=False):
        from java import jarray
        from android.os import SystemClock
        from android.view import MotionEvent, InputDevice
        start = SystemClock.uptimeMillis()
        async def deliver(action, p, tick):
            props = jarray(MotionEvent.PointerProperties)(1)
            coords = jarray(MotionEvent.PointerCoords)(1)
            props[0] = MotionEvent.PointerProperties()
            props[0].id, props[0].toolType = 4, tool
            coords[0] = MotionEvent.PointerCoords()
            coords[0].x, coords[0].y = p
            coords[0].pressure, coords[0].size = .6, 1.
            event = MotionEvent.obtain(start, start+tick, action, 1, props, coords, 0, 0, 1., 1., 0, 0,
                InputDevice.SOURCE_STYLUS if tool == 2 else InputDevice.SOURCE_TOUCHSCREEN, 0)
            try:
                native.dispatchTouchEvent(event)
            finally:
                event.recycle()
            await asyncio.sleep(.08)
        await deliver(0, point, 0)
        if end is not None:
            await deliver(2, end, 20)
        if moved_back:
            await deliver(2, point, 40)
        await deliver(3 if cancel else 1, point if moved_back or end is None else end, 60)

    async def pdf_point(self, canvas, x=.3, y=.35):
        impl = canvas._impl
        if self.apple:
            from rubicon.objc import CGPoint
            size = impl.picture.bounds.size
            point = impl.picture.convertPoint_toView_(CGPoint(size.width*x, size.height*y), None)
            return [float(point.x), float(point.y)]
        from java import jarray, jfloat
        native = impl.native
        image = native.getDrawable()
        point = jarray(jfloat)([image.getIntrinsicWidth()*x, image.getIntrinsicHeight()*y])
        native.getImageMatrix().mapPoints(point)
        return [float(point[0])+native.getPaddingLeft(), float(point[1])+native.getPaddingTop()]

    async def touch_pdf(self, canvas, **kwargs):
        point = await self.pdf_point(canvas)
        if self.apple:
            await self.ios_touch(point, **kwargs)
        else:
            await self.android_gesture(canvas._impl.native, point, **kwargs)

    async def check(self, app):
        output = Path(self.paths.cache) / 'link-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, physical_pen=False, cases=[], artifacts={})
        panel = None
        try:
            await self.wait(lambda: not getattr(self, '_startup_in_progress', False), 'Startup did not finish')
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            self.apple = type(app._impl).__module__.startswith('toga_iOS.')
            report['backend'] = type(app._impl).__module__
            if self.apple:
                # Require the host's real simulator touch protocol, never a fake selector argument.
                assert (Path(self.paths.cache) / 'drive-link-touches').exists(), 'iOS requires the owned Duo touch driver'
            path = self.private_root / 'linked.pdf'
            path.write_bytes(fixture())
            assert await self.open_download(path=path)
            owner = self.private_sessions.active
            canvas = owner.crypt_image
            await asyncio.sleep(.5)
            assert owner.crypt_reader.pdf_navigation.indices == (0,)
            for zoom in (1, 2):
                canvas.set_zoom(zoom)
                await asyncio.sleep(.2)
                await self.touch_pdf(canvas)
                await self.wait(lambda: canvas.return_page is not None, 'Native finger tap did not follow PDF link')
                assert owner.crypt_reader.pdf_navigation.indices[0] == 2
                assert not owner.reading_frame.immersive
                await capture_window(self, output / f'pdf-undo-{zoom}.png')
                await canvas.undo_link()
                assert owner.crypt_reader.pdf_navigation.indices[0] == 0
                report['cases'].append(f'native_pdf_finger_link_and_undo_zoom_{zoom}')
            if not self.apple:
                point = await self.pdf_point(canvas)
                native = canvas._impl.native
                for label, kwargs in [('cancel', dict(cancel=True)), ('pen', dict(tool=2)),
                                      ('move_out_back', dict(end=[point[0]+60, point[1]], moved_back=True))]:
                    await self.android_gesture(native, point, **kwargs)
                    await asyncio.sleep(.2)
                    assert owner.crypt_reader.pdf_navigation.indices[0] == 0, label
                    report['cases'].append('android_pdf_no_link_'+label)
            await self.touch_pdf(canvas)
            await self.wait(lambda: canvas.return_page is not None, 'Expiry fixture did not navigate')
            await asyncio.sleep(3.2)
            assert canvas.return_page is None and not canvas.return_box.children
            report['cases'].append('native_pdf_real_timer_expiry')
            owner.clear_private_reader()
            from features.pdf.annotation import notebook_from_pdf
            notebook = self.private_root / 'linked.rmdoc'
            notebook.write_bytes(notebook_from_pdf(fixture(), 'Native link QA').to_bytes())
            assert await self.open_download(path=notebook)
            panel = self.notebook_panel
            await self.wait(lambda: panel.editor is not None, 'Notebook editor absent')
            await asyncio.sleep(.5)
            for finger in (False, True):
                await panel.web.evaluate_javascript("paperView='pro';$('paperView').value=paperView;setZoom('page');$('finger').checked="+json.dumps(finger))
                await asyncio.sleep(.15)
                point = json.loads(await panel.web.evaluate_javascript(r'''(()=>{
                  const r=canvas.getBoundingClientRect();return JSON.stringify({
                    x:r.left+r.width*.3,y:r.top+r.height*.35,w:innerWidth,h:innerHeight})
                })()'''))
                if self.apple:
                    from rubicon.objc import CGPoint
                    native = panel.web._impl.native
                    # WKWebView coordinates are CSS points at page scale 1.
                    p = native.convertPoint_toView_(CGPoint(point['x'], point['y']), None)
                    await self.ios_touch([float(p.x), float(p.y)])
                else:
                    native = panel.web._impl.native
                    scale = native.getWidth()/point['w']
                    await self.android_gesture(native, [point['x']*scale, point['y']*scale])
                await self.wait(lambda: panel.editor.index == 2, 'Native notebook finger tap did not navigate')
                assert await panel.web.evaluate_javascript('!undoPageJump.hidden')
                assert not panel.editor.undo, 'Link tap added ink/history'
                await capture_window(self, output / ('notebook-undo-'+str(finger)+'.png'))
                await panel.web.evaluate_javascript('undoPageJump.click()')
                await self.wait(lambda: panel.editor.index == 0, 'Notebook undo did not return')
                report['cases'].append('native_notebook_finger_link_drawing_'+str(finger))
            if not self.apple:
                before = len(panel.editor.notebook.page(0).strokes)
                await self.android_gesture(native, [point['x']*scale, point['y']*scale], tool=2)
                await self.wait(lambda: len(panel.editor.notebook.page(0).strokes) > before, 'Native pen did not draw')
                assert panel.editor.index == 0
                report['cases'].append('native_android_notebook_pen_draws_without_link')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            try:
                await capture_window(self, output / 'failure.png')
            except Exception:
                pass
        finally:
            if panel is not None:
                panel.dispose()
            report['artifacts'] = {p.name: base64.b64encode(p.read_bytes()).decode() for p in output.glob('*.png')}
            (Path(self.paths.cache) / 'notebook-link-result.json').write_text(json.dumps(report, indent=2))


def main():
    return Probe('PDF and notebook link QA', BUNDLE)
