"""Physical Android page-switch and handwriting memory regression, synthetic data only."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import asyncio
import json
import math
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text


class NotebookMemoryProbe(NotebookProbe):
    async def check(self, app):
        from java import jclass
        from services.documents.mobile_notebooks import open_notebook
        from features.notebooks.notebook import Notebook
        from .fixtures import capture_window
        output = Path(self.paths.cache)
        progress = output / 'notebook-memory-progress.json'
        result = dict(success=False, samples=[], synthetic=True)
        panel = None
        def sample(stage):
            memory = jclass('android.os.Debug$MemoryInfo')()
            jclass('android.os.Debug').getMemoryInfo(memory)
            fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
            row = dict(stage=stage, app_pss_kb=memory.getTotalPss(),
                       available_kb=int(fields['MemAvailable'].split()[0]))
            result['samples'].append(row)
            progress.write_text(json.dumps(result, indent=2))
            print('Notebook memory QA: ' + json.dumps(row), flush=True)
        try:
            for _ in range(400):
                if not getattr(app, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            app.set_feature_enabled('notebooks', True, refresh=False)
            assert await open_notebook(app, name='Synthetic page two memory QA')
            panel = app.notebook_panel
            book = Notebook.new('Synthetic page two memory QA')
            book.add_page()
            assert await panel.load(lambda: book)
            await wait_for_text(panel.web, book.name)
            await asyncio.sleep(.5)
            native = panel.web._impl.native
            injector = jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks')

            async def idle():
                for _ in range(300):
                    state = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length})'))
                    if not panel.busy and not state['busy'] and not state['queued']:
                        return
                    await asyncio.sleep(.03)
                raise AssertionError('Ink queue did not drain')

            sample('opened')
            await panel.web.evaluate_javascript('''window.memoryResizeWrites=0;
                for(let name of ['width','height']){
                    const property=Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype,name);
                    Object.defineProperty(HTMLCanvasElement.prototype,name,{...property,set(value){
                        if(this===canvas||this===draft||this===mask)memoryResizeWrites++;
                        property.set.call(this,value);
                    }});
                }''')
            result['surface'] = json.loads(await panel.web.evaluate_javascript(
                'JSON.stringify({width:canvas.width,height:canvas.height,options:ctx.getContextAttributes()})'))
            for round_ in range(3):
                for index in (0, 1):
                    await panel.web.evaluate_javascript('send({op:"page",index:' + str(index) + '})')
                    await idle()
                    await panel.web.evaluate_javascript("$('tool').value='12';$('tool').onchange()")
                    geometry = json.loads(await panel.web.evaluate_javascript(
                        'JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})'))
                    x = (geometry['r']['left'] + 40) * native.getWidth() / geometry['width']
                    y = (geometry['r']['top'] + 100) * native.getHeight() / geometry['height']
                    before = len(panel.editor.notebook.page(index).strokes)
                    for stroke in range(20):
                        injector.stroke(native, x, y + stroke * 12)
                        await idle()
                        if stroke % 5 == 4:
                            sample(f'round-{round_}-page-{index + 1}-stroke-{stroke + 1}')
                    assert len(panel.editor.notebook.page(index).strokes) == before + 20
                    assert panel.editor.index == index
            assert [len(book.page(i).strokes) for i in range(2)] == [60, 60]
            result['page_switch_resize_writes'] = await panel.web.evaluate_javascript('memoryResizeWrites')
            for zoom, index in (('fit', 0), ('fit', 1), ('2', 0), ('2', 1)):
                await panel.web.evaluate_javascript('send({op:"page",index:' + str(index) + '})')
                await idle()
                await panel.web.evaluate_javascript("$('zoom').value='" + zoom + "';resize()")
                await asyncio.sleep(.3)
                result.setdefault('zoom_surfaces', []).append(json.loads(await panel.web.evaluate_javascript(
                    'JSON.stringify({zoom:$("zoom").value,width:canvas.width,height:canvas.height})')))
                for stroke in range(2):
                    injector.contact(native, 0, x, y, .3)
                    for point in range(250):
                        injector.contact(native, 2, x + point * .5, y + math.sin(point / 8) * 35, .5)
                        await asyncio.sleep(.01)
                        if point % 100 == 99:
                            sample(f'zoom-{zoom}-page-{index + 1}-stroke-{stroke + 1}-point-{point + 1}')
                    injector.contact(native, 1, x + 200, y, 0)
                    await idle()
            encoded = await asyncio.to_thread(book.to_bytes)
            recovered = Notebook.read(encoded)
            assert [len(recovered.page(i).strokes) for i in range(2)] == [64, 64]
            result['stroke_counts'] = [64, 64]
            result['max_surface_pixels'] = max(row['width'] * row['height'] for row in result['zoom_surfaces'])
            if await panel.web.evaluate_javascript('canvasPixelLimit') is not None:
                assert result['max_surface_pixels'] <= 8 * 1024 * 1024
                assert result['page_switch_resize_writes'] == 0
            (output / 'notebook-memory.rmdoc').write_bytes(encoded)
            await capture_window(app, output / 'notebook-memory.png')
            sample('finished')
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'notebook-memory-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookMemoryProbe('Notebook memory QA', 'io.github.ispaure.logisticsnotebookqa')
