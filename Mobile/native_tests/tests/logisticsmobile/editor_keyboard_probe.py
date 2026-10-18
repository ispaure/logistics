"""Isolated long-document typing and keyboard geometry checks."""
import asyncio
import json
from pathlib import Path
import traceback

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
        focused:root.contains(document.activeElement)};
})())"""


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'isolated-editor-keyboard'
        super().startup()

    def on_running(self):
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
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        (output / 'result.json').write_text(json.dumps(report, indent=2))

    async def android_probe(self):
        from android.content import Context
        from android.graphics import Rect
        from android.view.inputmethod import EditorInfo, InputMethodManager
        from java import jarray, jint, jclass
        output = Path(self.paths.cache) / 'editor-keyboard-evidence'
        output.mkdir(exist_ok=True)
        report = dict(success=False, cases=[])
        manager = self._impl.native.getSystemService(Context.INPUT_METHOD_SERVICE)

        def bounds(native):
            point = jarray(jint)(2)
            native.getLocationOnScreen(point)
            return [int(point[0]), int(point[1]), int(point[0] + native.getWidth()), int(point[1] + native.getHeight())]

        def sample(owner, native):
            visible = Rect()
            native.getWindowVisibleDisplayFrame(visible)
            insets = jclass('androidx.core.view.ViewCompat').getRootWindowInsets(native)
            ancestry, parent = [], native
            while parent is not None and hasattr(parent, 'getScrollY'):
                ancestry.append(dict(kind=str(parent.getClass().getName()), scroll=int(parent.getScrollY()), bounds=bounds(parent)))
                parent = parent.getParent()
            return dict(editor=bounds(native), toolbar=bounds(owner.toolbar._impl.native),
                panel=bounds(owner.document_view._impl.native), visible_top=int(visible.top),
                visible_bottom=int(visible.bottom), keyboard=bool(insets and insets.isVisible(
                    jclass('androidx.core.view.WindowInsetsCompat$Type').ime())), ancestors=ancestry)

        try:
            await asyncio.sleep(1)
            for name, source in (('Typing.txt', True), ('Source.md', True), ('Formatted.md', False),
                                 ('New.txt', True), ('New.md', False), ('Append.md', False)):
                text = '' if name.startswith('New') else 'A long editable paragraph.\n\n' * 150
                document = self.store.create(name, text.encode())
                self.refresh_documents()
                self.open_document(document.id)
                self.show_documents(edit=True)
                owner = self.editor_view
                if name.endswith('.md') and source:
                    owner.edit_mode.value = 'Source'
                await asyncio.sleep(.6)
                native = owner.editor._impl.native if source else owner.formatted.view._impl.native
                case = dict(name=name, before=sample(owner, native), samples=[])
                report['cases'].append(case)
                native.requestFocus()
                if source:
                    native.setSelection(len(owner.document.text))
                    connection = native.onCreateInputConnection(EditorInfo())
                else:
                    await owner.formatted.view.evaluate_javascript("""(() => {
                        const target = APPEND ? root.lastElementChild : Array.from(root.querySelectorAll('p')).filter(p=>p.textContent).at(-1);
                        target.closest('section').focus();
                        const range=document.createRange();range.selectNodeContents(target);range.collapse(false);
                        getSelection().removeAllRanges();getSelection().addRange(range);
                        root.scrollTop=root.scrollHeight;scheduleCaretReveal();
                    })()""".replace('APPEND', 'true' if name in ('New.md', 'Append.md') else 'false'))
                manager.showSoftInput(native, InputMethodManager.SHOW_IMPLICIT)
                await asyncio.sleep(1)
                connection = native.onCreateInputConnection(EditorInfo())
                for index in range(20):
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
                    assert data['editor'][1] >= data['toolbar'][3] - 2, data
                    assert data['editor'][3] <= data['visible_bottom'] + 2, data
                    assert data['editor'][3] > data['editor'][1] + 40, data
                    assert all(item['scroll'] == 0 for item in data['ancestors'][1:]), data
                    if not source:
                        assert abs(data['dom']['outer_scroll']) < 1, data
                        assert data['dom']['caret_top'] >= data['dom']['top'] - 2, data
                        assert data['dom']['caret_bottom'] <= data['dom']['bottom'] + 2, data
                    else:
                        assert data['caret_top'] >= data['editor'][1] - 2, data
                        assert data['caret_bottom'] <= data['editor'][3] + 2, data
                manager.hideSoftInputFromWindow(native.getWindowToken(), 0)
                native.clearFocus()
                await asyncio.sleep(.6)
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            await capture_window(self, output / 'failure.png')
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print('EDITOR_KEYBOARD_PROBE=' + json.dumps(report), flush=True)


def main():
    return Probe('Editor Keyboard Probe', 'io.github.ispaure.logisticseditorkeyboardprobe')
