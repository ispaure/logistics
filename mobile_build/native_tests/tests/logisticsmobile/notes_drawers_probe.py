"""Focused document swipes and adaptive Notes Library panels on native hosts."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from toga.style.pack import NONE

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import start_native_check
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class NotesDrawersProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-drawers-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        output = Path(self.paths.cache)
        report = dict(success=False, samples=[])
        owner = None
        try:
            root = output / 'drawer-fixture'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Home.md').write_text('# Home\n\nRead here. [[Other]]\n')
            (root / 'Other.md').write_text('# Other\n\n[[Home]]\n')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.5)
                if owner.sidebar.expanded:
                    assert owner.open_card.style.display == NONE
                    assert getattr(owner, '_document_return_side', None) is None
                owner.sidebar.show_sidebar()
                assert await owner.open_note('Home.md')
                if owner.sidebar.expanded:
                    assert owner.back_action() is None
                for _ in range(100):
                    if await owner.web.evaluate_javascript(
                            'window.notesDrawersBase===' + json.dumps(owner.base) +
                            ' && document.readyState==="complete"'):
                        break
                    await asyncio.sleep(.05)
                else:
                    raise AssertionError('Document swipe handlers did not load')
                expected_children = [owner.tree, owner.article] if owner.sidebar.expanded else [owner.article]
                assert list(owner.sidebar.view.children) == expected_children

                async def swipe_document(dx, *, vertical=False, media=''):
                    await owner.web.evaluate_javascript('''(function(){
                      const target=MEDIA?document.createElement(MEDIA):document.body;
                      if(MEDIA)document.body.appendChild(target);
                      function event(type,x,y=160){const e=new Event(type,{bubbles:true});
                        Object.defineProperty(e,'touches',{value:type==='touchend'?[]:[{clientX:x,clientY:y}]});
                        Object.defineProperty(e,'changedTouches',{value:[{clientX:x,clientY:y}]});
                        target.dispatchEvent(e);}
                      event('touchstart',innerWidth/2);
                      if(VERTICAL)event('touchmove',innerWidth/2+5,240);
                      event('touchend',innerWidth/2+DX);
                      if(MEDIA)target.remove();
                    })();'''.replace('DX', str(dx)).replace('VERTICAL', json.dumps(vertical)).replace('MEDIA', json.dumps(media)))

                async def wait_side(side):
                    for _ in range(100):
                        if owner.sidebar.side == side:
                            return
                        await asyncio.sleep(.05)
                    raise AssertionError((side, owner.sidebar.side))

                def dismiss(direction):
                    if type(self._impl).__module__.startswith('toga_iOS.'):
                        _, gesture, target = owner.sidebar.gestures[0]
                        assert int(gesture.direction) == (1 if direction > 0 else 2)
                        assert gesture.delegate is not None
                        owner.sidebar.refresh_gestures()
                        target.swipe_(gesture)
                    else:
                        from android.view import MotionEvent
                        from android.os import SystemClock
                        native = owner.sidebar.overlay.popup.getContentView().getRootView()
                        density = native.getContext().getResources().getDisplayMetrics().density
                        time = SystemClock.uptimeMillis()
                        x = 80 if direction > 0 else 220
                        overlay = owner.sidebar.overlay
                        for vertical in (True, False):
                            moves = [(0, 0, 0, 0)]
                            if vertical:
                                moves.append((2, 5, 80, 50))
                            moves.append((1, 140 * direction, 0, 100))
                            for action, offset, dy, elapsed in moves:
                                event = MotionEvent.obtain(time, time + elapsed, action,
                                    (x + offset) * density, (180 + dy) * density, 0)
                                try:
                                    native.dispatchTouchEvent(event)
                                    if action == 0:
                                        owner.sidebar.refresh_gestures()
                                finally:
                                    event.recycle()
                            if vertical:
                                assert owner.sidebar.overlay is overlay
                    assert owner.sidebar.overlay is None
                    assert not owner.sidebar.gestures

                for options in ({'vertical': True}, {'media': 'video'}, {'media': 'audio'}):
                    await swipe_document(-95, **options)
                    await asyncio.sleep(.2)
                    assert owner.sidebar.side is None
                await swipe_document(-95)
                await wait_side('links')
                await asyncio.sleep(.3)
                if (type(self._impl).__module__.startswith('toga_android.')
                        and orientation == 'portrait'):
                    from android.view import MotionEvent
                    from android.os import SystemClock
                    from java import jarray, jint
                    for _ in range(100):
                        buttons = [row for row in owner.link_rows.children
                                   if getattr(row, 'text', '') == 'Other.md']
                        if buttons:
                            break
                        await asyncio.sleep(.02)
                    assert buttons, 'Connections did not load'
                    button = buttons[0]._impl.native
                    native = owner.sidebar.overlay.popup.getContentView().getRootView()
                    point, origin = jarray(jint)(2), jarray(jint)(2)
                    button.getLocationOnScreen(point)
                    native.getLocationOnScreen(origin)
                    x, y = point[0] - origin[0], point[1] - origin[1]
                    y += button.getHeight() / 2
                    assert 0 <= y < native.getHeight(), (y, native.getHeight())
                    time = SystemClock.uptimeMillis()
                    for action, fraction, elapsed in ((0, .8, 0), (2, .5, 50), (1, .2, 100)):
                        event = MotionEvent.obtain(time, time + elapsed, action,
                            x + button.getWidth() * fraction, y, 0)
                        try:
                            native.dispatchTouchEvent(event)
                        finally:
                            event.recycle()
                    await asyncio.sleep(.3)
                    assert owner.path == 'Home.md', 'A non-closing swipe activated a note link'
                    assert owner.sidebar.side == 'links'
                    assert not button.isPressed(), 'Swipe left a link button pressed'
                await capture_window(self, output / ('notes-links-' + orientation + '.png'))
                dismiss(1)
                await swipe_document(95)
                if owner.sidebar.expanded:
                    await asyncio.sleep(.2)
                    assert owner.sidebar.overlay is None
                    assert owner.tree.parent is owner.sidebar.view
                else:
                    await wait_side('files')
                await asyncio.sleep(.3)
                await capture_window(self, output / ('notes-files-' + orientation + '.png'))
                if not owner.sidebar.expanded:
                    dismiss(-1)
                assert owner.path == 'Home.md'
                report['samples'].append(dict(orientation=orientation, expanded=owner.sidebar.expanded))
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
        (output / 'notes-drawers-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesDrawersProbe('Notes drawers QA', 'io.github.ispaure.logisticsnotebookqa')
