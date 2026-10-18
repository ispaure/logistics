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


def main():
    return Probe('Editor Keyboard Probe', 'io.github.ispaure.logisticseditorkeyboardprobe')
