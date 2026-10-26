"""Long multi-page Android editing with native callbacks, screenshots and memory evidence."""
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .notebook_memory_checks import ink_signature
from .web_checks import wait_for_text
from .fixtures import capture_window


class NotebookSoakProbe(NotebookProbe):
    async def check(self, app):
        from java import jclass
        from services.documents.mobile_notebooks import open_notebook
        from features.notebooks.notebook import Notebook
        from features.notebooks.editor import Editor
        output = Path(self.paths.cache)
        progress = output / 'notebook-memory-progress.json'
        result = dict(success=False, synthetic=True, optical_latency_measured=False, samples=[], screenshots=[])
        try:
            for _ in range(400):
                if not getattr(app, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            book = Notebook.new('Six-page stability QA')
            for _ in range(5):
                book.add_page()
            source = self.private_root / 'stability-soak.rmdoc'
            source.write_bytes(book.to_bytes())
            assert await open_notebook(app, path=source)
            panel = app.notebook_panel
            book = panel.editor.notebook
            await wait_for_text(panel.web, book.name)
            injector = jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks')

            async def idle():
                for _ in range(600):
                    state = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length,active})'))
                    if not panel.busy and not state['busy'] and not state['queued'] and state['active'] is None:
                        return
                    await asyncio.sleep(.03)
                raise AssertionError('Notebook edit queue did not drain')

            async def sample(stage, screenshot=False):
                memory = jclass('android.os.Debug$MemoryInfo')()
                jclass('android.os.Debug').getMemoryInfo(memory)
                fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
                pages = panel.editor.notebook.pages + [p for s in panel.editor.undo for p in s[0]]
                unique = {id(s) for p in pages if p.ink for s in p.ink.strokes}
                row = dict(stage=stage, app_pss_kb=memory.getTotalPss(),
                    native_heap_bytes=jclass('android.os.Debug').getNativeHeapAllocatedSize(),
                    available_kb=int(fields['MemAvailable'].split()[0]),
                    unique_strokes=len(unique), undo=len(panel.editor.undo),
                    strokes=sum(len(panel.editor.notebook.page(i).strokes) for i in range(6)),
                    canvas=json.loads(await panel.web.evaluate_javascript('JSON.stringify({width:canvas.width,height:canvas.height})')))
                for category in ('native-heap', 'java-heap', 'graphics', 'private-other'):
                    row[category + '_kb'] = memory.getMemoryStat('summary.' + category)
                result['samples'].append(row)
                progress.write_text(json.dumps(result, indent=2))
                if screenshot:
                    name = f'notebook-soak-{len(result["screenshots"]):02d}.png'
                    await capture_window(app, output / name)
                    result['screenshots'].append(name)
                print('Notebook soak: ' + json.dumps(row), flush=True)

            async def geometry():
                native = panel.web._impl.native
                info = json.loads(await panel.web.evaluate_javascript(
                    'JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),v:$("viewport").getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})'))
                x = (max(info['r']['left'], info['v']['left']) + 50) * native.getWidth() / info['width']
                y = (max(info['r']['top'], info['v']['top']) + 110) * native.getHeight() / info['height']
                return native, x, y

            await sample('opened')
            # Long raw contacts exercise the actual production buffer/pressure/save
            # callback. They do not claim optical latency or digitizer validation.
            for index in range(6):
                await panel.perform(dict(op='page', index=index))
                await panel.web.evaluate_javascript("$('tool').value='15';$('tool').onchange();$('color').value='6';$('width').value='3';document.dispatchEvent(new Event('change'))")
                await asyncio.sleep(.12)
                native, x, y = await geometry()
                for ordinal in range(10):
                    count = len(book.page(index).strokes)
                    injector.rawStroke(panel.pen_input, native, x, y + ordinal * 15, 512, 0)
                    for _ in range(400):
                        if len(book.page(index).strokes) == count + 1:
                            break
                        await asyncio.sleep(.02)
                    await idle()
                    assert len(book.page(index).strokes) == count + 1
                    assert len(book.page(index).strokes[-1].points) == 512
                await sample(f'native-page-{index + 1}', screenshot=index in (0, 5))
            result['native'] = json.loads(panel.pen_input.nativeStatus())
            assert result['native']['samples'] == 60 * 512 and not result['native']['error'], result['native']
            # History-rich Android delivery also covers the brushes using ordinary
            # rendering, including blur, grain, transparency and the fixed nib.
            panel.pen_input.disableNativePreview()
            tools = (12, 14, 13, 16, 18, 21, 23, 17, 15)
            for round_, zoom in enumerate(('fit', '2')):
                await panel.web.evaluate_javascript("$('zoom').value='" + zoom + "';resize()")
                await asyncio.sleep(.15)
                for index in range(6):
                    await panel.perform(dict(op='page', index=index))
                    for ordinal in range(10):
                        tool = tools[(ordinal + index) % len(tools)]
                        await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('width').value='2'")
                        native, x, y = await geometry()
                        count = len(book.page(index).strokes)
                        injector.historyStroke(native, x, y + ordinal * 12, 512)
                        await idle()
                        assert len(book.page(index).strokes) == count + 1
                    await sample(f'ordinary-{zoom}-page-{index + 1}', screenshot=index in (0, 5))
                    assert result['samples'][-1]['unique_strokes'] == result['samples'][-1]['strokes']
            assert [len(book.page(i).strokes) for i in range(6)] == [30] * 6
            signature = ink_signature(book)
            for _ in range(5):
                await panel.perform(dict(op='undo'))
            for _ in range(5):
                await panel.perform(dict(op='redo'))
            assert ink_signature(book) == signature
            await panel.perform(dict(op='erase', points=[[40, 180, .5], [300, 180, .5]], radius=16, kind='partial'))
            await panel.perform(dict(op='undo'))
            assert ink_signature(book) == signature
            await sample('history-and-eraser', screenshot=True)
            await panel.web.evaluate_javascript("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();$('pagesToggle').click()")
            for _ in range(300):
                if await panel.web.evaluate_javascript("document.querySelectorAll('.page-previews button').length===6"):
                    break
                await asyncio.sleep(.05)
            await asyncio.sleep(.2)
            await sample('page-overview', screenshot=True)
            await panel.web.evaluate_javascript("document.querySelectorAll('.page-previews button')[3].click()")
            await idle()
            await panel.perform(dict(op='save'))
            assert ink_signature(Notebook.read(source.read_bytes())) == signature
            (output / 'notebook-memory.rmdoc').write_bytes(source.read_bytes())
            for ordinal in range(6):
                current = panel.document
                reopened = Notebook.read(source.read_bytes())
                current.recovery.adopt(current.key, reopened, current.book)
                current.book = reopened
                panel.editor = Editor(reopened, current.checkpoint)
                panel.editor.index = ordinal
                previous = panel.web._impl.native
                panel.mount_canvas()
                await wait_for_text(panel.web, reopened.name)
                await asyncio.sleep(.25)
                assert previous.getParent() is None
                assert ink_signature(reopened) == signature
                book = reopened
                await sample(f'reopened-{ordinal + 1}')
            await panel.web.evaluate_javascript("$('tool').value='15';$('tool').onchange();document.dispatchEvent(new Event('change'))")
            await asyncio.sleep(.15)
            native, x, y = await geometry()
            injector.rawStroke(panel.pen_input, native, x, y, 512, 0)
            for _ in range(400):
                if len(book.page(5).strokes) == 31:
                    break
                await asyncio.sleep(.02)
            await idle()
            assert len(book.page(5).strokes) == 31
            await panel.perform(dict(op='save'))
            assert ink_signature(Notebook.read(source.read_bytes())) == ink_signature(book)
            (output / 'notebook-memory.rmdoc').write_bytes(source.read_bytes())
            await capture_window(app, output / 'notebook-memory.png')
            await sample('finished')
            result.update(success=True, final_strokes=181, samples_per_stroke=512, pages=6,
                native_contacts=61, android_history_contacts=120, saved_ink_identical=True,
                undo_redo=True, partial_eraser_undo=True, reloads=6)
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'notebook-memory-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookSoakProbe('Notebook stability QA', 'io.github.ispaure.logisticsnotebookqa')
