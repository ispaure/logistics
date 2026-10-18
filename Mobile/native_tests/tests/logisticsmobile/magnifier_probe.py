"""Native lens controls, shared preferences and pixel cleanup on synthetic pages."""
import asyncio
import json
from pathlib import Path
import struct
import traceback
from types import SimpleNamespace
from uuid import uuid4
import zlib
import toga
from toga.style import Pack
from commonUtils.runtime.platform import get_os, OS
from commonUtils.ui.native.image_canvas import ImageCanvas
from features.pdf.mobile.canvas import PDFCanvas
from logisticsmobile.app import LogisticsMobile
from logisticsmobile.magnifier import bind
from logisticsmobile.preferences import Preferences


def grid():
    width, height = 300, 420
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            pixel = (25,35,60) if x%20<2 or y%20<2 else (220,235,250) if (x//20+y//20)%2 else (255,255,255)
            row.extend(pixel)
        rows.append(bytes(row))
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')


class MagnifierProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache)/('magnifier-'+uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self,'_magnifier_probe_started',False):
            self._magnifier_probe_started = True
            self.loop.create_task(self.probe())

    async def phase(self, name):
        cache = Path(self.paths.cache)
        # Publish only after the Android popup and image have drawn this zoom.
        await asyncio.sleep(.25)
        state = {'name':name,'preferences':str(self.preferences.path)}
        if get_os() is OS.ANDROID:
            from java import jarray,jint
            position = jarray(jint)(2)
            self._probe_less.getLocationOnScreen(position)
            state['less'] = [int(position[0])+self._probe_less.getWidth()//2,
                int(position[1])+self._probe_less.getHeight()//2]
        (cache/'magnifier-probe-phase.json').write_text(json.dumps(state))
        from .fixtures import capture_window
        await capture_window(self, cache/('magnifier-'+name+'.png'))
        await asyncio.sleep(2)

    async def probe(self):
        result = dict(success=False, platform='ios' if get_os() is OS.IOS else 'android')
        canvases = []
        try:
            events = []
            for name, kind in (('comic',ImageCanvas),('pdf',PDFCanvas)):
                canvas = bind(self,kind(image=toga.Image(src=grid()),on_page=lambda value:events.append(value),
                    on_toggle=lambda:events.append('toggle'),style=Pack(flex=1)))
                canvases.append(canvas)
                canvas.magnifier_enabled = True
            comic, pdf = canvases
            for name, canvas in (('comic',comic),('pdf',pdf)):
                self.show_view(toga.Box(children=[canvas],style=Pack(flex=1)),destination='documents',
                    route='magnifier-'+name,title=name.title()+' magnifier')
                await asyncio.sleep(.5)
                impl = canvas._impl
                apple = get_os() is OS.IOS
                if apple:
                    from rubicon.objc import CGPoint
                    original_hold = impl.hold
                    def location(target):
                        return impl.picture.convertPoint(CGPoint(impl.picture.bounds.size.width/2,
                            impl.picture.bounds.size.height*.65),toView=target)
                    impl.hold = gesture = SimpleNamespace(locationInView=location,enabled=True)
                    impl.show_magnifier(gesture)
                    less, more = impl.lens_less, impl.lens_more
                    def click(button):button.sendActionsForControlEvents(64)
                    def enabled(button):return bool(button.isEnabled())
                    parent = impl.native.superview
                    if callable(parent):parent = parent()
                    for button in (less,more):
                        point = button.convertPoint(CGPoint(22,22),toView=parent)
                        hit = parent.hitTest(point,withEvent=None)
                        assert hit == button or hit.isDescendantOfView(button), 'Lens button is not touchable'
                else:
                    from java import jclass
                    native = impl.native
                    Motion = jclass('android.view.MotionEvent')
                    clock = jclass('android.os.SystemClock')
                    started = clock.uptimeMillis()
                    def touch(action):
                        event = Motion.obtain(started,clock.uptimeMillis(),action,
                            native.getWidth()/2.,native.getHeight()*.65,0)
                        try:native.onTouchEvent(event)
                        finally:event.recycle()
                    touch(0)
                    await asyncio.sleep(.55)
                    field = native.getClass().getDeclaredField('lensControls');field.setAccessible(True)
                    popup = field.get(native)
                    assert popup is not None and popup.isShowing() and popup.isSplitTouchEnabled()
                    less, more = popup.getContentView().getChildAt(1),popup.getContentView().getChildAt(2)
                    self._probe_less = less
                    def click(button):assert button.performClick()
                    def enabled(button):return bool(button.isEnabled())
                while canvas.magnifier_zoom < 250:click(more)
                assert not enabled(more) and enabled(less)
                assert comic.magnifier_zoom == pdf.magnifier_zoom == 250
                assert Preferences(self.private_root).values['magnifier_zoom']=='250'
                await self.phase(name)
                if not apple:assert popup.isShowing(), 'Touching lens controls dismissed the magnifier'
                while canvas.magnifier_zoom > 150:click(less)
                assert not enabled(less) and enabled(more)
                assert comic.magnifier_zoom == pdf.magnifier_zoom == 150
                click(more)
                assert comic.magnifier_zoom == pdf.magnifier_zoom == 170
                if apple:
                    assert impl.lens_label.text == '170%'
                    impl.hide_magnifier();impl.hold = original_hold
                    assert impl.lens is None
                else:
                    assert native.getMagnifierZoom()==170
                    touch(1)
                    assert not popup.isShowing()
                result[name] = dict(buttons=True,bounds=True,shared=True,persisted=True)
            self.show_settings()
            self.magnifier_choice.value = '230%'
            assert comic.magnifier_zoom == pdf.magnifier_zoom == 230
            assert Preferences(self.private_root).values['magnifier_zoom']=='230'
            for canvas in canvases:
                canvas.dispose()
                assert canvas.image is None and canvas.on_magnifier_zoom is None
            assert not events,events
            result.update(success=True,settings=True,no_page_or_toggle=True,cleanup=True)
        except BaseException:result['error'] = traceback.format_exc()
        (Path(self.paths.cache)/'magnifier-probe-result.json').write_text(json.dumps(result,indent=2))
