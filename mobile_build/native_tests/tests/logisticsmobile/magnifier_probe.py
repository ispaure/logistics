"""Native lens buttons, shared preferences, speech toggle and pixel cleanup."""
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
from mobile.app import LogisticsMobile
from mobile.magnifier import bind
from mobile.preferences import Preferences


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
                    # Moving a live lens must translate the existing native
                    # layers, retain their sizes, and keep the sampled pixels
                    # centered without rebuilding the overlay or buttons.
                    parent = impl.native.superview
                    if callable(parent):parent = parent()
                    picture = impl.lens_picture
                    initial_size = (picture.bounds.size.width, picture.bounds.size.height)
                    for fraction in (.25, .75, .5):
                        def moved(target):
                            return impl.picture.convertPoint(CGPoint(impl.picture.bounds.size.width*fraction,
                                impl.picture.bounds.size.height*.65),toView=target)
                        impl.show_magnifier(SimpleNamespace(locationInView=moved))
                        assert impl.lens_picture == picture and impl.lens_less == less and impl.lens_more == more
                        assert (picture.bounds.size.width, picture.bounds.size.height) == initial_size
                        from commonUtils.ui.native.image_canvas import magnifier_geometry
                        rect = impl.native.convertRect(impl.native.bounds,toView=parent)
                        thumb = moved(parent)
                        geometry = magnifier_geometry(rect.size.width,rect.size.height,
                            thumb.x-rect.origin.x,thumb.y-rect.origin.y)
                        sample = impl.picture.convertPoint(CGPoint(rect.origin.x+geometry[4],
                            rect.origin.y+geometry[5]),fromView=parent)
                        scale = canvas.magnifier_zoom/100*float(impl.native.zoomScale)
                        assert abs(picture.frame.origin.x+sample.x*scale-geometry[2]/2)<.01
                        assert abs(picture.frame.origin.y+sample.y*scale-geometry[3]/2)<.01
                    def click(button):button.sendActionsForControlEvents(64)
                    def enabled(button):return bool(button.isEnabled())
                    parent = impl.native.superview
                    if callable(parent):parent = parent()
                    for button in (less,more):
                        assert float(button.bounds.size.width) == 33
                        assert float(button.bounds.size.height) == 33
                        assert float(button.frame.origin.y) >= float(impl.lens.frame.origin.y + impl.lens.frame.size.height - 33)
                        point = button.convertPoint(CGPoint(16.5,16.5),toView=parent)
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
                    assert popup.getContentView().getChildCount() == 2
                    less, more = popup.getContentView().getChildAt(0),popup.getContentView().getChildAt(1)
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
                    assert not hasattr(impl, 'lens_label')
                    impl.hide_magnifier();impl.hold = original_hold
                    assert impl.lens is None
                else:
                    assert native.getMagnifierZoom()==170
                    touch(1)
                    assert not popup.isShowing()
                result[name] = dict(buttons=True,bounds=True,shared=True,persisted=True)
            self.show_settings()
            self.settings_navigation.choose('Books & Comics')
            self.magnifier_choice.value = '230%'
            assert comic.magnifier_zoom == pdf.magnifier_zoom == 230
            assert Preferences(self.private_root).values['magnifier_zoom']=='230'
            for canvas in canvases:
                canvas.dispose()
                assert canvas.image is None and canvas.on_magnifier_zoom is None
            from features.books.mobile.speech_view import ReadAloudPanel
            class Engine:
                ready, error, default_voice = True, '', 'Offline test voice'
                voices = {'Offline test voice': None}
                def voice_for_language(self, language, preferred):return self.default_voice
                def speak(self, *args):pass
                def stop(self):pass
                def close(self):pass
            async def source():return SimpleNamespace(text='Read this sentence aloud.'),0,None
            panel = ReadAloudPanel(loop=self.loop,source=source,on_range=lambda *a:None,
                close=lambda w:None,engine=Engine())
            self.show_view(panel,destination='documents',route='speech-toggle',title='Read aloud')
            await panel.ready_task
            assert sum(getattr(button,'control_icon','') in ('play','pause')
                for button in panel.play_button.parent.children)==1
            await panel.toggle_playback()
            assert panel.session.state=='speaking' and panel.play_button.control_icon=='pause'
            await self.phase('speech-toggle')
            await panel.toggle_playback()
            assert panel.session.state=='paused' and panel.play_button.control_icon=='play'
            await panel.toggle_playback()
            assert panel.session.state=='speaking' and panel.play_button.control_icon=='pause'
            panel.session.stop()
            assert panel.play_button.control_icon=='play'
            panel.dispose()
            result['speech_single_toggle'] = True
            assert not events,events
            result.update(success=True,settings=True,no_page_or_toggle=True,cleanup=True)
        except BaseException:result['error'] = traceback.format_exc()
        (Path(self.paths.cache)/'magnifier-probe-result.json').write_text(json.dumps(result,indent=2))
