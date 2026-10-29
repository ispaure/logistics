"""Hands-on production-native preview, pen-up appearance and save/reopen QA."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text


class BooxPreviewProbe(NotebookProbe):
    async def check(self, app):
        output = Path(self.paths.cache) / 'boox-raw-ink'
        output.mkdir(exist_ok=True)
        result = dict(success=False, production_native=True, optical_latency_measured=False, stages=[])
        def stage(name, **values):
            (output / 'stage.json').write_text(json.dumps(dict(stage=name, **values), indent=2))
        async def wait_for(predicate, message):
            for _ in range(3000):
                if await predicate():
                    return
                await asyncio.sleep(.2)
            raise TimeoutError(message)
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            task = getattr(self, 'cloud_startup_task', None)
            if task is not None:
                await task
            from features.notebooks.notebook import Notebook
            from services.documents.mobile_notebooks import open_notebook
            source = self.private_root / 'preview-check.rmdoc'
            book = Notebook.new('Native preview check')
            book.add_page()
            source.write_bytes(book.to_bytes())
            assert await open_notebook(self, path=source)
            panel = self.notebook_panel
            async def reopen_saved():
                current = panel.document
                reopened = Notebook.read(source.read_bytes())
                if current.recovery is not None:
                    current.recovery.adopt(current.key, reopened, current.book)
                from features.notebooks.editor import Editor
                from features.notebooks.protocol import update_script
                current.book = reopened
                panel.editor = Editor(reopened, current.checkpoint)
                await panel.web.evaluate_javascript(update_script(panel.state()))
                # Verify the freshly loaded model is still a valid recovery
                # writer before returning it to the user's pen.
                panel.document.checkpoint(panel.editor.notebook)
                await panel.perform(dict(op='save'))
            async def idle():
                async def ready():
                    value = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queued:queue.length,active})'))
                    return not panel.busy and not value['busy'] and not value['queued'] and value['active'] is None
                await wait_for(ready, 'Notebook bridge did not settle')
            async def choose(tool, color):
                await panel.web.evaluate_javascript("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value=" + repr(str(color)) + ";$('width').value='3';render();document.dispatchEvent(new Event('change'))")
                await asyncio.sleep(.2)
                status = json.loads(panel.pen_input.nativeStatus())
                assert bool(status.get('input')) == (tool in (15, 17)), status
            async def notice(text, button=False):
                await panel.web.evaluate_javascript("(()=>{let el=document.getElementById('previewQaNotice');if(!el){el=document.createElement('nav');el.id='previewQaNotice';el.style='position:fixed;bottom:22px;left:20px;right:20px;z-index:30;background:white;color:black;border:2px solid black;border-radius:12px;padding:16px;font:18px sans-serif;display:block';document.body.append(el)}el.replaceChildren();let label=document.createElement('span');label.textContent=" + json.dumps(text) + ";el.append(label);window.booxQaContinue=false;if(" + str(button).lower() + "){let b=document.createElement('button');b.textContent='Next / Finish';b.style='float:right;margin-left:12px';b.onclick=()=>window.booxQaContinue=true;el.append(b)}})()")
            await wait_for_text(panel.web, 'Native preview check')
            await reopen_saved()
            # Preflight every transition before the user starts writing.
            for index in (1, 0):
                await panel.perform(dict(op='page', index=index))
                assert panel.editor.index == index and len(panel.editor.notebook.pages) == 2
            for index, (tool, color, label) in enumerate(((15, 6, 'Blue Ballpoint'), (15, 7, 'Red Ballpoint'))):
                await wait_for_text(panel.web, 'Native preview check')
                if index:
                    await panel.perform(dict(op='page', index=index))
                    await idle()
                    assert panel.editor.index == index
                await choose(tool, color)
                before = json.loads(panel.pen_input.nativeStatus())
                baseline = {s.id for s in panel.editor.notebook.page(index).strokes}
                await notice(f'{index + 1}/2 · {label}: draw TWO curves, varying pen pressure. Watch the tip and what happens after lifting.')
                stage('draw', number=index + 1, brush=label)
                async def drawn():
                    return sum(s.id not in baseline for s in panel.editor.notebook.page(index).strokes) >= 2
                await wait_for(drawn, 'Waiting for two physical pen strokes')
                await idle()
                status = json.loads(panel.pen_input.nativeStatus())
                strokes = [s for s in panel.editor.notebook.page(index).strokes if s.id not in baseline]
                observed = dict(brush=label, native=status, requested=[tool, color],
                                actual=[[s.tool, s.color] for s in strokes],
                                selected=json.loads(await panel.web.evaluate_javascript('JSON.stringify(chosenInk())')))
                result['stages'].append(observed)
                (output / 'observations.json').write_text(json.dumps(result, indent=2))
                observed['matches_requested'] = all((s.tool, s.color) == (tool, color) for s in strokes)
                assert observed['matches_requested'], observed
                observed['native_strokes'] = status['ends'] - before['ends']
                # Short contacts during canonical-frame reconciliation use the
                # ordinary path and legitimately have no raw callback count.
                observed['fallback_strokes'] = len(strokes) - observed['native_strokes']
                expected = [s.payload() for s in panel.editor.notebook.page(index).strokes]
                await panel.perform(dict(op='save'))
                assert not panel.document.dirty
                (output / 'comparison.rmdoc').write_bytes(source.read_bytes())
                reopened = Notebook.read(source.read_bytes())
                actual = [s.payload() for s in reopened.page(index).strokes]
                assert len(actual) == len(expected)
                for old, new in zip(expected, actual):
                    assert (old['tool'], old['color'], old['scale']) == (new['tool'], new['color'], new['scale'])
                    assert len(old['points']) == len(new['points'])
                    for a, b in zip(old['points'], new['points']):
                        assert abs(a[0] - b[0]) < .001 and abs(a[1] - b[1]) < .001
                        assert abs(a[2] - b[2]) <= 1 / 255 and a[3] == b[3]
                # Replace the live model and WebView from the saved archive,
                # keeping its existing resource binding for subsequent saves.
                await reopen_saved()
                if index:
                    await panel.perform(dict(op='page', index=index))
                await choose(tool, color)
                observed.update(strokes=len(strokes), samples=status['samples'] - before['samples'], save_reopen=True, pressure=[min(p[2] for s in strokes for p in s.points), max(p[2] for s in strokes for p in s.points)])
                await notice(f'{label}: saved and reopened correctly. Inspect the final strokes, then tap Next / Finish.', True)
                stage('inspect-reopened', number=index + 1, brush=label)
                async def continued():
                    return bool(await panel.web.evaluate_javascript('window.booxQaContinue'))
                await wait_for(continued, 'Waiting for review of reopened strokes')
            (output / 'comparison.rmdoc').write_bytes(source.read_bytes())
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if 'panel' in locals() and panel.editor is not None:
                (output / 'comparison.rmdoc').write_bytes(panel.editor.notebook.to_bytes())
            stage('finished', success=result['success'])
        (Path(self.paths.cache) / 'boox-preview-result.json').write_text(json.dumps(result, indent=2))


def main():
    return BooxPreviewProbe('Boox preview check', 'io.github.ispaure.logisticsrawinkqa')
