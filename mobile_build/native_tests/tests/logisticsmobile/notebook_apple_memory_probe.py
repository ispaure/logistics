"""WKWebView page-two/zoom regression; simulator pen events, synthetic files only."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import resource
import traceback

from .notebook_probe import NotebookProbe
from .notebook_memory_checks import INSTALL, ink_signature, recovery_history_stats
from .web_checks import wait_for_text


class AppleMemoryProbe(NotebookProbe):
    async def check(self, app):
        from features.notebooks.notebook import Notebook
        from services.documents.mobile_notebooks import open_notebook
        from .fixtures import capture_window
        output = Path(self.paths.cache)
        result = dict(success=False, surfaces=[], samples=[], raster=[], synthetic=True,
                      physical_pencil_tested=False)
        try:
            for _ in range(400):
                if not getattr(app, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            app.show_home()
            await asyncio.sleep(.3)
            app.set_feature_enabled('notebooks', True, refresh=False)
            original = Notebook.new('Apple page two memory QA')
            for _ in range(3):
                original.add_page()
            source = Path(app.private_root) / 'LocalFiles/memory-source.rmdoc'
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(original.to_bytes())
            original_hash = sha256(source.read_bytes()).hexdigest()
            opened = await open_notebook(app, path=source)
            assert opened, getattr(getattr(getattr(app, 'notebook_panel', None), 'status', None), 'text', '')
            panel = app.notebook_panel
            assert panel.document.recovery is not None, 'Recovery must participate in this memory test'
            await wait_for_text(panel.web, original.name)
            await asyncio.sleep(.5)
            result['backend'] = type(panel.web._impl).__module__
            assert result['backend'].startswith('toga_iOS.')

            async def js(script):
                return await panel.web.evaluate_javascript(script)

            async def value(expression):
                # WKWebView/Toga can return scalar results as strings. Cross
                # this boundary as JSON so false/null retain their real types.
                return json.loads(await js('JSON.stringify(' + expression + ')'))

            async def idle():
                for _ in range(600):
                    status = json.loads(await js('JSON.stringify({busy,queued:queue.length,done:window.memoryProbe?.done,error:window.memoryProbe?.error})'))
                    assert not status.get('error'), status
                    if not panel.busy and not status['busy'] and not status['queued'] and status.get('done', True):
                        return
                    await asyncio.sleep(.03)
                raise AssertionError('Ink queue did not drain')

            await js(INSTALL)
            tools = list(panel.editor.state()['tools'].values())
            for zoom in ('fit', '1', '1.5', '2', '4', 'fit'):
                await js('memoryProbe.zoom(' + json.dumps(zoom) + ')')
                await asyncio.sleep(.15)
                for index in range(4):
                    before = ink_signature(panel.editor.notebook)
                    writes = await value('memoryProbe.writes')
                    await js('send({op:"page",index:' + str(index) + '})')
                    await idle()
                    assert ink_signature(panel.editor.notebook) == before
                    assert await value('memoryProbe.writes') == writes
                    for ordinal, tool in enumerate(tools):
                        await js(f'memoryProbe.stroke({tool},{ordinal % 3 + 1})')
                        await idle()
                    surface = json.loads(await js('JSON.stringify(memoryProbe.surface())'))
                    assert surface['width'] * surface['height'] <= 8 * 1024 * 1024
                    result['surfaces'].append(dict(zoom=zoom, page=index + 1, **surface))
                    result['samples'].append(dict(zoom=zoom, page=index + 1,
                        host_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        **recovery_history_stats(panel.editor)))
                    stats = result['samples'][-1]
                    assert stats['retained_strokes'] == stats['visible_strokes'], stats
                    assert stats['retained_native_blocks'] == stats['visible_strokes'], stats
                    (output / 'notebook-memory-progress.json').write_text(json.dumps(result, indent=2))
                if zoom in ('fit', '2'):
                    await js('memoryProbe.raster()')
                    for _ in range(200):
                        if await value('memoryProbe.rasterDone'):
                            break
                        await asyncio.sleep(.03)
                    assert await value('memoryProbe.rasterDone'), 'Raster round trip did not finish'
                    error = await value('memoryProbe.rasterError')
                    assert error is None, error
                    pixels = await value('memoryProbe.rasterResult')
                    assert pixels['inkPixels'] > 0 and pixels['differentPixels'] == 0, pixels
                    result['raster'].append(dict(zoom=zoom, **pixels))
                (output / 'notebook-memory-progress.json').write_text(json.dumps(result, indent=2))
            book = panel.editor.notebook
            expected = ink_signature(book)
            assert [len(book.page(i).strokes) for i in range(4)] == [54] * 4
            await js('draw();memoryProbe.historyRaster=canvas.toDataURL()')
            for op in ('undo', 'redo'):
                for _ in range(36):
                    await js('send({op:' + json.dumps(op) + '})')
                    await idle()
                if op == 'undo':
                    assert sum(len(book.page(i).strokes) for i in range(4)) == 216 - 36
            await js('send({op:"page",index:3})')
            await idle()
            assert ink_signature(book) == expected
            assert await value('(()=>{draw();return canvas.toDataURL()===memoryProbe.historyRaster})()')
            assert ink_signature(panel.document.recovery.open(panel.document.key)) == expected
            assert sha256(source.read_bytes()).hexdigest() == original_hash, 'Editing changed source before Save'
            await js('send({op:"save"})')
            await idle()
            saved = Notebook.read(source.read_bytes())
            assert ink_signature(saved) == expected
            destination = output / 'notebook-memory.rmdoc'
            destination.write_bytes(saved.to_bytes())
            assert ink_signature(Notebook.read(destination.read_bytes())) == expected
            result.update(success=True, strokes_per_page=[54] * 4, page_switches_preserve_ink=True,
                          source_unchanged_until_save=True, saved_native_ink_identical=True,
                          recovery_enabled=True, recovery_reopened_ink_identical=True,
                          undo_redo_steps=36, undo_redo_ink_and_raster_identical=True,
                          history=recovery_history_stats(panel.editor))
            await capture_window(app, output / 'notebook-memory.png')
        except BaseException:
            result['error'] = traceback.format_exc()
        (output / 'notebook-memory-result.json').write_text(json.dumps(result, indent=2))


def main():
    return AppleMemoryProbe('Apple notebook memory QA', 'io.github.ispaure.logisticsnotebookqa')
