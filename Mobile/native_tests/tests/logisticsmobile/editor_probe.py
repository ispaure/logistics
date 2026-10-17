"""Isolated native source-editor validation; synthetic data and separate app ID."""
import asyncio
import json
from pathlib import Path
import traceback

from logisticsmobile.app import LogisticsMobile


class EditorProbe(LogisticsMobile):
    def startup(self):
        (Path(self.paths.cache)/'editor-progress.txt').write_text('startup')
        self.storage_root = Path(self.paths.cache) / 'editor-probe'
        super().startup()
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
            assert owner.split_preview in owner.editor_area.children
            assert owner.editor.value == doc.text
            result['layout'] = str(owner.editor_area.style.direction)
            assert await owner.split_preview.evaluate_javascript('document.querySelectorAll("table").length') == 1
            assert owner.editor.language == 'markdown'
            from rubicon.objc import NSRange
            native = owner.editor._impl.native
            native.selectedRange = NSRange(len(owner.editor.value), 0)
            before = owner.editor.value
            native.insertText('\n## Typed update')
            await asyncio.sleep(1)
            assert owner.document.text == before + '\n## Typed update'
            assert await owner.split_preview.evaluate_javascript('Boolean(document.getElementById("typed-update"))')
            result['source_and_live_preview'] = True
            result['line_starts'] = owner.editor.line_starts
            assert float(native.textContainerInset.left) >= 40
            result['gutter_inset'] = float(native.textContainerInset.left)
            from tests.logisticsmobile.fixtures import capture_window
            await capture_window(self, output / 'markdown-live.png')
            owner.toggle_split()
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
            result['selection_preserved'] = True
            await capture_window(self, output / 'source-python.png')
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'editor.json').write_text(json.dumps(result, indent=2))
        print('LOGISTICS_EDITOR_PROBE=' + json.dumps(result), flush=True)


def main():
    return EditorProbe('Editor Probe', 'io.github.ispaure.logisticseditorprobe')
