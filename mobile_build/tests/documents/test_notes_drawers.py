"""Mobile drawer navigation and local connection indexing contracts."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
from commonUtils.testing.stages import TestStage
from commonUtils.runtime.operations import OperationCancelled
from features.notes_library.notes import NotesLibrary, vault_root
from features.notes_library.notes_links import connections
from mobile.obsidian import open_vault
import mobile_build.tests.documents.test_obsidian as fixtures

TEST_STAGE = TestStage.REGRESSION
NODE = os.environ.get('LOGISTICS_NODE') or shutil.which('node')


class NotesDrawerTests(unittest.TestCase):
    setUp = fixtures.ObsidianTests.setUp
    tearDown = fixtures.ObsidianTests.tearDown
    run_async = fixtures.ObsidianTests.run_async

    def test_links_resolve_aliases_references_and_ignore_code_images_and_hidden_notes(self):
        (self.vault / 'Home.md').write_text('[[Projects/Plan.MD|Plan]] [Plan][p]\n\n[p]: Projects/Plan.MD\n'
            '\n`[[Ignored]]`\n\n```\n[[Ignored]]\n```\n\n![[Missing.png]] [[Missing]]')
        (self.vault / 'Projects/Plan.MD').write_text('[[Home]] [Root](../Home.md#heading)')
        result = connections(NotesLibrary(self.provider, 'Vault'), 'Vault/Home.md')
        self.assertEqual(result['incoming'], ['Vault/Projects/Plan.MD'])
        self.assertEqual(result['outgoing'], ['Vault/Projects/Plan.MD'])
        self.assertEqual(result['unresolved'], ['Missing'])
        self.assertGreater(result['words'], 0)
        with self.assertRaises(OperationCancelled):
            connections(NotesLibrary(self.provider, 'Vault'), 'Vault/Home.md', cancelled=lambda: True)

    def test_remote_wrappers_are_rejected_before_any_io(self):
        remote = SimpleNamespace(provider=self.provider, remote_storage=True)
        wrapped = SimpleNamespace(provider=remote)
        self.assertIsNone(vault_root(wrapped, 'Vault', self.provider.list('Vault')))
        with self.assertRaisesRegex(ValueError, 'local copy'):
            NotesLibrary(wrapped, 'Vault')
        self.assertIsNone(self.run_async(open_vault(self.app, wrapped, 'Vault')))

    def test_files_document_links_sequence_and_history_on_phone_and_tablet(self):
        async def exercise():
            for width in (320, 390, 900, 1366):
                owner = await open_vault(self.app, self.provider, 'Vault', 'files')
                owner.reflow(width)
                self.assertIsNone(owner.sidebar.side)
                owner.open_card.on_press()
                wide = width >= 864  # Library reserves a 24-unit inset.
                self.assertEqual(owner.sidebar.expanded, wide)
                self.assertEqual(owner.sidebar.side, None if wide else 'files')
                self.assertEqual(list(owner.sidebar.view.children),
                                 [owner.tree, owner.article] if wide else [owner.article])
                if not wide:
                    self.assertTrue(self.app.routes.system_back())
                self.assertIsNone(owner.sidebar.side)
                self.assertTrue(owner.valid())
                await owner.open_note('Vault/Projects/Plan.MD')
                await owner.show_links()
                self.assertEqual(owner.sidebar.side, 'links')
                self.assertIn('Backlinks (1)', [getattr(w, 'text', '') for w in owner.link_rows.children])
                self.assertIs(owner.back_action().__self__, owner.sidebar)
                self.assertTrue(self.app.routes.system_back())
                self.assertIsNone(owner.sidebar.side)
                owner.follow_link(owner.web, owner.base + '?drawer=files')
                self.assertEqual(owner.sidebar.side, None if wide else 'files')
                owner.dispose()
                self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())

    def test_swipes_dismiss_only_the_opposite_drawer_and_resize_preserves_document(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.reflow(390)
            await owner.open_note('Vault/Home.md')
            for side, closing in (('files', -1), ('links', 1)):
                owner.sidebar.show(side)
                self.assertFalse(owner.sidebar.swipe(-closing))
                self.assertEqual(owner.sidebar.side, side)
                self.assertTrue(owner.sidebar.swipe(closing))
                self.assertIsNone(owner.sidebar.side)
                self.assertIsNone(owner.sidebar.overlay)
            owner.sidebar.show_sidebar()
            owner.select_panel_tab('Calendar')
            await owner.calendar_task
            owner.reflow(863)
            self.assertFalse(owner.sidebar.expanded)
            owner.reflow(864)
            self.assertTrue(owner.sidebar.expanded)
            self.assertIsNone(owner.sidebar.overlay)
            self.assertEqual(owner.sidebar.view.children, [owner.tree, owner.article])
            owner.reflow(864)
            self.assertEqual(owner.sidebar.view.children, [owner.tree, owner.article])
            self.assertEqual(owner.panel_body.children, [owner.calendar_scroll])
            await owner.show_links()
            owner.reflow(390)
            self.assertEqual(owner.sidebar.side, 'links')
            self.assertEqual(owner.sidebar.view.children, [owner.article])
            self.assertEqual(owner.panel_body.children, [owner.calendar_scroll])
            owner.sidebar.swipe(1)
            self.assertIsNone(owner.sidebar.side)
            self.assertEqual(owner.path, 'Vault/Home.md')
            self.assertIs(owner.web.parent, owner.article)
            owner.dispose()
        self.run_async(exercise())

    def test_wide_files_does_not_offer_noop_open_or_back_actions(self):
        from toga.style.pack import NONE, PACK
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.reflow(900)
            with self.subTest('welcome action with pinned Files'):
                self.assertEqual(owner.open_card.style.display, NONE)
                self.assertFalse(owner.menu.enabled)
            owner.reflow(390)
            self.assertEqual(owner.open_card.style.display, PACK)
            self.assertTrue(owner.menu.enabled)
            owner.sidebar.show_sidebar()
            await owner.open_note('Vault/Home.md')
            self.assertEqual(owner.back_action(), owner.return_to_browsing)
            owner.reflow(900)
            self.assertEqual(owner.open_card.style.display, NONE)
            self.assertIsNone(owner.back_action())
            self.assertIsNone(owner._document_return_side)
            owner.reflow(390)
            self.assertIsNone(owner.back_action())
            owner.sidebar.show_sidebar()
            await owner.open_note('Vault/Projects/Plan.MD')
            owner.reflow(900)
            self.assertEqual(owner.back_action(), owner.previous_note)
            await owner.back_action()()
            self.assertEqual(owner.path, 'Vault/Home.md')
            owner.dispose()
        self.run_async(exercise())

    def test_widening_during_a_note_read_does_not_restore_a_stale_files_return(self):
        from dataclasses import replace
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.reflow(390)
            owner.sidebar.show_sidebar()
            entered, release = Event(), Event()
            load = owner.library.load_note
            def delayed(*args, **kwargs):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('Test did not release note read')
                return load(*args, **kwargs)
            with patch.object(owner, 'host', replace(owner.host, render=lambda: None)), \
                    patch.object(owner.library, 'load_note', side_effect=delayed):
                task = asyncio.create_task(owner.open_note('Vault/Home.md'))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 2))
                    owner.reflow(900)
                finally:
                    release.set()
                    opened = await task
            self.assertTrue(opened)
            self.assertTrue(owner.sidebar.expanded)
            self.assertIsNone(owner._document_return_side)
            self.assertIsNone(owner.back_action())
            owner.dispose()
        self.run_async(exercise())

    def test_returning_to_links_refreshes_connections_for_the_current_document(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            owner.reflow(390)
            await owner.open_note('Vault/Home.md')
            await owner.show_links()
            self.assertEqual(owner.link_rows.children[0].text, 'Home.md')
            await owner.open_note('Vault/Projects/Plan.MD')
            owner.reflow(900)
            self.assertEqual(owner.back_action(), owner.return_to_browsing)
            owner.back_action()()
            if owner.links_refresh_task is not None:
                await owner.links_refresh_task
            self.assertEqual(owner.sidebar.side, 'links')
            self.assertEqual(owner.link_rows.children[0].text, 'Plan.MD')
            self.assertEqual(owner.back_action(), owner.sidebar.show_detail)
            owner.dispose()
        self.run_async(exercise())

    def test_android_popup_observes_child_touches_and_releases_its_listener(self):
        from mobile.notes_drawers import NotesDrawers
        owner = NotesDrawers.__new__(NotesDrawers)
        owner.gestures = []
        owner.swipe = Mock(return_value=True)
        popup = Mock()
        owner.overlay = SimpleNamespace(popup=popup)
        panel = SimpleNamespace(_impl=type('AndroidBox', (), {'__module__':'toga_android.widgets.box'})())
        with patch.dict(sys.modules, {
            'android.view': SimpleNamespace(View=SimpleNamespace(OnTouchListener=object)),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }):
            owner.install_swipe(panel)
        listener = popup.setTouchInterceptor.call_args.args[0]
        view = Mock()
        view.getContext().getResources().getDisplayMetrics.return_value.density = 2
        def touch(action, x, y=0, time=0):
            event = Mock()
            event.getActionMasked.return_value = action
            event.getRawX.return_value, event.getRawY.return_value = x, y
            event.getEventTime.return_value = time
            return listener.onTouch(view, event)
        for distance, direction in ((150, 1), (-150, -1)):
            self.assertFalse(touch(0, 0))
            self.assertTrue(touch(1, distance, time=100))
            owner.swipe.assert_called_with(direction)
        owner.swipe.reset_mock()
        for action, x, y, time in ((1, 150, 100, 100), (1, 100, 0, 100), (1, 150, 0, 900)):
            touch(0, 0)
            self.assertFalse(touch(action, x, y, time))
        for cancellation in (3, 5):
            touch(0, 0)
            touch(cancellation, 0)
            self.assertFalse(touch(1, 150, time=100))
        touch(0, 0)
        touch(2, 5, 80, 50)
        self.assertFalse(touch(1, 150, time=100))
        owner.swipe.assert_not_called()
        owner.clear_gestures()
        popup.setTouchInterceptor.assert_called_with(None)
        self.assertEqual(owner.gestures, [])

    def test_android_wrong_direction_preserves_child_touch_and_refresh_preserves_swipe(self):
        from mobile.notes_drawers import NotesDrawers
        owner = NotesDrawers.__new__(NotesDrawers)
        owner.side, owner.gestures = 'files', []
        owner.show_detail = Mock()
        popup = Mock()
        owner.overlay = SimpleNamespace(popup=popup)
        panel = SimpleNamespace(_impl=type('AndroidBox', (), {'__module__':'toga_android.widgets.box'})())
        owner.sidebar = panel
        view = Mock()
        view.getContext().getResources().getDisplayMetrics.return_value.density = 1
        def touch(action, x, time=0):
            event = Mock()
            event.getActionMasked.return_value = action
            event.getRawX.return_value, event.getRawY.return_value = x, 0
            event.getEventTime.return_value = time
            listener = popup.setTouchInterceptor.call_args.args[0]
            return listener.onTouch(view, event)
        with patch.dict(sys.modules, {
            'android.view': SimpleNamespace(View=SimpleNamespace(OnTouchListener=object)),
            'java': SimpleNamespace(dynamic_proxy=lambda interface: object),
        }):
            owner.install_swipe(panel)
            # A swipe toward the already-open Files drawer must still reach
            # its child control, including the final up event.
            touch(0, 100)
            self.assertFalse(touch(1, 200, 100))
            owner.show_detail.assert_not_called()
            # Tree/link rendering can finish between down and up. A parent
            # recognizer does not need replacing when its children change.
            touch(0, 200)
            owner.refresh_gestures()
            self.assertTrue(touch(1, 100, 100))
            owner.show_detail.assert_called_once()
            self.assertEqual(popup.setTouchInterceptor.call_count, 1)
        owner.clear_gestures()

    @unittest.skipUnless(NODE, 'Node required for document touch events')
    def test_document_touch_events_open_from_center_and_preserve_reading_gestures(self):
        from features.notes_library.mobile.notes_swipe import document_swipes
        script = r'''
const assert = require('node:assert/strict');
const events = {};
let registrations = 0;
global.window = {visualViewport: {scale: 1}};
global.document = {body: {}, addEventListener: (name, handler) => {events[name] = handler; registrations++;}};
global.location = {href: ''};
let selection = '';
global.getSelection = () => selection;
let now = 0;
Date.now = () => now;
eval(SCRIPT);
const point = (x, y=100) => ({clientX:x, clientY:y});
const normal = {parentElement: document.body, scrollWidth: 200, clientWidth: 200};
function swipe(dx, {dy=0, target=normal, duration=100, during=()=>{}}={}) {
  location.href = '';
  now = 0;
  events.touchstart({touches:[point(180)], target});
  during();
  now = duration;
  events.touchend({touches:[], changedTouches:[point(180+dx,100+dy)]});
  return location.href;
}
assert.equal(swipe(90), '/note?drawer=files');
assert.equal(swipe(-90), '/note?drawer=links');
assert.equal(swipe(40), '');
assert.equal(swipe(90, {dy:60}), '');
assert.equal(swipe(90, {duration:900}), '');
assert.equal(swipe(90, {target:{...normal, scrollWidth:400}}), '');
assert.equal(swipe(90, {target:{...normal, isContentEditable:true}}), '');
assert.equal(swipe(90, {target:{...normal, tagName:'INPUT'}}), '');
assert.equal(swipe(90, {target:{...normal, tagName:'VIDEO'}}), '');
assert.equal(swipe(90, {target:{...normal, tagName:'AUDIO'}}), '');
assert.equal(swipe(90, {during:()=>events.touchmove({touches:[point(185,180)]})}), '');
assert.equal(swipe(90, {during:()=>events.touchmove({touches:[point(245,105)]})}), '/note?drawer=files');
selection = 'selected';
assert.equal(swipe(90), '');
selection = '';
assert.equal(swipe(90, {during:()=>{selection='selected';}}), '');
selection = '';
window.visualViewport.scale = 2;
assert.equal(swipe(90), '');
window.visualViewport.scale = 1;
assert.equal(swipe(90, {during:()=>events.touchstart({touches:[point(1),point(2)],target:normal})}), '');
assert.equal(swipe(90, {during:()=>events.touchmove({touches:[point(1),point(2)]})}), '');
assert.equal(swipe(90, {during:()=>events.touchcancel()}), '');
const installedCount = registrations;
eval(REINSTALL);
assert.equal(registrations, installedCount);
assert.equal(swipe(90), '/next?drawer=files');
assert.equal(swipe(-90), '/next?drawer=links');
'''.replace('SCRIPT', json.dumps(document_swipes('/note'))).replace(
            'REINSTALL', json.dumps(document_swipes('/next')))
        result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_closed_library_cannot_publish_delayed_connections(self):
        async def exercise():
            owner = await open_vault(self.app, self.provider, 'Vault', 'files')
            await owner.open_note('Vault/Home.md')
            entered, release = Event(), Event()
            def delayed(*args, **kwargs):
                entered.set()
                release.wait(5)
                return dict(incoming=['private.md'], outgoing=[], unresolved=[], words=1, characters=1)
            with patch('features.notes_library.notes_links.connections', side_effect=delayed):
                task = asyncio.create_task(owner.show_links())
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.01)
                    self.assertTrue(entered.is_set())
                    owner.dispose()
                finally:
                    release.set()
                    await task
                self.assertEqual(list(owner.link_rows.children), [])
                self.assertIsNone(owner.sidebar.overlay)
        self.run_async(exercise())
