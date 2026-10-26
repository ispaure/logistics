"""Physical Boox software-timing probe; host injects stylus swipes per ready file.

The isolated build supplies canvas_baseline.py from a recorded source revision.
Measurements end at JavaScript/animation callbacks, not at visible E Ink pixels.
"""
import asyncio
import json
import math
from pathlib import Path
import time
import traceback

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text

BUNDLE = 'io.github.ispaure.logisticsbooxinkqa'

INSTRUMENT = r"""(()=>{
    window.inkTiming={delivery:[],draw:[],animation:[],types:[],up:false,saved:false};
    const move=canvas.onpointermove,up=canvas.onpointerup,update=window.notebookUpdate;
    canvas.onpointermove=e=>{
        const begin=performance.now();move(e);
        inkTiming.delivery.push(begin-e.timeStamp);inkTiming.draw.push(performance.now()-begin);
        inkTiming.types.push(e.pointerType);
        requestAnimationFrame(()=>inkTiming.animation.push(performance.now()-e.timeStamp));
    };
    canvas.onpointerup=e=>{inkTiming.end=performance.now();up(e);inkTiming.up=true};
    window.notebookUpdate=(next,error)=>{update(next,error);inkTiming.save=performance.now()-inkTiming.end;inkTiming.saved=true;inkTiming.error=error};
    return JSON.stringify({rect:canvas.getBoundingClientRect().toJSON(),width:innerWidth,height:innerHeight});
})()"""


class BooxDrawingProbe(NotebookProbe):
    async def check(self, app):
        from java import jarray, jint, jclass
        from features.notebooks.mobile.documents import open_notebook
        from features.notebooks.notebook import Notebook
        from .canvas_baseline import editor_html as baseline_html
        from features.notebooks.canvas import editor_html
        output = Path(self.paths.cache)
        control_path = output / 'boox-ink-control.json'
        control = json.loads(control_path.read_text()) if control_path.exists() else {}
        result = dict(success=False, optical_latency_measured=False,
                      input_source=control.get('input_source', 'ADB stylus injection'), trials=[])
        panel = None
        try:
            assert 'onyx' in str(jclass('android.os.Build').MANUFACTURER).lower()
            assert await open_notebook(app)
            panel = app.notebook_panel
            epd = jclass('com.onyx.android.sdk.api.device.epd.EpdController')
            result['model'] = str(jclass('android.os.Build').MODEL)
            ordinal = 0
            for count in control.get('pages', [0, 500]):
                for repeat in range(control.get('repeats', 3)):
                    # Interleave configurations to reduce warm-up/temperature bias.
                    for mode in control.get('modes', ['baseline', 'incremental', 'boox']):
                        book = Notebook.new('Synthetic drawing latency QA')
                        ink = book.page(0)
                        for index in range(count):
                            x, y = 25 + index % 20 * 65, 25 + index // 20 * 22
                            ink.add([[x + point, y + math.sin(point / 3) * 4, .6]
                                     for point in range(24)], tool=17, width=2)
                        assert await panel.load(lambda: book)
                        if mode != 'boox' and panel.boox_refresh is not None:
                            panel.boox_refresh.close()
                            panel.boox_refresh = None
                        html = baseline_html if mode == 'baseline' else editor_html
                        panel.web.set_content('https://logistics.invalid/notebooks/', html(panel.editor.state(), panel.bridge.url))
                        await wait_for_text(panel.web, 'Synthetic drawing latency QA')
                        await asyncio.sleep(.35)
                        geometry = json.loads(await panel.web.evaluate_javascript(INSTRUMENT))
                        native = panel.web._impl.native
                        origin = jarray(jint)(2)
                        native.getLocationOnScreen(origin)
                        ratio = native.getWidth() / geometry['width']
                        rect = geometry['rect']
                        left, top = rect['x'], rect['y']
                        # Keep the test stroke inside the visible canvas on a portrait tablet.
                        y = min(top + 260, geometry['height'] - 90)
                        points = [round(origin[0] + (left + 40) * ratio), round(origin[1] + y * ratio),
                                  round(origin[0] + min(left + rect['width'] - 40, left + 550) * ratio),
                                  round(origin[1] + (y + 90) * ratio)]
                        before = str(epd.getViewDefaultUpdateMode(native))
                        ordinal += 1
                        ready = dict(ordinal=ordinal, mode=mode, strokes=count, repeat=repeat, points=points)
                        (output / 'boox-ink-ready.json').write_text(json.dumps(ready))
                        active_modes = set()
                        active_seen = False
                        deadline = time.monotonic() + 35
                        while time.monotonic() < deadline:
                            controller = panel.boox_refresh
                            if controller is not None and not active_seen and controller.isFastModeActive():
                                active_seen = True
                                active_modes.add(str(epd.getViewDefaultUpdateMode(native)))
                            done = await panel.web.evaluate_javascript('Boolean(inkTiming.saved)')
                            if done:
                                break
                            await asyncio.sleep(.025)
                        else:
                            raise TimeoutError('No saved stylus stroke for ' + repr(ready))
                        await asyncio.sleep(.3)
                        metrics = json.loads(await panel.web.evaluate_javascript('JSON.stringify(inkTiming)'))
                        assert len(panel.editor.notebook.page(0).strokes) == count + 1
                        assert metrics['delivery'] and set(metrics['types']) == {'pen'}, metrics
                        assert not metrics.get('error'), metrics
                        trial = dict(**ready, metrics=metrics, previous_mode=before,
                                     active_modes=sorted(active_modes), fast_mode_seen=active_seen,
                                     fast_mode_after_up=bool(panel.boox_refresh.isFastModeActive()) if panel.boox_refresh is not None else None,
                                     restored_mode=str(epd.getViewDefaultUpdateMode(native)),
                                     refresh_supported=bool(panel.boox_refresh.isSupported()) if panel.boox_refresh is not None else None)
                        if control.get('diagnostics') and panel.boox_refresh is not None:
                            panel.boox_refresh.onWindowFocusChanged(False)
                            trial['after_forced_restore'] = str(epd.getViewDefaultUpdateMode(native))
                            epd.setViewDefaultUpdateMode(native, jclass('com.onyx.android.sdk.api.device.epd.UpdateMode').GC)
                            trial['after_direct_gc'] = str(epd.getViewDefaultUpdateMode(native))
                            epd.invalidate(native, jclass('com.onyx.android.sdk.api.device.epd.UpdateMode').GU)
                            trial['after_gu_invalidate'] = str(epd.getViewDefaultUpdateMode(native))
                        result['trials'].append(trial)
                        (output / 'boox-ink-progress.json').write_text(json.dumps(result))
                        if mode == 'boox':
                            assert trial['refresh_supported'] and trial['fast_mode_seen'], trial
                            assert trial['active_modes'] == ['DU'], trial
                            assert not trial['fast_mode_after_up'], trial
                            assert trial['restored_mode'] == before, trial
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        finally:
            if panel is not None:
                panel.dispose()
            (output / 'boox-ink-result.json').write_text(json.dumps(result, indent=2))


def main():
    return BooxDrawingProbe('Boox drawing QA', BUNDLE)
