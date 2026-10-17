"""Isolated Markdown/source validation; synthetic data and separate app ID."""
import asyncio
import json
from pathlib import Path
import traceback

from logisticsmobile.app import LogisticsMobile


class EditorProbe(LogisticsMobile):
    def startup(self):
        (Path(self.paths.cache)/'editor-progress.txt').write_text('startup')
        self.storage_root = Path(self.paths.cache) / 'editor-probe'
        try:
            super().startup()
        except BaseException:
            (Path(self.paths.cache)/'editor-progress.txt').write_text(traceback.format_exc())
            raise
        (Path(self.paths.cache)/'editor-progress.txt').write_text('started')

    def on_running(self):
        (Path(self.paths.cache)/'editor-progress.txt').write_text('running')
        self.loop.create_task(self.probe())

    async def probe(self):
        output = self.private_root / 'evidence'
        output.mkdir(exist_ok=True)
        result = {'success': False}
        try:
            doc = self.store.create('Live.md', b'# Live preview\n\n| Source | Result |\n| --- | --- |\n| **Markdown** | Ready |\n\n- Parent\n  - Child\n')
            self.refresh_documents()
            self.open_document(doc.id)
            self.show_documents()
            owner = self.editor_view
            await asyncio.sleep(1)
            assert owner.session.view['markdown_mode'] == 'preview'
            self.show_documents(edit=True)
            await asyncio.sleep(1)
            assert owner.editor_area.children == [owner.formatted.view]
            assert owner.editor.value == doc.text
            web = owner.formatted.view
            assert await web.evaluate_javascript('document.querySelectorAll("table").length') == 1
            before = owner.document.text
            await web.evaluate_javascript("""(() => {
                const heading = document.querySelector('section[contenteditable=true] h1');
                const selection = getSelection();
                const range = document.createRange();
                range.selectNodeContents(heading); range.collapse(false);
                selection.removeAllRanges(); selection.addRange(range); heading.focus();
                document.execCommand('insertText', false, ' updated');
            })()""")
            for attempt in range(30):
                if owner.document.text != before:
                    break
                await asyncio.sleep(.1)
            assert owner.document.text.startswith('# Live preview updated'), repr(owner.document.text)
            assert owner.document.text.endswith('- Parent\n  - Child\n')
            assert owner.editor.value == owner.document.text
            await web.evaluate_javascript("""(() => {
                const cell = document.querySelectorAll('td')[1];
                cell.closest('section').focus();
                const selection = getSelection(), range = document.createRange();
                range.selectNodeContents(cell);
                selection.removeAllRanges(); selection.addRange(range);
                document.querySelector('[data-command="italic"]').click();
            })()""")
            for attempt in range(30):
                if '*Ready*' in owner.document.text:
                    break
                await asyncio.sleep(.1)
            assert '*Ready*' in owner.document.text, repr(owner.document.text)
            assert owner.document.text.endswith('- Parent\n  - Child\n')
            result['formatted_bridge_and_preservation'] = True
            result['formatting_toolbar'] = True
            await web.evaluate_javascript("""(() => {
                const cell = document.querySelector('td');
                cell.closest('section').focus();
                const range = document.createRange(); range.selectNodeContents(cell);
                getSelection().removeAllRanges(); getSelection().addRange(range);
                document.querySelector('[data-table="row"]').click();
            })()""")
            assert await web.evaluate_javascript('document.querySelector("table").rows.length') == 3
            await web.evaluate_javascript("""(() => {
                const cell = document.querySelector('td');
                cell.closest('section').focus();
                const range = document.createRange(); range.selectNodeContents(cell);
                getSelection().removeAllRanges(); getSelection().addRange(range);
                document.querySelector('[data-table="column"]').click();
            })()""")
            assert await web.evaluate_javascript('document.querySelector("table").rows[0].cells.length') == 3
            await web.evaluate_javascript("document.querySelector('[data-command=undo]').click()")
            assert await web.evaluate_javascript('document.querySelector("table").rows[0].cells.length') == 2
            await web.evaluate_javascript("document.querySelector('[data-command=redo]').click()")
            assert await web.evaluate_javascript('document.querySelector("table").rows[0].cells.length') == 3
            await asyncio.sleep(.2)
            assert owner.document.text.endswith('- Parent\n  - Child\n')
            result['table_structure_undo'] = True
            from tests.logisticsmobile.fixtures import capture_window
            await capture_window(self, output / 'markdown-formatted.png')
            owner.edit_mode.value = 'Source'
            assert owner.editor_area.children == [owner.editor]
            from rubicon.objc import NSRange
            native = owner.editor._impl.native
            native.selectedRange = NSRange(len(owner.editor.value), 0)
            before = owner.editor.value
            native.insertText('\n## Typed update')
            await asyncio.sleep(1)
            assert owner.document.text == before + '\n## Typed update'
            result['source_fallback'] = True
            result['line_starts'] = owner.editor.line_starts
            assert float(native.textContainerInset.left) >= 40
            result['gutter_inset'] = float(native.textContainerInset.left)
            owner.name.value = 'sample.py'
            owner.editor.value = 'def greet(name):\n    # Unicode 😀\n    return "Hello " + name\n'
            native.selectedRange = NSRange(4, 0)
            await asyncio.sleep(1)
            assert owner.editor.language == 'python'
            assert int(native.selectedRange.location) == 4
            result['composition'] = str(native.markedTextRange)
            result['composing'] = owner.editor.composing()
            result['backend'] = type(owner.editor._impl).__module__
            result['worker'] = str(owner.editor.worker)
            result['pending'] = str(owner.editor.pending)
            await owner.editor.highlight()
            colour = native.textStorage.attribute('NSColor', atIndex=0, effectiveRange=None)
            assert colour is not None
            result['python_colour'] = str(colour)
            result['gutter_error'] = getattr(owner.editor, 'gutter_error', '')
            result['gutter_frame'] = str(owner.editor._impl.gutter.frame)
            assert not result['gutter_error'], result['gutter_error']
            result['selection_preserved'] = True
            await capture_window(self, output / 'source-python.png')
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
            try:
                result['dom'] = await self.editor_view.formatted.view.evaluate_javascript('document.getElementById("document").innerHTML')
                result['notice'] = await self.editor_view.formatted.view.evaluate_javascript('document.getElementById("notice").textContent')
                result['source'] = self.editor_view.document.text
            except Exception:
                pass
        (output / 'editor.json').write_text(json.dumps(result, indent=2))
        print('LOGISTICS_EDITOR_PROBE=' + json.dumps(result), flush=True)


def main():
    return EditorProbe('Editor Probe', 'io.github.ispaure.logisticseditorprobe')
