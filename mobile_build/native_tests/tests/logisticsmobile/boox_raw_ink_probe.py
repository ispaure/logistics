"""Physical Boox comparison; SDK preview is QA-only and saved ink stays canonical."""
import asyncio
import json
from pathlib import Path
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text
from .fixtures import capture_window


class BooxRawInkProbe(NotebookProbe):
    async def check(self, app):
        output = Path(self.paths.cache) / 'boox-raw-ink'
        output.mkdir(exist_ok=True)
        result = dict(success=False, optical_latency_measured=False, production_enabled=False)
        raw = None
        def stage(name, **values):
            result['last_stage'] = name
            (output / 'stage.json').write_text(json.dumps(dict(stage=name, **values), indent=2))
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            from features.notebooks.notebook import Notebook
            from features.notebooks.mobile.documents import open_notebook
            source = self.private_root / 'raw-comparison.rmdoc'
            source.write_bytes(Notebook.new('Boox handwriting comparison').to_bytes())
            assert await open_notebook(self, path=source)
            panel = self.notebook_panel
            await wait_for_text(panel.web, 'Boox handwriting comparison')
            await asyncio.sleep(.4)
            panel.pen_input.disableNativePreview()
            await panel.web.evaluate_javascript("$('tool').value='15';$('tool').onchange();$('width').value='3'")
            from java import jclass
            raw = jclass('io.github.ispaure.logistics.notebooks.BooxRawInk')(panel.web._impl.native)
            result['initialization'] = json.loads(raw.status())
            assert result['initialization']['created'], result['initialization']
            async def idle():
                for _ in range(300):
                    js = json.loads(await panel.web.evaluate_javascript('JSON.stringify({busy,queue:queue.length})'))
                    if not panel.busy and not js['busy'] and not js['queue']:
                        return
                    await asyncio.sleep(.05)
                raise AssertionError('Canonical stroke/save bridge did not finish')
            async def notice(text):
                await panel.web.evaluate_javascript("(()=>{let el=document.getElementById('rawQaNotice');if(!el){el=document.createElement('div');el.id='rawQaNotice';el.style='position:fixed;bottom:20px;left:20px;right:20px;z-index:20;background:white;color:black;border:2px solid black;border-radius:12px;padding:16px;text-align:center;pointer-events:none;font:18px sans-serif';document.body.append(el)}el.textContent=" + json.dumps(text) + "})()")
            async def drawing(count):
                for _ in range(1800):
                    if len(panel.editor.notebook.page(panel.editor.index).strokes) >= count:
                        await idle()
                        return
                    await asyncio.sleep(.2)
                raise TimeoutError('No completed physical strokes received before the QA deadline')
            await notice('1 / 2 · Current renderer. Draw TWO long curves with varying pen pressure. Then lift the pen.')
            stage('baseline-ready', sdk=result['initialization'])
            await drawing(2)
            result['baseline'] = dict(strokes=len(panel.editor.notebook.page(0).strokes), source='Android MotionEvent')
            await panel.perform(dict(op='save'))
            await capture_window(self, output / 'baseline.png')
            await panel.web.evaluate_javascript("send({op:'add-page'})")
            await idle()
            geometry = json.loads(await panel.web.evaluate_javascript('JSON.stringify({r:canvas.getBoundingClientRect().toJSON(),w:innerWidth,h:innerHeight,scale:canvas.getBoundingClientRect().width/state.width})'))
            native = panel.web._impl.native
            sx, sy = native.getWidth() / geometry['w'], native.getHeight() / geometry['h']
            rect = geometry['r']
            raw.configure(15, -16777216, 4 * geometry['scale'] * sx, int(max(0, rect['left']) * sx),
                          int(max(80, rect['top']) * sy), int(min(geometry['w'], rect['right']) * sx),
                          int(min(geometry['h'] - 100, rect['bottom']) * sy))
            # Only the SDK callbacks own raw-trial ink. Keep the old JS contract
            # but stop its competing Android event listener for this trial.
            panel.pen_input.close()
            if panel.boox_refresh is not None:
                panel.boox_refresh.close()
            await notice('2 / 2 · Boox native preview. Draw TWO long curves with varying pressure in the middle of the page.')
            raw.enable(True)
            stage('raw-ready', sdk=json.loads(raw.status()))
            await drawing(2)
            raw.enable(False)
            await asyncio.sleep(.3)
            result['raw'] = json.loads(raw.status())
            strokes = panel.editor.notebook.page(1).strokes
            assert result['raw']['ends'] == len(strokes), (result['raw'], len(strokes))
            assert result['raw']['samples'] > 2 and result['raw']['rejected'] == 0, result['raw']
            assert all(s.tool == 15 for s in strokes)
            result['canonical_pressure'] = dict(min=min(p[2] for s in strokes for p in s.points),
                max=max(p[2] for s in strokes for p in s.points),
                min_width=min(p[3] for s in strokes for p in s.points), max_width=max(p[3] for s in strokes for p in s.points))
            await panel.perform(dict(op='save'))
            assert not panel.document.dirty
            reopened = Notebook.read(source.read_bytes())
            restored = reopened.page(1).strokes
            assert len(restored) == len(strokes)
            max_coordinate_error = max_pressure_error = 0
            for expected, actual in zip(strokes, restored):
                assert (expected.tool, expected.color, expected.scale) == (actual.tool, actual.color, actual.scale)
                assert len(expected.points) == len(actual.points)
                for before, after in zip(expected.points, actual.points):
                    max_coordinate_error = max(max_coordinate_error, abs(before[0] - after[0]), abs(before[1] - after[1]))
                    max_pressure_error = max(max_pressure_error, abs(before[2] - after[2]))
                    assert before[3] == after[3]
            assert max_coordinate_error < .001 and max_pressure_error <= 1 / 255
            result['codec_precision'] = dict(max_coordinate_error=max_coordinate_error, max_pressure_error=max_pressure_error)
            await notice('Native trial saved and reopened successfully. QA is finishing; your main app is unchanged.')
            await capture_window(self, output / 'raw-final.png')
            result.update(success=True, save_reopen=True, no_duplicate_strokes=True)
            (output / 'comparison.rmdoc').write_bytes(source.read_bytes())
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if raw is not None:
                raw.close()
                result['closed'] = json.loads(raw.status())
            (output / 'stage.json').write_text(json.dumps(dict(stage='finished', success=result['success']), indent=2))
        (Path(self.paths.cache) / 'boox-raw-ink-result.json').write_text(json.dumps(result, indent=2))


def main():
    return BooxRawInkProbe('Boox native ink QA', 'io.github.ispaure.logisticsrawinkqa')
