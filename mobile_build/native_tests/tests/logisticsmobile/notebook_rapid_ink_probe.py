"""Timed pressure traces through the mounted mobile RMDOC editor."""

import asyncio
import json
from math import sin
from pathlib import Path
from time import perf_counter
import traceback

from commonUtils.testing.stages import TestStage

from .notebook_probe import NotebookProbe
from .web_checks import wait_for_text

TEST_STAGE = TestStage.REGRESSION
TITLE = 'Rapid ink QA'
PAGE_COUNTS = (0, 350, 350)
STROKES_PER_BURST = 17
BURSTS_PER_PAGE = 3

WATCH = r'''(()=>{
    $('tool').value = '12';
    $('tool').onchange();
    $('layer').value = state.layers.at(-1)[0];
    mode = 'ink';
    let data;
    window.startRapidInkQA = () => {
        const burst = data = window.rapidInkQA = {input:[], model:[], work:{}, frames:[],
            packets:0, samples:0, highWater:0};
        let previous = performance.now();
        function frame(now) {
            if (burst.done) return;
            burst.frames.push(Math.max(0, now - previous));
            previous = now;
            requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
    };
    const timed = (name, fn) => (...args) => {
        const start = performance.now();
        try { return fn(...args); }
        finally {
            if (data && !data.done) {
                const metric = data.work[name] ??= {calls:0, total:0, max:0};
                const elapsed = performance.now() - start;
                metric.calls++;
                metric.total += elapsed;
                metric.max = Math.max(metric.max, elapsed);
            }
        }
    };
    draw = timed('draw', draw);
    resize = timed('resize', resize);
    flushPreview = timed('preview', flushPreview);
    const deliver = window.logisticsNativePen;
    window.logisticsNativePen = (action, id, samples, w, h) => {
        const at = Date.now();
        deliver(action, id, samples, w, h);
        if (data && !data.done) {
            data.packets++;
            data.samples += samples.length;
        }
        if (data && !data.done && (action === 'down' || action === 'up')) {
            const contact = {action, at, done:Date.now(), accepted:active === id + 100000};
            data.input.push(contact);
            if (action === 'down' && contact.accepted) {
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    contact.paintOpportunity = Date.now();
                }));
            }
        }
    };
    const enqueue = send;
    send = action => {
        if (data && !data.done && action.op === 'stroke')
            data.model.push({points:action.points.length, pressures:action.points.map(p=>p[2]), sent:Date.now()});
        enqueue(action);
        if (data && !data.done) data.highWater = Math.max(data.highWater, queue.length);
    };
    const reply = window.notebookStrokeUpdate;
    window.notebookStrokeUpdate = (...args) => {
        reply(...args);
        if (data && !data.done && active === null) {
            const stroke = data.model.find(value => !value.ack);
            if (stroke) stroke.ack = Date.now();
        }
    };
    window.rapidInkGeometry = () => {
        const page = canvas.getBoundingClientRect(), view = $('viewport').getBoundingClientRect();
        const left = Math.max(page.left, view.left, 0), right = Math.min(page.right, view.right, innerWidth);
        const top = Math.max(page.top, view.top, 0), bottom = Math.min(page.bottom, view.bottom, innerHeight);
        const x = left + (right - left) / 5, y = top + (bottom - top) / 4;
        return JSON.stringify({x,y,w:innerWidth,h:innerHeight,span:Math.min((right-left)/3,100),
            hit:document.elementFromPoint(x,y)===canvas});
    };
    return rapidInkGeometry();
})()'''

IOS_REPLAY = r'''(trace=>{
    const start = Date.now() + 80;
    rapidInkQA.scheduleStart = start;
    for (const [delay,action,x,y,p] of trace) {
        setTimeout(()=>{
            window.logisticsNativePen(['down','up','move'][action],0,[[x,y,p]],innerWidth,innerHeight);
        }, Math.max(0, start + delay - Date.now()));
    }
})'''


def fixture(path):
    from features.notebooks.notebook import Notebook

    book = Notebook.new(TITLE)
    for index, count in enumerate(PAGE_COUNTS):
        if index:
            book.add_page()
        ink = book.page(index)
        ink.add_layer('QA ink')
        layer = ink.layers[-1][0]
        for stroke in range(count):
            x = 70 + stroke % 12 * 110
            y = 100 + stroke % 80 * 18
            points = [[x + point * 2, y + 10 * sin(point / 3), .5 + .3 * sin(point / 4)]
                      for point in range(35)]
            ink.add(points, 12, 0, 2, layer)
    path.write_bytes(book.to_bytes())


def replay(geometry, stroke_count, burst):
    events = []
    elapsed = 0
    for stroke in range(stroke_count):
        count = 96 if stroke == stroke_count - 1 else 7
        x = geometry['x']
        y = geometry['y'] + (stroke + burst * 2) % 12 * 5
        for sample in range(count):
            fraction = sample / (count - 1)
            pressure = .2 + .6 * fraction
            events.append((elapsed, 0 if sample == 0 else 2,
                x + geometry['span'] * fraction, y + 8 * sin(fraction * 9), pressure))
            elapsed += 4
        # Keep pressure stable on the duplicate-position lift so layout
        # realignment cannot turn this fixture's pressure ramp into a zero.
        events.append((elapsed, 1, *events[-1][2:4], .8))
        elapsed += 6
    return events


def signature(book):
    return [
        [(stroke.layer, stroke.tool, stroke.color,
          [(round(x, 3), round(y, 3), round(p, 3), round(w, 3)) for x, y, p, w in stroke.points])
         for stroke in book.page(page).strokes]
        for page in range(len(book.pages))
    ]


def ordered_transport(burst):
    models = burst['model']
    if not burst['drained'] or len(models) != STROKES_PER_BURST:
        return False
    if not all(item['accepted'] for item in burst['input'][::2]):
        return False
    for model, count in zip(models, [7] * (STROKES_PER_BURST - 1) + [96]):
        pressures = model['pressures']
        if model.get('ack') is None or len(pressures) not in (count, count + 1):
            return False
        expected = [.2 + .6 * point / (count - 1) for point in range(count)]
        if len(pressures) > count:
            # A viewport adjustment during the gesture can expose the lift as
            # one more canvas coordinate. It still has the final test pressure.
            expected.append(.8)
        if any(abs(actual - target) > .0001 for actual, target in zip(pressures, expected)):
            return False
    return True


async def timed_bursts(panel, result):
    from features.notebooks.ink import InkPage
    from unittest.mock import patch

    web = panel.web
    android = 'toga_android' in type(web._impl).__module__
    await web.evaluate_javascript(WATCH)
    native = web._impl.native
    if android:
        from java import jclass
        dispatch = jclass('io.github.ispaure.logistics.notebooks.NotebookInputChecks').rapidTrace

    editor = panel.editor
    apply = editor.apply
    checkpoint = editor.checkpoint
    encode = InkPage.to_bytes
    costs = result['host_ms'] = {'apply':[], 'checkpoint':[], 'encode':[]}

    def measured(name, function):
        def measure(*args, **kwargs):
            start = perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                costs[name].append(round((perf_counter() - start) * 1000, 2))
        return measure

    async def collect():
        return json.loads(await web.evaluate_javascript('''JSON.stringify((()=>{
            rapidInkQA.done = true;
            return rapidInkQA;
        })())'''))

    with patch.object(editor, 'apply', measured('apply', apply)), \
            patch.object(editor, 'checkpoint', measured('checkpoint', checkpoint)), \
            patch.object(InkPage, 'to_bytes', measured('encode', encode)):
        count = len(editor.notebook.page(editor.index).strokes)
        for burst in range(BURSTS_PER_PAGE):
            await asyncio.sleep(.8)
            geometry = json.loads(await web.evaluate_javascript('startRapidInkQA();rapidInkGeometry()'))
            assert geometry['hit'], geometry
            trace = replay(geometry, STROKES_PER_BURST, burst)
            contacts = None
            if android:
                contacts = dispatch(native, json.dumps(trace),
                    native.getWidth() / geometry['w'], native.getHeight() / geometry['h'])
            else:
                await web.evaluate_javascript(IOS_REPLAY + '(' + json.dumps(trace) + ')')
            await asyncio.sleep((trace[-1][0] + 150) / 1000)
            drained = False
            for _ in range(900):
                if not panel.busy and await web.evaluate_javascript(
                        f'rapidInkQA.input.length === {2 * STROKES_PER_BURST} && window.notebookIdle()'):
                    drained = True
                    break
                await asyncio.sleep(.05)
            snapshot = await collect()
            if contacts is not None:
                snapshot['native_contacts'] = json.loads(str(contacts.toString()))
            actual = len(editor.notebook.page(editor.index).strokes)
            snapshot.update(before=count, after=actual, scheduled_strokes=STROKES_PER_BURST,
                            scheduled_last_up_ms=trace[-1][0], viewport=geometry, drained=drained)
            result['bursts'].append(snapshot)
            count = actual
    return count


class RapidInkProbe(NotebookProbe):
    async def check(self, app):
        from features.notebooks.mobile.documents import close_notebook, open_notebook
        from features.notebooks.notebook import Notebook

        result = {'success': False, 'pages': [], 'optical_latency_measured': False}
        source = self.storage_root / (TITLE + '.rmdoc')
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            background = getattr(self, 'cloud_startup_task', None)
            if background is not None:
                await background
            source.parent.mkdir(exist_ok=True, parents=True)
            await asyncio.to_thread(fixture, source)
            assert await open_notebook(app, path=source)
            panel = app.notebook_panel
            await wait_for_text(panel.web, TITLE)
            assert await panel.web.evaluate_javascript('state.native_pen')
            result['compiled_apple_transport_mounted'] = panel.native_transport
            if 'toga_iOS' in type(panel.web._impl).__module__:
                assert panel.native_transport
            for index, existing in enumerate(PAGE_COUNTS):
                if index:
                    await panel.web.evaluate_javascript(f"send({{op:'page',index:{index}}})")
                    await panel.flush_input()
                assert panel.editor.index == index
                if index:
                    panel.mount_canvas()
                    await wait_for_text(panel.web, TITLE)
                page = {'index': index, 'bursts': []}
                result['pages'].append(page)
                count = await timed_bursts(panel, page)
                ink = panel.editor.notebook.page(index)
                strokes = ink.strokes[existing:]
                page['count_correct'] = count - existing == STROKES_PER_BURST * BURSTS_PER_PAGE
                page['ordered_transport'] = all(map(ordered_transport, page['bursts']))
                page['layer_correct'] = all(stroke.layer == ink.layers[-1][0] for stroke in strokes)
                page['saved_pressure'] = bool(strokes) and all(
                    abs(stroke.points[0][2] - .2) <= .01 and abs(stroke.points[-1][2] - .8) <= .01
                    for stroke in strokes)
                page['saved_points'] = [len(stroke.points) for stroke in strokes]
                if strokes:
                    await panel.web.evaluate_javascript("$('undo').click()")
                    await panel.flush_input()
                    page['undo'] = len(panel.editor.notebook.page(index).strokes) == count - 1
                    await panel.web.evaluate_javascript("$('redo').click()")
                    await panel.flush_input()
                    page['redo'] = len(panel.editor.notebook.page(index).strokes) == count
            expected = signature(panel.editor.notebook)
            layer = panel.editor.notebook.page(panel.editor.index).layers[-1][0]
            await panel.web.evaluate_javascript(
                "send({op:'layer-visible',visible:false,layer:" + json.dumps(layer) + '})')
            await panel.flush_input()
            result['layer_visibility'] = not panel.editor.notebook.page(panel.editor.index).layers[-1][2]
            result['verified_save'] = await panel.save_from_view()
            saved = Notebook.read(source.read_bytes())
            result['reopened_source_matches'] = signature(saved) == expected and not saved.page(2).layers[-1][2]
            assert close_notebook(app, panel.session.id, 'keep')
            assert await open_notebook(app, path=source)
            reopened = app.notebook_panel
            await wait_for_text(reopened.web, TITLE)
            result['reopened_editor_matches'] = reopened is not panel and signature(reopened.editor.notebook) == expected
            pages_verified = all(
                all(page.get(key) for key in ('count_correct', 'ordered_transport', 'layer_correct',
                                             'saved_pressure', 'undo', 'redo'))
                for page in result['pages'])
            result['success'] = pages_verified and all(result[key] for key in (
                'layer_visibility', 'verified_save', 'reopened_source_matches', 'reopened_editor_matches'))
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-rapid-ink-result.json').write_text(json.dumps(result))


def main():
    return RapidInkProbe('Rapid notebook ink QA', 'io.github.ispaure.logisticsnotebookqa')
