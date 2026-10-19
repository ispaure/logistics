"""Isolated long-document typing and keyboard geometry checks."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from logisticsmobile.app import LogisticsMobile
from tests.logisticsmobile.fixtures import capture_window


MEASURE = """JSON.stringify((() => {
    const root = document.getElementById('document');
    const selection = getSelection();
    const range = selection.getRangeAt(0).cloneRange();
    let caret = range.getBoundingClientRect();
    if (!caret.height && range.startOffset > 0 && range.startContainer.nodeType === 3) {
        range.setStart(range.startContainer, range.startOffset - 1); caret = range.getBoundingClientRect();
    }
    const bounds = root.getBoundingClientRect(), nav = document.querySelector('nav').getBoundingClientRect();
    return {top:bounds.top, bottom:bounds.bottom, caret_top:caret.top, caret_bottom:caret.bottom,
        scroll:root.scrollTop, outer_scroll:scrollY, toolbar_top:nav.top, height:innerHeight,
        focused:root.contains(document.activeElement), viewport_top:visualViewport.offsetTop,
        compact_menu:getComputedStyle(document.querySelector('nav')).position === 'absolute',
        toolbar_height:nav.height, button_height:Array.from(document.querySelectorAll('nav button,nav summary'))
            .map(button=>button.getBoundingClientRect().height).find(height=>height>0)};
})())"""


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('isolated-editor-keyboard-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_probe_started', False):
            self._probe_started = True
            self.loop.create_task(self.probe())

    async def probe(self):
        if type(self._impl).__module__.startswith('toga_android.'):
            await self.android_probe()
            return
        output = Path(self.paths.cache) / 'editor-keyboard-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, markdown=[], source=[])
        try:
            document = self.store.create('Typing.md', '\n\n'.join(
                'Paragraph %d. A long document keeps the caret far below the beginning.' % i
                for i in range(100)).encode())
            self.refresh_documents()
            self.open_document(document.id)
            self.show_documents(edit=True)
            owner = self.editor_view
            web = owner.formatted.view
            ios = type(self._impl).__module__.startswith('toga_iOS.')
            if ios:
                controller = self.native_host.adapter.controller
                report['tabs_before_keyboard'] = bool(controller.isTabBarHidden())
                assert not report['tabs_before_keyboard']
            await asyncio.sleep(.7)
            await web.evaluate_javascript("""(() => {
                const root = document.getElementById('document');
                const target = Array.from(root.querySelectorAll('p')).filter(p => p.textContent).at(-1);
                target.closest('section').focus();
                const range = document.createRange(); range.selectNodeContents(target); range.collapse(false);
                const selection = getSelection(); selection.removeAllRanges(); selection.addRange(range);
                root.scrollTop = root.scrollHeight;
                scheduleCaretReveal();
            })()""")
            if type(self._impl).__module__.startswith('toga_iOS.'):
                # JavaScript focus alone need not show the software keyboard.
                # Activate the already-focused WebKit content's native responder.
                from logisticsmobile.keyboard import native_value
                for child in native_value(native_value(web._impl.native.scrollView).subviews):
                    if 'WKContentView' in str(type(child)) or 'WKContentView' in str(child.objc_class):
                        child.becomeFirstResponder()
            await asyncio.sleep(.8)
            if type(self._impl).__module__.startswith('toga_iOS.'):
                report['markdown_keyboard_inset'] = self.native_host.adapter.keyboard_inset
                assert report['markdown_keyboard_inset'] > 100, 'Markdown software keyboard did not open'
                assert bool(controller.isTabBarHidden()), 'Destination tabs stayed above the keyboard'
                # Measure the actual space recovered, not only a hidden flag.
                controller.setTabBarHidden(False, animated=False)
                await asyncio.sleep(.4)
                with_tabs = json.loads(await web.evaluate_javascript(MEASURE))['height']
                controller.setTabBarHidden(True, animated=False)
                await asyncio.sleep(.4)
                without_tabs = json.loads(await web.evaluate_javascript(MEASURE))['height']
                report['writing_area'] = dict(with_tabs=with_tabs, without_tabs=without_tabs,
                                              gained=without_tabs - with_tabs)
                assert without_tabs >= with_tabs + 20, report['writing_area']
            for index in range(16):
                await web.evaluate_javascript("document.execCommand('insertText', false, ' typing continues');")
                await asyncio.sleep(.08)
                sample = json.loads(await web.evaluate_javascript(MEASURE))
                report['markdown'].append(sample)
                assert sample['focused'] and abs(sample['outer_scroll']) < 1, sample
                assert sample['caret_top'] >= sample['top'] - 2, sample
                assert sample['caret_bottom'] <= sample['bottom'] + 2, sample
                assert owner.formatted.view is web and owner.formatted.text == owner.document.text
            assert max(s['toolbar_top'] for s in report['markdown']) - min(
                s['toolbar_top'] for s in report['markdown']) < 1
            if type(self._impl).__module__.startswith('toga_iOS.'):
                report['filename_width'] = float(owner.name._impl.native.bounds.size.width)
                assert report['filename_width'] >= 44, 'Filename field collapsed under the toolbar icons'
            await capture_window(self, output / 'markdown-typing.png')
            if type(self._impl).__module__.startswith('toga_iOS.'):
                self.main_window._impl.native.endEditing(True)
                await asyncio.sleep(.4)
                report['tabs_after_markdown_dismissal'] = bool(controller.isTabBarHidden())
                assert not report['tabs_after_markdown_dismissal']
                # Both plain text and Markdown Source use the same native input.
                for name in ('Typing.txt', 'Source.md'):
                    document = self.store.create(name, ('A long editable line\n' * 150).encode())
                    self.refresh_documents()
                    self.open_document(document.id)
                    self.show_documents(edit=True)
                    owner = self.editor_view
                    if name.endswith('.md'):
                        owner.edit_mode.value = 'Source'
                    native = owner.editor._impl.native
                    from rubicon.objc import NSRange
                    native.becomeFirstResponder()
                    native.selectedRange = NSRange(len(owner.document.text), 0)
                    native.scrollRangeToVisible(native.selectedRange)
                    await asyncio.sleep(.7)
                    assert bool(controller.isTabBarHidden()), (name, 'Destination tabs stayed visible')
                    for index in range(12):
                        native.insertText('Native typing\n')
                        await asyncio.sleep(.08)
                        caret = native.caretRectForPosition(native.selectedTextRange.end)
                        bounds = native.bounds
                        sample = dict(name=name, caret_top=float(caret.origin.y),
                            caret_bottom=float(caret.origin.y + caret.size.height),
                            top=float(bounds.origin.y), bottom=float(bounds.origin.y + bounds.size.height))
                        report['source'].append(sample)
                        assert sample['caret_top'] >= sample['top'] - 2, sample
                        assert sample['caret_bottom'] <= sample['bottom'] + 2, sample
                    await capture_window(self, output / (name + '.png'))
                    self.main_window._impl.native.endEditing(True)
                    await asyncio.sleep(.3)
                    assert not bool(controller.isTabBarHidden()), (name, 'Destination tabs did not restore')
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))

    async def android_probe(self):
        from android.content import Context
        from android.graphics import Rect
        from android.os import Build
        from android.view.inputmethod import EditorInfo, InputMethodManager
        from java import jarray, jint, jclass
        output = Path(self.paths.cache) / 'editor-keyboard-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, running=True, cases=[])
        (output / 'result.json').write_text(json.dumps(report))
        manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)

        def bounds(native):
            point = jarray(jint)(2)
            native.getLocationOnScreen(point)
            return [int(point[0]), int(point[1]), int(point[0] + native.getWidth()), int(point[1] + native.getHeight())]

        def sample(owner, native):
            visible = Rect()
            native.getWindowVisibleDisplayFrame(visible)
            insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(native)
            ime = jclass('androidx.core.view.WindowInsetsCompat$Type').ime()
            ime_bottom = int(insets.getInsets(ime).bottom) if insets else 0
            visible_bottom = int(visible.bottom)
            if insets and ime_bottom and Build.VERSION.SDK_INT >= 30:
                window = self._impl.native.getWindowManager().getCurrentWindowMetrics().getBounds()
                visible_bottom = min(visible_bottom, int(window.bottom) - ime_bottom)
            ancestry, parent = [], native
            while parent is not None and hasattr(parent, 'getScrollY'):
                ancestry.append(dict(kind=str(parent.getClass().getName()), scroll=int(parent.getScrollY()), bounds=bounds(parent)))
                parent = parent.getParent()
            secondary = owner.source_tools if hasattr(owner, 'source_tools') else owner.footer
            return dict(editor=bounds(native), toolbar=bounds(owner.toolbar._impl.native),
                compact=self.native_host.adapter.keyboard_chrome is not None,
                secondary_attached=secondary.parent is not None,
                secondary_native_attached=secondary._impl.native_toplevel.getParent() is not None,
                panel=bounds(owner.document_view._impl.native), visible_top=int(visible.top),
                visible_frame_bottom=int(visible.bottom), ime_bottom=ime_bottom,
                visible_bottom=visible_bottom, keyboard=bool(insets and insets.isVisible(ime)), ancestors=ancestry)

        def tap(native, point):
            from android.view import MotionEvent
            from android.os import SystemClock
            scale = native.getWidth() / point['width']
            down = SystemClock.uptimeMillis()
            for action in (MotionEvent.ACTION_DOWN, MotionEvent.ACTION_UP):
                event = MotionEvent.obtain(down, SystemClock.uptimeMillis(), action,
                    point['x'] * scale, point['y'] * scale, 0)
                native.dispatchTouchEvent(event)
                event.recycle()

        try:
            await asyncio.sleep(1)
            from commonUtils.runtime.local_files import LocalFiles
            from features.text_editor.resources import LocalTextCopies
            from types import SimpleNamespace
            local = output / 'local'
            local.mkdir(exist_ok=True)
            cases = [(name, source, False) for name, source in (
                ('Typing.txt', True), ('Source.md', True), ('Formatted.md', False),
                ('New.txt', True), ('New.md', False), ('Append.md', False),
                ('Heading.md', False), ('Large.md', False), ('Large-source.md', True))]
            cases += [(name, source, True) for name, source in (
                ('Local-long.md', False), ('Local-short.md', False), ('Local-source.md', True))]
            for name, source, provider in cases:
                print('EDITOR_KEYBOARD_CASE=' + name, flush=True)
                text = '' if name.startswith('New') else 'A long editable paragraph.\n\n' * 150
                if 'short' in name:
                    text = '# Heading\n\nShort note'
                if name == 'Heading.md':
                    text += '\n\n# Editable heading'
                font_size = self.preferences.values['font_size']
                if name.startswith('Large'):
                    self.preferences.values['font_size'] = '32'
                if provider:
                    (local / name).write_text(text)
                    assert await self.open_crypt(copies=LocalTextCopies(LocalFiles(local)), key=name, edit=True)
                    actual = self.private_sessions.active
                    if source:
                        actual.crypt_edit_mode.value = 'Source'
                    owner = SimpleNamespace(editor=actual.crypt_text, formatted=actual.crypt_formatted,
                        document=SimpleNamespace(text=actual.crypt_text.value), toolbar=actual.reader_toolbar,
                        document_view=actual.crypt_view, footer=actual.crypt_markdown_footer)
                else:
                    document = self.store.create(name, text.encode())
                    self.refresh_documents()
                    self.open_document(document.id)
                    self.show_documents(edit=True)
                    owner = self.editor_view
                    if name.endswith('.md') and source:
                        owner.edit_mode.value = 'Source'
                self.preferences.values['font_size'] = font_size
                if name == 'Large-source.md':
                    large_source = owner
                await asyncio.sleep(.6)
                native = owner.editor._impl.native if source else owner.formatted.view._impl.native
                case = dict(name=name, before=sample(owner, native), samples=[])
                report['cases'].append(case)
                native.requestFocus()
                if source:
                    native.setSelection(len(owner.document.text))
                    connection = native.onCreateInputConnection(EditorInfo())
                else:
                    # Match a finger tap: programmatic focus skips WebView's
                    # native focus/caret reveal and can miss whole-panel panning.
                    await owner.formatted.view.evaluate_javascript("root.scrollTop=root.scrollHeight;")
                    touch = json.loads(await owner.formatted.view.evaluate_javascript(
                        "JSON.stringify({x:30,y:Math.max(root.getBoundingClientRect().top+5,"
                        "root.getBoundingClientRect().bottom-20),width:innerWidth})"))
                    if name == 'Heading.md':
                        touch = json.loads(await owner.formatted.view.evaluate_javascript("""(() => {
                            const heading = root.querySelector('h1');
                            root.scrollTop += heading.getBoundingClientRect().top - root.getBoundingClientRect().top;
                            const bounds = heading.getBoundingClientRect();
                            return JSON.stringify({x:bounds.left+30,y:bounds.top+bounds.height/2,width:innerWidth});
                        })()"""))
                    tap(native, touch)
                    await asyncio.sleep(.4)
                manager.showSoftInput(native, InputMethodManager.SHOW_IMPLICIT)
                await asyncio.sleep(1)
                connection = native.onCreateInputConnection(EditorInfo())
                for index in range(8):
                    # Exercise the IME's composition path, not JavaScript-only
                    # edits which skip Android WebView's caret reveal behavior.
                    connection.setComposingText('typing', 1)
                    await asyncio.sleep(.05)
                    connection.setComposingText('typing continues', 1)
                    connection.commitText('typing continues' + ('\n' if source else ' '), 1)
                    await asyncio.sleep(.12)
                    data = sample(owner, native)
                    if not source:
                        data['dom'] = json.loads(await owner.formatted.view.evaluate_javascript(MEASURE))
                    else:
                        layout = native.getLayout()
                        line = layout.getLineForOffset(native.getSelectionEnd())
                        data['caret_top'] = data['editor'][1] + native.getTotalPaddingTop() + layout.getLineTop(line) - native.getScrollY()
                        data['caret_bottom'] = data['editor'][1] + native.getTotalPaddingTop() + layout.getLineBottom(line) - native.getScrollY()
                    case['samples'].append(data)
                await capture_window(self, output / (name + '.png'))
                for data in case['samples']:
                    assert data['keyboard'], 'Android software keyboard did not open'
                    assert data['toolbar'][1] >= data['visible_top'], data
                    assert abs(data['toolbar'][1] - case['samples'][0]['toolbar'][1]) <= 2, data
                    assert data['editor'][1] >= data['toolbar'][3] - 2, data
                    assert data['editor'][3] <= data['visible_bottom'] + 2, data
                    assert data['editor'][3] > data['editor'][1] + 40, data
                    assert all(item['scroll'] == 0 for item in data['ancestors'][1:]), data
                    if data['compact']:
                        assert not data['secondary_attached'] and not data['secondary_native_attached'], data
                    if not source:
                        assert abs(data['dom']['outer_scroll']) < 1, data
                        assert abs(data['dom']['viewport_top']) < 1, data
                        assert data['dom']['toolbar_top'] >= 0, data
                        assert data['dom']['toolbar_height'] + 1 >= data['dom']['button_height'], data
                        assert data['dom']['caret_top'] >= data['dom']['top'] - 2, data
                        assert data['dom']['caret_bottom'] <= data['dom']['bottom'] + 2, data
                    else:
                        assert data['caret_top'] >= data['editor'][1] - 2, data
                        assert data['caret_bottom'] <= data['editor'][3] + 2, data
                if not source and name == 'Formatted.md' and case['samples'][-1]['dom']['compact_menu']:
                    web = owner.formatted.view
                    button_point = """JSON.stringify((() => {
                        const bounds = document.querySelector(SELECTOR).getBoundingClientRect();
                        return {x:bounds.left+bounds.width/2,y:bounds.top+bounds.height/2,width:innerWidth};
                    })())"""
                    await web.evaluate_javascript("document.querySelector('nav details').open=true;")
                    point = json.loads(await web.evaluate_javascript(button_point.replace('SELECTOR', json.dumps('.compact-formatting [data-command=bold]'))))
                    tap(native, point)
                    await asyncio.sleep(.3)
                    assert not await web.evaluate_javascript("document.querySelector('nav details').open")
                    await web.evaluate_javascript("document.querySelector('nav details').open=true;document.getElementById('show-link').scrollIntoView({block:'center'});")
                    point = json.loads(await web.evaluate_javascript(button_point.replace('SELECTOR', json.dumps('#show-link'))))
                    tap(native, point)
                    await asyncio.sleep(.6)
                    case['link_dialog'] = json.loads(await web.evaluate_javascript("""JSON.stringify((() => {
                        const input = document.getElementById('link-target').getBoundingClientRect();
                        const actions = document.querySelector('.dialog-actions').getBoundingClientRect();
                        return {open:document.getElementById('link-dialog').open, height:innerHeight,
                            input_top:input.top,input_bottom:input.bottom,actions_top:actions.top,actions_bottom:actions.bottom};
                    })())"""))
                    dialog = case['link_dialog']
                    dialog['keyboard_visible'] = sample(owner, native)['keyboard']
                    dialog['fullscreen_ime'] = bool(manager.isFullscreenMode())
                    assert dialog['keyboard_visible'] and not dialog['fullscreen_ime'], dialog
                    assert dialog['open'] and dialog['input_top'] >= -1 and dialog['actions_top'] >= -1, dialog
                    assert dialog['input_bottom'] <= dialog['height'] + 1 and dialog['actions_bottom'] <= dialog['height'] + 1, dialog
                    await capture_window(self, output / 'link-dialog.png')
                    connection = native.onCreateInputConnection(EditorInfo())
                    connection.finishComposingText()
                    connection.commitText('https://example.test', 1)
                    connection.finishComposingText()
                    point = json.loads(await web.evaluate_javascript(button_point.replace('SELECTOR', json.dumps('#apply-link'))))
                    tap(native, point)
                    await asyncio.sleep(.4)
                    assert not await web.evaluate_javascript("document.getElementById('link-dialog').open")
                    assert 'https://example.test' in owner.editor.value
                    case['link_inserted'] = True
                manager.hideSoftInputFromWindow(native.getWindowToken(), 0)
                native.clearFocus()
                await asyncio.sleep(.6)
                case['dismissed'] = sample(owner, native)
                assert abs(case['dismissed']['toolbar'][1] - case['before']['toolbar'][1]) <= 2, case
                assert abs(case['dismissed']['panel'][3] - case['before']['panel'][3]) <= 2, case
            # Keep the IME open while rotating through rail/bottom navigation.
            # This also checks that the cached inactive bar is restored later.
            self.open_document(large_source.document.id)
            self.show_documents(edit=True)
            owner = large_source
            native = owner.editor._impl.native
            await asyncio.sleep(.6)
            native.setSelection(len(owner.editor.value))
            activity = self._impl.native
            original_orientation = activity.getRequestedOrientation()
            report['rotation'] = []
            rotation_text = owner.editor.value
            try:
                for label, orientation, configuration in (('portrait', 1, 1), ('landscape', 0, 2), ('portrait-return', 1, 1)):
                    activity.setRequestedOrientation(orientation)
                    for _ in range(80):
                        if activity.getResources().getConfiguration().orientation == configuration:
                            break
                        await asyncio.sleep(.1)
                    assert activity.getResources().getConfiguration().orientation == configuration
                    await asyncio.sleep(.7)
                    native.requestFocus()
                    manager.showSoftInput(native, InputMethodManager.SHOW_IMPLICIT)
                    await asyncio.sleep(.7)
                    # Rotation can let the IME resume composition of the last
                    # word. Finish it before inserting this synthetic token.
                    connection = native.onCreateInputConnection(EditorInfo())
                    connection.finishComposingText()
                    connection.commitText(' rotation', 1)
                    connection.finishComposingText()
                    await asyncio.sleep(.2)
                    data = sample(owner, native)
                    layout = native.getLayout()
                    line = layout.getLineForOffset(native.getSelectionEnd())
                    top = data['editor'][1] + native.getTotalPaddingTop() - native.getScrollY()
                    data.update(label=label, caret_top=top + layout.getLineTop(line),
                                caret_bottom=top + layout.getLineBottom(line),
                                selection=int(native.getSelectionEnd()), text_tail=owner.editor.value[-120:])
                    report['rotation'].append(data)
                    assert data['keyboard'] and data['toolbar'][1] >= data['visible_top'], data
                    assert data['editor'][3] <= data['visible_bottom'] + 2, data
                    assert data['caret_top'] >= data['editor'][1] - 2, data
                    assert data['caret_bottom'] <= data['editor'][3] + 2, data
                    assert all(item['scroll'] == 0 for item in data['ancestors'][1:]), data
                    await capture_window(self, output / ('rotation-' + label + '.png'))
                manager.hideSoftInputFromWindow(native.getWindowToken(), 0)
                native.clearFocus()
                await asyncio.sleep(.7)
                assert self.native_host.adapter.keyboard_chrome is None
                assert self.native_host.adapter.impl.native_navigationview.getVisibility() == 0
                assert activity.getSupportActionBar().isShowing()
                assert owner.editor.value.replace(' rotation', '') == rotation_text
                assert len(owner.editor.value) == len(rotation_text) + 3 * len(' rotation')
            finally:
                activity.setRequestedOrientation(original_orientation)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            await capture_window(self, output / 'failure.png')
        report['running'] = False
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('EDITOR_KEYBOARD_PROBE=' + json.dumps(dict(success=report['success'], cases=len(report['cases']), error=report.get('error'))), flush=True)


def main():
    return Probe('Editor Keyboard Probe', 'io.github.ispaure.logisticseditorkeyboardprobe')
