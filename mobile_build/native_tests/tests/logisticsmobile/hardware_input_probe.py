"""Generated fixtures for native focus and pageable WebView input."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "marcandre.voyer@gmail.com"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path
import traceback

import toga
from toga.style import Pack
from commonUtils.testing.stages import TestStage
from commonUtils.testing.waiting import wait_until
from commonUtils.ui.native.inline_html import set_inline_html
from features.books.mobile.presentation import chapter_view
from mobile.clipboard import KEY, controller
from mobile.native.file_shortcuts import focus, focused
from .clipboard_probe import ClipboardProbe, OTHER

TEST_STAGE = TestStage.REGRESSION
RESULT = 'hardware-input-result.json'


class HardwareInputProbe(ClipboardProbe):
    def send_file_key(self, widget, key):
        if self.policy.android:
            from android.view import KeyEvent
            code = KeyEvent.KEYCODE_X if key == 'x' else KeyEvent.KEYCODE_V
            activity = self._impl.native
            assert activity.dispatchKeyEvent(KeyEvent(0, 0, KeyEvent.ACTION_DOWN, code, 0, KeyEvent.META_CTRL_ON))
            assert activity.dispatchKeyEvent(KeyEvent(0, 0, KeyEvent.ACTION_DOWN, code, 1, KeyEvent.META_CTRL_ON))
            assert activity.dispatchKeyEvent(KeyEvent(0, 0, KeyEvent.ACTION_UP, code, 0, KeyEvent.META_CTRL_ON))
        else:
            from rubicon.objc import ObjCClass, SEL, objc_id, send_message
            from ctypes import c_bool
            from commonUtils.ui.native.keyboard import native_value
            binding = widget._file_key_binding
            command = next(item for item in native_value(binding.keyCommands) if str(item.input) == key)
            assert int(command.modifierFlags) == 1 << 20
            assert send_message(ObjCClass('UIApplication').sharedApplication, 'sendAction:to:from:forEvent:',
                SEL('logisticsMoveFiles:'), None, command, None,
                restype=c_bool, argtypes=[SEL, objc_id, objc_id, objc_id])

    def mouse_scroll(self, widget, *, horizontal=0., vertical=0., timestamp=None):
        from android.os import SystemClock
        from android.view import InputDevice, MotionEvent
        from java import jarray

        native = widget._impl.native
        coords = jarray(MotionEvent.PointerCoords)(1)
        coords[0] = MotionEvent.PointerCoords()
        coords[0].x, coords[0].y = 20., 90.
        coords[0].setAxisValue(MotionEvent.AXIS_VSCROLL, vertical)
        coords[0].setAxisValue(MotionEvent.AXIS_HSCROLL, horizontal)
        props = jarray(MotionEvent.PointerProperties)(1)
        props[0] = MotionEvent.PointerProperties()
        props[0].id, props[0].toolType = 0, MotionEvent.TOOL_TYPE_MOUSE
        time = SystemClock.uptimeMillis() if timestamp is None else timestamp
        event = MotionEvent.obtain(time, time, MotionEvent.ACTION_SCROLL, 1, props, coords,
            0, 0, 1., 1., 0, 0, InputDevice.SOURCE_MOUSE, 0)
        try:
            return bool(native.dispatchGenericMotionEvent(event))
        finally:
            event.recycle()

    async def check_file_move(self):
        assert await self.show_files(location=('Local files', ''))
        root = self.file_provider.root
        (root / 'Destination').mkdir()
        for name in ('Move alpha.txt', 'Move beta.txt'):
            (root / name).write_text(name)
        for index in range(45):
            (root / f'row-{index:02d}.txt').touch()
        assert await self.browse_files()
        browser = self.file_browser
        await asyncio.sleep(.5)
        if self.policy.android:
            self.mouse_scroll(browser.native_list, vertical=-6.)
            assert browser.vertical_position > 0
        release = self.protection.register(object(), lambda: (), protected=lambda: True)
        try:
            assert self.policy.restricted()
            self.seed(OTHER)
            self.begin_file_selection()
            for entry in browser.tree.entries.values():
                if entry.label.startswith('Move '):
                    self.check_file_entry(entry)
            assert len(self.file_checked) == 2
            focus(browser.native_list)
            assert focused(browser.native_list)
            self.send_file_key(browser.native_list, 'x')
            assert len(self.pending_file_cut()[1]) == 2
            assert self.access() == OTHER
            browser.open_search()
            await asyncio.sleep(.25)
            assert not focused(browser.native_list)
            self.shortcut(browser.search._impl.native, 'paste')
            assert browser.search.value == '' and len(self.pending_file_cut()[1]) == 2
            browser.close_search()
            focus(browser.native_list)
            assert focused(browser.native_list), 'Listing could not regain focus after search'

            assert await self.browser_file_location(('Local files', 'Destination'))
            assert browser.empty_label.parent is browser.widget
            if not self.policy.android:
                # A folder push replaces the active native controller. Invoke
                # the new listing's tap action after its view is on screen.
                from commonUtils.ui.native.keyboard import native_value
                await wait_until(lambda: native_value(browser.empty_label._impl.native.window) is not None,
                                 timeout=4, message='The destination folder is offscreen')
                focus(browser.empty_label)
            assert focused(browser.empty_label), 'The empty listing does not own keyboard focus'
            self.send_file_key(browser.empty_label, 'v')
            await asyncio.wait_for(self._file_paste_shortcut_task, 35)
            assert self.pending_file_cut() is None
            assert self.access() == OTHER
            for name in ('Move alpha.txt', 'Move beta.txt'):
                assert (root / 'Destination' / name).read_text() == name
                assert not (root / name).exists()
        finally:
            release()

    async def check_reader(self, web):
        paragraphs = '<p>Generated EPUB passage with enough words to paginate the viewport.</p>' * 780
        head = '<html><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        chapter_view(head + '<body>' + paragraphs + '</body></html>', web, motion_enabled=False)
        for _ in range(60):
            await asyncio.sleep(.15)
            state = json.loads(await web.evaluate_javascript(
                'JSON.stringify(window.reader ? window.reader.pagination() : null)'))
            if state and state['count'] > 8:
                break
        assert state and state['count'] > 8, state

        async def js(source):
            return await web.evaluate_javascript('(() => {' + source + '})()')

        assert await js("""
          window.qaWheel = (x,y,target=document.body,mode=0,ctrlKey=false) => {
            const e=new WheelEvent('wheel',{deltaX:x,deltaY:y,deltaMode:mode,bubbles:true,cancelable:true,ctrlKey});
            target.dispatchEvent(e);return e.defaultPrevented;
          };
          window.qaKey=(key,target=document.body,options={})=>{
            const e=new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true,...options});
            target.dispatchEvent(e);return e.defaultPrevented;
          };
          window.qaIndex=()=>reader.pagination().index;
          window.qaColumns=()=>reader.pagination().columns;
          return true;
        """)
        assert await js("""
          for(let i=0;i<14;i++)qaWheel(0,0.3);
          if(qaIndex()!==0)return false;
          for(let i=0;i<30;i++)qaWheel(0,8);
          return qaIndex()===qaColumns();
        """), 'vertical fractional wheel or burst limit'
        await asyncio.sleep(.3)
        assert await js("""
          for(let i=0;i<16;i++)qaWheel(8,1);
          return qaIndex()===2*qaColumns();
        """), 'horizontal wheel'
        await asyncio.sleep(.3)
        assert await js("""
          const nested=document.body.appendChild(document.createElement('div'));
          Object.assign(nested.style,{position:'fixed',width:'50px',height:'50px',overflow:'auto'});
          const content=nested.appendChild(document.createElement('div'));
          Object.assign(content.style,{width:'300px',height:'300px'});
          const pass=!qaWheel(80,0,content)&&!qaWheel(0,80,content);
          nested.remove();
          return pass&&qaIndex()===2*qaColumns();
        """), 'nested scroll ownership'
        assert await js("""
          const input=document.body.appendChild(document.createElement('textarea'));
          input.focus();
          const pass=!qaKey('ArrowRight',input)&&!qaKey('PageDown',input)&&!qaKey(' ',input)
            &&!qaKey('ArrowRight',document.body,{shiftKey:true})&&!qaWheel(0,80,document.body,0,true);
          input.remove();
          return pass&&qaIndex()===2*qaColumns();
        """), 'focused input and modified gestures'
        original = json.loads(await web.evaluate_javascript('JSON.stringify(reader.pagination())'))
        await web.evaluate_javascript('reader.setGeometry({seam:0.5,gap:0.04})')
        folded = json.loads(await web.evaluate_javascript('JSON.stringify(reader.pagination())'))
        assert folded['columns'] == 2 and folded['anchor'] == original['anchor'], (original, folded)
        await web.evaluate_javascript('reader.setGeometry(null); reader.seekPage(2*qaColumns())')
        assert await js("""
          const touch=(type,x,property)=>{const e=new Event(type,{bubbles:true,cancelable:true});
            Object.defineProperty(e,property,{value:[{clientX:x,clientY:100}]});document.body.dispatchEvent(e);};
          touch('touchstart',240,'touches');touch('touchcancel',0,'changedTouches');touch('touchend',120,'changedTouches');
          if(qaIndex()!==2*qaColumns())return false;
          touch('touchstart',240,'touches');touch('touchend',120,'changedTouches');
          if(qaIndex()!==3*qaColumns())return false;
          qaKey('PageUp');qaKey('PageUp',document.body,{repeat:true});
          return qaIndex()===2*qaColumns();
        """), 'touch cancel, single turn, reader keyboard repeat'

        return await js("return qaIndex();")

    async def check_native_web_scroll(self, web, before):
        from android.os import SystemClock

        await web.evaluate_javascript("""window.qaRawWheel=[];
            document.addEventListener('wheel', e => qaRawWheel.push(
                [e.deltaX,e.deltaY,e.deltaMode,e.isTrusted,e.timeStamp]), {capture:true,passive:true});""")
        results = {}
        for axis in ('vertical', 'horizontal'):
            await asyncio.sleep(.35)
            # Fix the native sample times so slowdown in the emulator cannot
            # turn a single burst into several disjoint wheel sequences.
            start = SystemClock.uptimeMillis() - 120
            delivered = [self.mouse_scroll(web, timestamp=start + 10 * i, **{axis: -5.})
                         for i in range(12)]
            await asyncio.sleep(.45)
            state = json.loads(await web.evaluate_javascript('JSON.stringify(reader.pagination())'))
            wheel = json.loads(await web.evaluate_javascript('JSON.stringify(qaRawWheel.splice(0))'))
            assert any(event[3] for event in wheel), (axis, delivered, wheel)
            assert state['index'] == before + state['columns'], (axis, before, state, wheel)
            results[axis] = dict(before=before, after=state['index'], wheel=wheel)
            before = state['index']

        await web.evaluate_javascript("""
            window.qaNested = document.body.appendChild(document.createElement('div'));
            Object.assign(qaNested.style,{position:'fixed',left:'0',top:'0',zIndex:10,
                width:'180px',height:'150px',overflow:'auto'});
            const content=qaNested.appendChild(document.createElement('div'));
            Object.assign(content.style,{width:'380px',height:'380px'});
            true;
        """)
        await asyncio.sleep(.35)
        self.mouse_scroll(web, vertical=-2.)
        await asyncio.sleep(.35)
        self.mouse_scroll(web, horizontal=-2.)
        await asyncio.sleep(.4)
        nested = json.loads(await web.evaluate_javascript(
            'JSON.stringify({x:qaNested.scrollLeft,y:qaNested.scrollTop,index:reader.pagination().index})'))
        assert nested['x'] > 0 and nested['y'] > 0 and nested['index'] == before, nested
        results['nested'] = nested
        return results

    async def check_editors(self):
        multi = toga.MultilineTextInput()
        loaded = asyncio.Event()
        web = toga.WebView(on_webview_load=lambda widget: loaded.set(), style=Pack(flex=1))
        self.main_window.content = toga.Box(children=[multi, web], style=Pack(flex=1))
        set_inline_html(web, 'https://logistics.invalid/hardware-input/', '<textarea></textarea>')
        await asyncio.wait_for(loaded.wait(), timeout=20)
        await self.check_text(multi, self.shortcut, False)
        await self.check_web(web, False)
        release = self.protection.register(object(), lambda: (), protected=lambda: True)
        try:
            await self.check_text(multi, self.shortcut, True)
            await self.check_web(web, True)
        finally:
            release()

    async def exercise(self):
        report = dict(success=False, cases=[], errors={}, input={
            'ios': 'UIKit responder actions and WebKit DOM events',
            'android': 'Android KeyEvent, mouse-source ListView and WebView MotionEvent, and DOM events',
        })
        try:
            await wait_until(lambda: getattr(self, 'screen_privacy', None) is not None,
                             timeout=45, message='Hardware input workspace did not start')
            self.policy = controller(self)
            self.policy.preferences.save(**{KEY: 'true'})
            self.policy.publish()
            navigation = self.main_window.content

            async def case(name, run):
                try:
                    await run()
                except Exception:
                    report['errors'][name] = traceback.format_exc()
                else:
                    report['cases'].append(name)
                finally:
                    if self.main_window.content is not navigation:
                        self.main_window.content = navigation

            async def reading():
                reader = toga.WebView(style=Pack(flex=1))
                self.main_window.content = toga.Box(children=[reader], style=Pack(flex=1))
                index = await self.check_reader(reader)
                report['cases'].append('EPUB wheel bursts on both axes, nested ownership, fold reflow, focus and touch')
                if self.policy.android:
                    report['android_wheel'] = await self.check_native_web_scroll(reader, index)

            await case('file selection and move with restricted clipboard, native listing focus', self.check_file_move)
            if self.policy.android and not report['errors']:
                report['cases'].append('mouse-source vertical scrolling in the native file list')
            await case('ordinary and restricted clipboard in focused multiline and WebView editors', self.check_editors)
            await case('reader input' if not self.policy.android else 'mouse-source page turns through Android WebView', reading)
            report['success'] = not report['errors']
            if report['errors']:
                report['error'] = '\n'.join(report['errors'].values())
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            (Path(self.paths.cache) / RESULT).write_text(json.dumps(report, indent=2))


def main():
    return HardwareInputProbe()
