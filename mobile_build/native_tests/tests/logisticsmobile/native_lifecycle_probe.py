"""Isolated native navigation/canvas/speech acceptance; synthetic content only.

Stage as a separate-bundle app entry point. Reports include loaded source hashes;
dummy adapters are refused. Keep reports in ignored native-validation evidence.
"""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import gc
from hashlib import sha256
import json
import marshal
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import struct
import traceback
import weakref
import zlib

import toga
from toga.platform import get_factory
from toga.style import Pack
from commonUtils.ui.native import image_canvas, navigation, speech

BUNDLE = 'io.github.ispaure.logisticsnativelifecycle'
ITEMS = (('home', 'Home', 'house', 'home'), ('notes', 'Notes', 'doc', 'ic_menu_edit'))


def fingerprint(module):
    # Chaquopy imports from packaged bytecode rather than extracted .py files.
    try:
        payload, kind = Path(module.__file__).read_bytes(), 'source'
    except FileNotFoundError:
        payload = marshal.dumps(module.__loader__.get_code(module.__name__))
        kind = 'loaded_bytecode'
    return dict(kind=kind, sha256=sha256(payload).hexdigest())


def sample_image():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + bytes((x % 256, y % 256, 128)) * 128 for y, x in enumerate(range(128)))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 128, 128, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class NativeLifecycleProbe(toga.App):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from commonUtils.ui.native.event_loop import bind_cooperative_loop
        bind_cooperative_loop(self.loop)

    def startup(self):
        self.run_id = uuid4().hex
        self.visibility_events = []
        self.resize_events = 0
        self.status = toga.Label('Running native lifecycle checks', style=Pack(margin=12))
        self.placeholder = toga.Box(children=[self.status], style=Pack(direction='column', flex=1))
        self.main_window = toga.MainWindow(title='Native lifecycle validation')
        self.main_window.on_resize = self.resized
        self.main_window.on_show = lambda window: self.visibility_events.append('show')
        self.main_window.on_hide = lambda window: self.visibility_events.append('hide')
        self.main_window.content = self.placeholder
        self.main_window.show()

    def resized(self, window):
        self.resize_events += 1

    def on_running(self):
        self.loop.create_task(self.validate())

    async def validate(self):
        backend = get_factory().WebView.__module__
        self.apple = backend.startswith('toga_iOS.')
        report = dict(backend=backend, pid=os.getpid(), run_id=self.run_id, cases=[], source={
            name: fingerprint(module)
            for name, module in (('navigation', navigation), ('image_canvas', image_canvas), ('speech', speech))})
        try:
            assert self.apple or backend.startswith('toga_android.'), 'A genuine mobile backend is required'
            await asyncio.sleep(.5)
            for name, check in (('navigation', self.navigation_cycles), ('canvas', self.canvas_cycles),
                                ('speech', self.speech_cycles)):
                try:
                    details = await check()
                    report['cases'].append(dict(name=name, passed=True, details=details))
                except Exception:
                    report['cases'].append(dict(name=name, passed=False, error=traceback.format_exc()))
            report['passed'] = all(case['passed'] for case in report['cases'])
        except Exception:
            report['error'] = traceback.format_exc()
            report['passed'] = False
        finally:
            self.main_window.content = self.placeholder
        self.status.text = 'Native lifecycle: ' + ('PASS' if report['passed'] else 'FAIL')
        report['visibility_events'] = self.visibility_events
        path = Path(self.paths.cache) / 'native-lifecycle.json'
        path.write_text(json.dumps(report, indent=2) + '\n')
        print('NATIVE_LIFECYCLE=' + json.dumps(report), flush=True)

    async def checkpoint(self, name, inspect):
        cache = Path(self.paths.cache)
        if not (cache / 'native-lifecycle-external').exists():
            return
        for tick in range(600):
            if not self.apple:
                from org.beeware.android import MainActivity
                assert MainActivity.singletonThis == self._impl.native, 'Probe Activity was replaced; this run requires in-place configuration changes'
            (cache / 'native-lifecycle-phase.json').write_text(json.dumps(dict(
                name=name, pid=os.getpid(), run_id=self.run_id, tick=tick, state=inspect())))
            ack = cache / 'native-lifecycle-continue'
            if ack.exists() and ack.read_text() == name:
                return
            await asyncio.sleep(.1)
        raise TimeoutError('External native lifecycle driver did not acknowledge ' + name)

    async def navigation_cycles(self):
        results = []
        selected = []
        host = navigation.NativeNavigationHost(ITEMS, on_select=lambda key: selected.append(key))
        self.main_window.content = host.root
        try:
            # A failed backend admission must not poison the next real install.
            try:
                host.install(object())
            except AttributeError:
                pass
            assert host.window is None and host.adapter is None, 'Failed install retained its window'
            for cycle in range(3):
                original_resize = self.main_window.on_resize
                host.install(self.main_window)
                adapter = host.adapter
                host.activate('notes')
                await asyncio.sleep(.2)
                before = adapter.diagnostics()
                assert before['main_thread']
                assert host.state.destination == 'notes'
                if cycle == 0:
                    await self.checkpoint('navigation', adapter.diagnostics)
                    assert host.state.destination == 'notes'
                host.chrome.set_hidden(True)
                await asyncio.sleep(.1)
                host.chrome.restore()
                if not self.apple:
                    adapter.set_mode('rail')
                    adapter.set_mode('bottom')
                    selection_listener = adapter.impl.onItemSelectedListener
                    menu_item = adapter.bottom.getMenu().getItem(0)
                host.uninstall()
                assert host.window is None and host.adapter is None
                assert self.main_window.on_resize == original_resize
                # Simulate a layout event already queued at native detachment.
                if self.apple:
                    container = self.main_window._impl.container
                    baseline = tuple(getattr(container, edge + '_inset') for edge in ('top', 'bottom', 'left', 'right'))
                    try:
                        for edge in ('top', 'bottom', 'left', 'right'):
                            setattr(container, edge + '_inset', 17)
                        adapter.layout_window(container)
                        assert all(getattr(container, edge + '_inset') == 17 for edge in ('top', 'bottom', 'left', 'right'))
                    finally:
                        for edge, value in zip(('top', 'bottom', 'left', 'right'), baseline):
                            setattr(container, edge + '_inset', value)
                else:
                    events = adapter.layout_events
                    adapter.window_resized(self.main_window)
                    adapter.resize_content()
                    adapter.content_refreshed()
                    assert not selection_listener.onNavigationItemSelected(menu_item)
                    assert adapter.layout_events == events, 'Retired adapter processed a resize'
                host.uninstall()
                results.append(before)
            assert not selected, 'Programmatic selection leaked to the host callback'
        finally:
            host.dispose()
            self.main_window.content = self.placeholder
        return results

    async def canvas_cycles(self):
        results = []
        for cycle in range(3):
            events = []
            canvas = image_canvas.ImageCanvas(image=toga.Image(data=sample_image()),
                on_page=lambda step: events.append(step), on_toggle=lambda: events.append('toggle'),
                magnifier_enabled=True, style=Pack(flex=1))
            self.main_window.content = toga.Box(children=[canvas], style=Pack(flex=1))
            try:
                await asyncio.sleep(.3)
                canvas.set_zoom(2)
                assert abs(canvas.zoom_scale - 2) < .1
                canvas.fit_page()
                impl = canvas._impl
                listener = getattr(impl, 'listener', None)
                if cycle == 0:
                    await self.checkpoint('canvas', lambda: dict(zoom=canvas.zoom_scale, pixels=canvas.image is not None))
                # Enter native gesture handlers while live, then replay them retired.
                if self.apple:
                    from rubicon.objc import CGPoint
                    impl.native.toggleControls_(impl.tap)
                    impl.native.pageSwipe_(impl.swipes[0])
                    original_hold = impl.hold
                    def location(target):
                        return impl.picture.convertPoint(CGPoint(impl.picture.bounds.size.width / 2,
                            impl.picture.bounds.size.height / 2), toView=target)
                    impl.hold = SimpleNamespace(locationInView=location)
                    try:
                        impl.show_magnifier(impl.hold)
                        assert impl.lens is not None
                        lens_picture = impl.lens_picture
                    finally:
                        impl.hold = original_hold
                else:
                    listener.toggleControls()
                    listener.page(1)
                assert len(events) == 2, 'Live native gesture handlers did not publish'
                events.clear()
                canvas.dispose()
                canvas.dispose()
                assert canvas.image is None
                if self.apple:
                    assert impl.native.delegate is None
                    assert not impl.native.isUserInteractionEnabled()
                    assert impl.picture.image is None
                    assert lens_picture.image is None and impl.lens is None
                    # Enter the real Objective-C gesture target after retirement.
                    impl.native.toggleControls_(impl.tap)
                    impl.native.pageSwipe_(impl.swipes[0])
                else:
                    assert impl.listener is None
                    if listener is not None:
                        listener.page(1)
                        listener.toggleControls()
                canvas.page(1)
                canvas.toggle_controls()
                assert not events, 'A retired canvas published a gesture'
                results.append(dict(cycle=cycle, zoom=canvas.zoom_scale, pixels_cleared=True))
            finally:
                canvas.dispose()
                self.main_window.content = self.placeholder
        return results

    async def speech_cycles(self):
        results = []
        for cycle in range(3):
            engine = speech.NativeSpeech(self.loop)
            events = []

            class Receiver:
                def delivered(self, *args):
                    events.append(args)

            receiver = Receiver()
            retained = weakref.ref(receiver)
            for name in ('completed', 'failed', 'progress', 'started'):
                setattr(engine, name, receiver.delivered)
            del receiver
            try:
                for _ in range(100):
                    if engine.ready or engine.error:
                        break
                    await asyncio.sleep(.1)
                voices = len(engine.voices)
                assert engine.ready, engine.error
                engine.speak('Native lifecycle validation. This is synthetic speech.', engine.default_voice, 1., str(cycle))
                for _ in range(40):
                    if events:
                        break
                    await asyncio.sleep(.1)
                assert events, 'No native speech callback arrived'
                engine.stop()
                assert engine.ready, 'Stop retired a reusable speech engine'
                events.clear()
                engine.speak('Speech restarted.', engine.default_voice, 1., 'restart-' + str(cycle))
                for _ in range(40):
                    if events:
                        break
                    await asyncio.sleep(.1)
                assert events, 'Speech did not restart after stop'
                if cycle == 0:
                    await self.checkpoint('speech', lambda: dict(ready=engine.ready, callbacks=len(events)))
                engine.deliver('queued-before-close')
                engine.close()
                engine.close()
                count = len(events)
                engine.deliver('late')
                engine.begin('late')
                engine.word_range('late', 0, 1)
                engine.failure('late')
                await asyncio.sleep(.3)
                assert len(events) == count, 'Retired speech delivered a callback'
                gc.collect()
                assert retained() is None, 'Closed speech retained its presentation callbacks'
                if self.apple:
                    assert engine.native.delegate is None
                results.append(dict(cycle=cycle, voices=voices, native_callbacks=count))
            finally:
                engine.close()
        return results


def main():
    # Logistics' existing iOS native launcher names this delegate explicitly.
    # Use Toga's ordinary scene lifecycle; the probe has no application services.
    if get_factory().WebView.__module__.startswith('toga_iOS.'):
        from toga_iOS.app import PythonAppDelegate

        class LogisticsSceneAppDelegate(PythonAppDelegate):
            pass

    return NativeLifecycleProbe('Native lifecycle validation', BUNDLE)
