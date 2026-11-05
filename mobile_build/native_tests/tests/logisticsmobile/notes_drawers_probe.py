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
from .notes_interactions import NotesInteractionChecks

TEST_STAGE = TestStage.REGRESSION


class NotesDrawersProbe(NotesInteractionChecks, LogisticsMobile):
    async def check_file_holds(self, owner, report):
        from unittest.mock import patch
        output = Path(self.paths.cache)
        async def touch(payload):
            (output / 'notes-touch-request.json').write_text(json.dumps(payload))
            for _ in range(200):
                done = output / 'notes-touch-done'
                if done.exists():
                    done.unlink()
                    await asyncio.sleep(.3)
                    return
                await asyncio.sleep(.1)
            raise AssertionError('Native hold driver did not reply')
        owner.sidebar.show_sidebar()
        await asyncio.sleep(.4)
        original = owner.view.window.dialog
        dialogs = []
        async def show(dialog):
            dialogs.append(dialog)
            return await original(dialog)
        with patch.object(owner.view.window, 'dialog', new=show):
            for path in ('Home.md', 'Long folder name for compact row preview'):
                button = next(button for row in owner.rows.children for button in row.children
                              if getattr(button, 'vault_path', None) == path)
                native = button._impl.native
                frame = native.convertRect(native.bounds, toView=self.main_window._impl.native)
                before = len(dialogs)
                await touch(dict(action='long-press', points=[float(frame.origin.x + frame.size.width / 2),
                                                            float(frame.origin.y + frame.size.height / 2)]))
                assert len(dialogs) == before + 1, ('Hold did not open options', path)
                assert [value for _, value, _ in dialogs[-1].choices] == ['rename', 'move', 'copy', 'delete', 'cancel']
                assert owner.file_drag.source is None
                assert owner.sidebar.overlay is None and not owner.sidebar.retiring
                await capture_window(self, output / 'notes-file-hold.png')
                await touch(dict(action='capture-menu'))
                from rubicon.objc import SEL
                from commonUtils.ui.native.keyboard import native_value
                def find_cancel(view):
                    if view.respondsToSelector(SEL('text')) and str(native_value(view.text)) == 'Cancel':
                        return view
                    for child in native_value(view.subviews):
                        found = find_cancel(child)
                        if found is not None:
                            return found
                    return None
                cancel = find_cancel(native_value(dialogs[-1].native.view))
                assert cancel is not None, 'Cancel label missing from native options'
                frame = cancel.convertRect(cancel.bounds, toView=self.main_window._impl.native)
                await touch(dict(action='tap', points=[float(frame.origin.x + frame.size.width / 2),
                                                      float(frame.origin.y + frame.size.height / 2)]))
                assert owner.sidebar.side == 'files'
        await capture_window(self, output / 'notes-compact-files.png')
        owner.sidebar.show_detail()
        await asyncio.sleep(.3)
        report['native_file_and_folder_holds'] = True

    async def check_note_actions(self, owner, report):
        assert await owner.open_note('Other.md')
        await asyncio.sleep(.3)
        assert owner.secondary.parent is not None
        assert owner.secondary.style.display != NONE
        assert owner.breadcrumb_scroll.parent is owner.secondary
        async def invoke(button, complete):
            assert button.enabled
            button._impl.native.sendActionsForControlEvents(1 << 6)
            for _ in range(100):
                if complete():
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError(('Native action did not complete', button.accessible_name,
                                      owner.notice.text, getattr(owner.embedded, 'dirty', None)))
            await asyncio.sleep(.2)
        await invoke(owner.back_button, lambda: owner.path == 'Home.md')
        assert owner.forward_button.enabled
        await invoke(owner.forward_button, lambda: owner.path == 'Other.md')
        await invoke(owner.edit, lambda: owner.editing)
        formatted = owner.embedded.formatted
        for _ in range(100):
            if await formatted.view.evaluate_javascript(
                    'document.documentElement.dataset.editorBridge===' + json.dumps(formatted.bridge)
                    + ' && typeof window.markdownSnapshot==="function"'):
                break
            await asyncio.sleep(.05)
        else:
            raise AssertionError('Formatted editor did not finish loading')
        await invoke(owner.edit, lambda: not owner.editing)
        actions = owner.reader_actions_button._impl.native
        assert actions.menu is not None and actions.showsMenuAsPrimaryAction
        assert any(label == 'Contents…' for label, _ in owner.reader_actions.actions)
        assert await owner.open_note('Home.md')
        await asyncio.sleep(.3)
        # Check that title content cannot swallow taps on the folder row.
        from rubicon.objc import CGPoint
        from commonUtils.ui.native.keyboard import native_value
        button = owner.breadcrumbs.children[-1]._impl.native
        window = self.main_window._impl.native
        frame = button.convertRect(button.bounds, toView=window)
        viewport = owner.breadcrumb_scroll._impl.native
        clip = viewport.convertRect(viewport.bounds, toView=window)
        left, top = max(frame.origin.x, clip.origin.x), max(frame.origin.y, clip.origin.y)
        right = min(frame.origin.x + frame.size.width, clip.origin.x + clip.size.width)
        bottom = min(frame.origin.y + frame.size.height, clip.origin.y + clip.size.height)
        assert right > left and bottom > top, 'Folder breadcrumb has no visible touch area'
        # A narrow phone intentionally scrolls/clips breadcrumbs. Test the
        # visible intersection, rather than an offscreen content-button center.
        point = CGPoint((left + right) / 2, (top + bottom) / 2)
        hit = window.hitTest(point, withEvent=None)
        while hit is not None and hit != button:
            hit = native_value(hit.superview)
        assert hit == button, 'Folder breadcrumb is covered by another native view'
        report['native_note_actions'] = True

    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-drawers-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def real_swipe(self, owner, direction, *, strip=None):
        output = Path(self.paths.cache)
        native = (strip if strip is not None else owner.article)._impl.native
        frame = native.convertRect(native.bounds, toView=self.main_window._impl.native)
        y = float(frame.origin.y + frame.size.height * (.5 if strip is not None else .75))
        center = float(frame.origin.x + frame.size.width / 2)
        half_span = min(65, float(frame.size.width) * .4)
        (output / 'notes-touch-request.json').write_text(json.dumps(
            dict(points=[center - direction * half_span, y, center + direction * half_span, y])))
        for _ in range(200):
            done = output / 'notes-touch-done'
            if done.exists():
                done.unlink()
                await asyncio.sleep(.3)
                return
            await asyncio.sleep(.1)
        raise AssertionError('Native swipe driver did not reply')

    async def probe(self):
        output = Path(self.paths.cache)
        report = dict(success=False, samples=[])
        owner = None
        try:
            # on_running may fire while Android still presents its startup
            # cover. Never change routes until the app publishes readiness.
            deadline = self.loop.time() + 120
            while getattr(self, '_startup_in_progress', False) and self.loop.time() < deadline:
                await asyncio.sleep(.1)
            if getattr(self, '_startup_in_progress', False):
                if not self.apple_probe:
                    native, content = self.navigation._impl.native, self.navigation._impl.native_content
                    report['startup_geometry'] = dict(root=[native.getWidth(), native.getHeight()],
                        content=[content.getWidth(), content.getHeight()],
                        layout_requested=[native.isLayoutRequested(), content.isLayoutRequested()])
                raise AssertionError('Application startup did not finish before native interactions')
            report['startup_ready'] = True
            for name in ('cloud_startup_task', 'cloud_restore_task'):
                pending = getattr(self, name, None)
                if pending is not None:
                    await asyncio.shield(pending)
            self.show_documents_hub()
            self.document_view_buttons['Libraries'].on_press()
            while True:
                discovery = self._notes_discovery_task
                await discovery
                if discovery is self._notes_discovery_task:
                    break
            await asyncio.sleep(.5)
            status = self.document_notes_list.children[2]
            notice = getattr(status, '_settings_source_text', status.text)
            assert 'Looking for libraries' not in notice, notice
            if notice:
                assert status._settings_rendered_text
            report['library_discovery_notice'] = notice
            await capture_window(self, output / 'notes-discovery.png')
            root = output / 'Art'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Home.md').write_text('# Character Art Team\n\nProducer: Diane Guillemont\n\nLead Character Artist: Chad Emond\n\n## Pages\n\n[[Other]]\n\n## Naming conventions\n\nKeep shared files organized by project.\n')
            (root / 'Other.md').write_text('# Other\n\n[[Home]]\n')
            (root / 'Long folder name for compact row preview').mkdir(exist_ok=True)
            (root / 'Long folder name for compact row preview/Child.md').write_text('Child bytes')
            (root / 'Long document name to preview inside the sidebar.md').write_text('# Preview')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            await asyncio.sleep(1)
            await capture_window(self, output / 'notes-landing.png')
            if not self.apple_probe or (output / 'drive-notes-touches').exists():
                await self.check_empty_swipes(owner, report)
            if type(self._impl).__module__.startswith('toga_iOS.'):
                header = owner.view._document_title_header
                assert list(header.children) == [owner.menu, header._title_content, owner.links_button]
                assert float(header._title_content._impl.native.bounds.size.width) > 0
                # Toga flattens Box children into its native layout container;
                # measure screen positions rather than native parentage.
                def screen_frame(native):
                    return native.convertRect(native.bounds, toView=None)
                left = screen_frame(owner.menu._impl.native)
                title = screen_frame(owner.view._document_title_view)
                right = screen_frame(owner.links_button._impl.native)
                assert float(left.origin.x + left.size.width) <= float(title.origin.x) + 1
                assert float(title.origin.x + title.size.width) <= float(right.origin.x) + 1
                if (output / 'drive-notes-touches').exists():
                    directions = ((-1, 'links'),) if owner.sidebar.expanded else ((1, 'files'), (-1, 'links'))
                    for direction, side in directions:
                        await self.real_swipe(owner, direction)
                        assert owner.sidebar.side == side, ('landing swipe', direction, owner.sidebar.side)
                        await self.real_swipe(owner, -direction)
                        assert owner.sidebar.side is None
                    assert await owner.open_note('Home.md')
                    await asyncio.sleep(.5)
                    for direction, side in directions:
                        await self.real_swipe(owner, direction)
                        assert owner.sidebar.side == side, ('article swipe', direction, owner.sidebar.side)
                        owner.sidebar.show_detail()
                        assert owner.sidebar.retiring
                        overlay = owner.sidebar.retiring[0][0]
                        assert overlay.container is not None
                        await asyncio.sleep(.3)
                        assert not owner.sidebar.retiring
                        assert overlay.container is None
                    report['native_touch_swipes'] = True
                    await self.check_file_holds(owner, report)
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.5)
                if owner.sidebar.expanded:
                    assert owner.open_card.style.display == NONE
                    assert getattr(owner, '_document_return_side', None) is None
                owner.sidebar.show_sidebar()
                assert await owner.open_note('Home.md')
                if type(self._impl).__module__.startswith('toga_iOS.'):
                    await self.check_note_actions(owner, report)
                    await capture_window(self, output / ('notes-reading-' + orientation + '.png'))
                if owner.sidebar.expanded:
                    assert owner.back_action() == (owner.previous_note if owner.history_index > 0 else None)
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
            if not self.apple_probe or (output / 'drive-notes-touches').exists():
                await self.check_library_copies(owner, report, 'local')
                owner.dispose()
                owner = None
                await self.check_private_copies(report)
                await self.check_workspace_copies(report)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
        (output / 'notes-drawers-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesDrawersProbe('Notes drawers QA', 'io.github.ispaure.logisticsnotebookqa')
