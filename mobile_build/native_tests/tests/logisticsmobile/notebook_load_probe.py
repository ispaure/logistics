"""Bounded single-page dense-ink, scrolling and live eraser profiling on Android."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import time
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text


class NotebookLoadProbe(NotebookProbe):
    async def check(self, app):
        from java import jclass
        from services.documents.mobile_notebooks import open_notebook
        from features.notebooks.notebook import Notebook
        output = Path(self.paths.cache)
        result = dict(success=False, synthetic=True, optical_latency_measured=False, samples=[])
        progress = output / 'notebook-memory-progress.json'
        try:
            for _ in range(400):
                if not getattr(app, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            assert await open_notebook(app, name='Dense handwriting and eraser QA')
            panel = app.notebook_panel
            await wait_for_text(panel.web, 'Dense handwriting and eraser QA')
            injector = jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks')
            native = panel.web._impl.native
            from features.notebooks import eraser
            erase_original = eraser.erase
            checkpoint_original = panel.editor.checkpoint
            timings = dict(erase_ms=0., checkpoint_ms=0.)
            def timed_erase(*args, **kwargs):
                started = time.monotonic()
                try:
                    return erase_original(*args, **kwargs)
                finally:
                    timings['erase_ms'] += (time.monotonic() - started) * 1000
            def timed_checkpoint(book):
                started = time.monotonic()
                try:
                    return checkpoint_original(book)
                finally:
                    timings['checkpoint_ms'] += (time.monotonic() - started) * 1000
            eraser.erase = timed_erase
            panel.editor.checkpoint = timed_checkpoint
            await panel.web.evaluate_javascript('''window.loadDrawMs=0;const originalDraw=draw;
                draw=(...args)=>{const t=performance.now();try{return originalDraw(...args)}
                finally{window.loadDrawMs+=performance.now()-t}}''')

            async def idle():
                for _ in range(1000):
                    state = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length,active})'))
                    if not panel.busy and not state['busy'] and not state['queued'] and state['active'] is None:
                        return
                    await asyncio.sleep(.02)
                raise AssertionError('Dense ink queue did not drain')

            async def sample(stage, **extra):
                memory = jclass('android.os.Debug$MemoryInfo')()
                jclass('android.os.Debug').getMemoryInfo(memory)
                fields = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
                row = dict(stage=stage, app_pss_kb=memory.getTotalPss(),
                    available_kb=int(fields['MemAvailable'].split()[0]),
                    strokes=len(panel.editor.notebook.page(0).strokes),
                    points=sum(len(s.points) for s in panel.editor.notebook.page(0).strokes), **extra)
                row['native'] = json.loads(panel.pen_input.nativeStatus())
                row['canvas'] = json.loads(await panel.web.evaluate_javascript('JSON.stringify({width:canvas.width,height:canvas.height})'))
                result['samples'].append(row)
                progress.write_text(json.dumps(result, indent=2))
                assert row['available_kb'] > 1200 * 1024, 'Stopping QA before device-wide memory exhaustion'

            async def geometry():
                info = json.loads(await panel.web.evaluate_javascript(
                    'JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),v:$("viewport").getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight})'))
                return ((max(info['r']['left'], info['v']['left']) + 50) * native.getWidth() / info['width'],
                        (max(info['r']['top'], info['v']['top']) + 110) * native.getHeight() / info['height'])

            await panel.web.evaluate_javascript("$('tool').value='15';$('tool').onchange();$('width').value='3';document.dispatchEvent(new Event('change'))")
            await asyncio.sleep(.2)
            await sample('opened')
            for ordinal in range(32):
                x, y = await geometry()
                before = len(panel.editor.notebook.page(0).strokes)
                started = time.monotonic()
                injector.rawStroke(panel.pen_input, native, x, y + ordinal * 12, 4096, 0)
                for _ in range(1000):
                    if len(panel.editor.notebook.page(0).strokes) == before + 1:
                        break
                    await asyncio.sleep(.02)
                await idle()
                assert len(panel.editor.notebook.page(0).strokes) == before + 1
                assert injector.handoffReleased(), 'Native renderer still held during WebView handoff'
                await sample(f'long-stroke-{ordinal + 1}', elapsed_ms=(time.monotonic() - started) * 1000)
            for zoom in ('fit', '2'):
                await panel.web.evaluate_javascript("$('zoom').value='" + zoom + "';resize()")
                for step in range(12):
                    await panel.web.evaluate_javascript('$("viewport").scrollTop=' + str(step * 60))
                    await asyncio.sleep(.08)
                await sample('scroll-' + zoom)
                await panel.web.evaluate_javascript("mode='erase';eraserKind='partial';$('viewport').scrollTop=0;document.dispatchEvent(new Event('change'))")
                await asyncio.sleep(.2)
                x, y = await geometry()
                timings.update(erase_ms=0., checkpoint_ms=0.)
                await panel.web.evaluate_javascript('window.loadDrawMs=0')
                started = time.monotonic()
                injector.contact(native, 0, x, y, .3)
                for point in range(60):
                    injector.contact(native, 2, x + point * 2, y + point, .5)
                    await asyncio.sleep(.008)
                injector.contact(native, 1, x + 120, y + 60, 0)
                await idle()
                await sample('eraser-' + zoom, elapsed_ms=(time.monotonic() - started) * 1000,
                    **timings, draw_ms=await panel.web.evaluate_javascript('window.loadDrawMs'))
                await panel.perform(dict(op='undo'))
                await idle()
                await sample('undo-' + zoom)
            encoded = await asyncio.to_thread(panel.editor.notebook.to_bytes)
            assert sum(len(s.points) for s in Notebook.read(encoded).page(0).strokes) == 32 * 4096
            await panel.web.evaluate_javascript("$('tool').onchange();document.dispatchEvent(new Event('change'))")
            await asyncio.sleep(.2)
            for ordinal in range(8):
                x, y = await geometry()
                before = len(panel.editor.notebook.page(0).strokes)
                injector.rawPressureStroke(panel.pen_input, native, x, y + ordinal * 12, 1024, 2)
                for _ in range(1000):
                    if len(panel.editor.notebook.page(0).strokes) == before + 1:
                        break
                    await asyncio.sleep(.02)
                await idle()
                assert len(panel.editor.notebook.page(0).strokes) == before + 1
                assert injector.handoffReleased(), 'Native renderer still held during WebView handoff'
                await sample('fluctuating-pressure-' + str(ordinal + 1))
            encoded = await asyncio.to_thread(panel.editor.notebook.to_bytes)
            assert sum(len(s.points) for s in Notebook.read(encoded).page(0).strokes) == 32 * 4096 + 8 * 1024
            (output / 'notebook-memory.rmdoc').write_bytes(encoded)
            result['success'] = True
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'notebook-memory-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookLoadProbe('Dense handwriting QA', 'io.github.ispaure.logisticsnotebookqa')
