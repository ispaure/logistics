"""Native desktop burst, history, publication failure, recovery and zoom acceptance.

Uses synthetic notebooks and manager scratch; saves only concise evidence outside it.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import platform
import os
import time
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from PySide6.QtTest import QTest
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import javascript, wait_until
from features.notebooks.notebook import Notebook
from features.notebooks.storage import NotebookDocument
from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
from features.notebooks.ui.menus import NotebookMenus


def scheduler_sample():
    """Retain optional guest scheduling evidence outside timed input delivery."""
    sample = dict(monotonic_seconds=time.monotonic(), process_cpu_seconds=time.process_time())
    if platform.system() == 'Linux':
        sources = {'cpu': '/proc/stat', 'load': '/proc/loadavg',
                   'cpu_pressure': '/proc/pressure/cpu', 'memory_pressure': '/proc/pressure/memory'}
        for name, filename in sources.items():
            try:
                text = Path(filename).read_text()
                sample[name] = text.splitlines()[0] if name == 'cpu' else text.strip()
            except OSError as error:
                sample[name] = dict(unavailable=str(error))
    return sample


def windows_foreground():
    """Qt's active widget is not proof of Windows' actual foreground process."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    window = user32.GetForegroundWindow()
    process = wintypes.DWORD()
    user32.GetWindowThreadProcessId(window, ctypes.byref(process))
    return dict(window=window, process=process.value)


class Probe:
    def __init__(self, root):
        self.window_states = []
        self.window = NotebookWindow()
        self.panel = NotebookWorkspace(self.window, root=root / 'recovery', library=False)
        self.window.setCentralWidget(self.panel)
        self.window.notebook_menus = NotebookMenus(self.window)
        self.window.resize(1100, 900)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.panel.open_resource(NotebookDocument(Notebook.new('Desktop acceptance')))
        self.ready()

    def ready(self):
        # This synchronous probe does not run QApplication.exec(). Retire the
        # previous WebView as the production event loop normally would, before
        # timing a fresh renderer with large canvas buffers.
        qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        self.wait(lambda: self.js("typeof window.notebookUI==='function'"), 'canvas loading')
        # Chromium can finish executing the page before Windows creates its
        # native input child. Send mouse events to that child only once exposed.
        self.wait(lambda: self.panel.web.focusProxy() is not None and self.panel.web.isVisible(),
                  'native canvas input widget')
        self.panel.web.setFocus()
        if platform.system() == 'Windows':
            self.window.raise_()
            self.window.activateWindow()
            assert QTest.qWaitForWindowActive(self.window, 3000), 'Native Windows editor did not become active'
        self.js("(()=>{window.qaPaintReady=false;window.qaPointerUps=0;canvas.addEventListener('pointerup',()=>qaPointerUps++);requestAnimationFrame(()=>requestAnimationFrame(()=>{qaPaintReady=true}));return true})()")
        self.wait(lambda: self.js('window.qaPaintReady'), 'canvas presentation')
        self.idle()
        self.window_states.append(dict(active=self.window.isActiveWindow(), process=os.getpid(),
            native_foreground=windows_foreground() if platform.system() == 'Windows' else None,
            browser=self.js('({visibility:document.visibilityState,focused:document.hasFocus(),dpr:devicePixelRatio,canvas:[canvas.width,canvas.height],context:ctx.getContextAttributes()})')))

    def wait(self, predicate, label, timeout=15):
        wait_until(predicate, label, timeout)

    def js(self, expression):
        result = json.loads(javascript(self.panel.web, 'JSON.stringify((()=>{try{return {ok:true,value:(' + expression
            + ')}}catch(error){return {ok:false,error:String(error)}}})())'))
        assert result['ok'], result
        return result.get('value')

    def idle(self, timeout=15, *, layout=True):
        self.wait(lambda: not self.panel.busy and self.js('!busy&&!queue.length&&active===null'), 'bridge idle', timeout=timeout)
        if layout:
            QTest.qWait(35)  # Qt/WebEngine layout can outlive browser frame callbacks.

    def action(self, op, **fields):
        self.panel.request_command(dict(op=op, **fields))
        self.idle(timeout=60 if op in ('save', 'save-as', 'export') else 15)

    def stroke(self, row=0, samples=8, pause_ms=0, pace_ms=0, while_down=None):
        if platform.system() == 'Windows':
            foreground = windows_foreground()
            assert foreground['process'] == os.getpid(), ('Editor is not the native foreground window', foreground)
        box = self.js('canvas.getBoundingClientRect().toJSON()')
        releases = self.js('qaPointerUps')
        target = self.panel.web.focusProxy() or self.panel.web
        x, y = int(box['left'] + box['width'] * .1), int(box['top'] + box['height'] * (.1 + (row % 35) * .02))
        start = time.monotonic()
        QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x, y))
        last_point = qt.QPoint(x, y)
        for index in range(samples):
            if pause_ms and index == samples // 2:
                if while_down is not None:
                    while_down()
                QTest.qWait(pause_ms)
            last_point = qt.QPoint(x + int((index % 60) * max(1, box['width'] / 180)), y + index % 4)
            QTest.mouseMove(target, last_point, delay=1)
            if pace_ms:
                QTest.qWait(pace_ms)
        # Sample count is not a coordinate: releasing at x + 2 * samples put
        # the 500-sample gesture outside the Windows native input widget.
        assert target.rect().contains(last_point), 'Probe gesture leaves native input widget'
        QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=last_point)
        # Input and runJavaScript use separate Chromium channels on Windows.
        # A JS idle query can overtake the mouse release; observe its delivery
        # before checking bridge idleness or sending the next gesture.
        self.wait(lambda: self.js('qaPointerUps') == releases + 1, 'native pointer release')
        return (time.monotonic() - start) * 1000

    def count(self):
        return len(self.panel.editor.notebook.page(self.panel.editor.index).strokes)

    def raster(self):
        return hashlib.sha256(self.js('canvas.toDataURL()').encode()).hexdigest()

    def close(self):
        # A failed assertion must not destroy an asynchronous writer or remove
        # its scratch file while publication is still running.
        self.wait(lambda: not self.panel.busy, 'pending publication before teardown', timeout=120)
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
            self.window.close()
        QTest.qWait(50)


def source_hashes():
    owner = Path(__file__).resolve().parents[2] / 'features' / 'notebooks'
    return {name: hashlib.sha256((owner / name).read_bytes()).hexdigest()
            for name in ('canvas.py', 'assets/drawing.js', 'assets/input.js', 'assets/viewport.js',
                         'assets/queue.js', 'assets/desktop.js', 'ui/workspace.py')}


def main(output, *, latency_mode='enforce'):
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(status='running', platform=platform.platform(), source_hashes=source_hashes(), checks={}, timings_ms={})
    with scratch() as root:
        probe = Probe(root)
        report['window_states'] = probe.window_states
        try:
            tools = probe.js('Object.values(state.tools)')
            for index, tool in enumerate(tools):
                probe.js("(()=>{$('tool').value=" + str(tool) + ";$('tool').onchange();$('color').value='6';return true})()")
                probe.stroke(index)
                probe.idle()
                assert probe.count() == index + 1, (tool, probe.count())
            report['checks']['all_nine_brushes_native_mouse'] = True
            print('Nine native brush strokes passed', flush=True)
            first = probe.panel.editor.notebook.page(0).strokes[0]
            point = list(first.points[0])
            def edit_first(mode, dx=0, dy=0, eraser_kind='whole'):
                probe.panel.request_ui(mode)
                probe.idle()
                if mode == 'erase':
                    probe.wait(lambda: probe.js('eraserDialog.open'), 'eraser settings')
                    probe.js("(()=>{$(" + json.dumps("eraserWhole" if eraser_kind == "whole" else "eraserPartial") + ").click();$('closeEraser').click();return true})()")
                box = probe.js('canvas.getBoundingClientRect().toJSON()')
                x = int(box['left'] + point[0] / 1404 * box['width'])
                y = int(box['top'] + point[1] / 1872 * box['height'])
                target = probe.panel.web.focusProxy() or probe.panel.web
                releases = probe.js('qaPointerUps')
                QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x, y))
                QTest.mouseMove(target, qt.QPoint(x + dx, y + dy), delay=1)
                QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x + dx, y + dy))
                probe.wait(lambda: probe.js('qaPointerUps') == releases + 1, 'native edit pointer release')
                probe.idle()
            original_points = len(first.points)
            edit_first('erase', eraser_kind='partial')
            remaining = next(stroke for stroke in probe.panel.editor.notebook.page(0).strokes if stroke.id == first.id)
            assert remaining.points[0] != point and len(remaining.points) <= original_points
            probe.action('undo')
            assert probe.panel.editor.notebook.page(0).strokes[0].points[0] == point
            report['checks']['native_partial_erase_and_undo'] = True
            edit_first('erase')
            assert probe.count() < len(tools)
            probe.action('undo')
            assert probe.count() == len(tools)
            edit_first('select', 12, 8)
            moved = next(stroke for stroke in probe.panel.editor.notebook.page(0).strokes if stroke.id == first.id)
            assert moved.points[0][0] != point[0] and moved.points[0][1] != point[1]
            probe.action('undo')
            restored = next(stroke for stroke in probe.panel.editor.notebook.page(0).strokes if stroke.id == first.id)
            assert restored.points[0] == point
            probe.panel.request_ui('ink')
            probe.idle()
            report['checks']['native_whole_stroke_erase_select_move_and_undo'] = True

            # Delay only host dispatch, emulating storage/bridge latency. Every
            # rapid gesture must remain visible and eventually become durable.
            delivered = probe.panel.deliver
            def delayed(page, action):
                qt.QTimer.singleShot(120, lambda: delivered(page, action))
            probe.panel.deliver = delayed
            before = probe.count()
            durations = [probe.stroke(index + 10, samples=2) for index in range(12)]
            probe.idle()
            probe.panel.deliver = delivered
            assert probe.count() == before + 12, ('Dropped rapid strokes', before, probe.count())
            report['checks']['twelve_rapid_strokes_with_120ms_ack_delay'] = True
            report['timings_ms']['burst_mouse_gestures'] = durations
            print('Delayed-ack rapid drawing passed', flush=True)

            probe.js('(()=>{draw();return true})()')
            raster = probe.raster()
            for _ in range(10):
                probe.action('undo')
            assert probe.count() == before + 2
            for _ in range(10):
                probe.action('redo')
            assert probe.count() == before + 12 and probe.raster() == raster
            report['checks']['ten_undo_redo_cycles_and_identical_raster'] = True

            provider = LocalFiles(root)
            def save_as(name):
                with patch('services.documents.ui.editors.choose_editor_resource',
                           return_value=ResourceChoice(provider, name)):
                    probe.action('save-as')
                assert not probe.panel.document.dirty
                saved = Notebook.read((root / name).read_bytes())
                assert len(saved.page(0).strokes) == probe.count()
            save_as('first.rmdoc')
            delivered = probe.panel.deliver
            probe.panel.deliver = lambda page, action: qt.QTimer.singleShot(120, lambda: delivered(page, action))
            previous_count = probe.count()
            for row in range(5):
                probe.stroke(22 + row, samples=2)
            probe.action('save')  # Must follow all pending ink, not snapshot early.
            probe.panel.deliver = delivered
            assert probe.count() == previous_count + 5
            assert len(Notebook.read((root / 'first.rmdoc').read_bytes()).page(0).strokes) == probe.count()
            report['checks']['save_waits_for_all_pending_strokes'] = True
            original = (root / 'first.rmdoc').read_bytes()
            probe.stroke(25)
            probe.idle()
            with patch.object(probe.panel.document.resource, 'save', side_effect=OSError('Synthetic full disk')):
                probe.action('save')
            assert probe.panel.document.dirty and (root / 'first.rmdoc').read_bytes() == original, dict(dirty=probe.panel.document.dirty, strokes=probe.count(), bytes_changed=(root / 'first.rmdoc').read_bytes()!=original, status=probe.js("$('status').textContent"))
            assert 'Synthetic full disk' in probe.js("$('status').textContent")
            probe.action('save')
            assert not probe.panel.document.dirty
            assert len(Notebook.read((root / 'first.rmdoc').read_bytes()).page(0).strokes) == probe.count()
            report['checks']['real_save_failure_preserves_source_and_retry'] = True
            exported = root / 'export.rmdoc'
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(exported), '')):
                probe.action('export')
            assert len(Notebook.read(exported.read_bytes()).page(0).strokes) == probe.count()
            exported_before = exported.read_bytes()
            original_document = probe.panel.document
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(exported), '')), \
                    patch('features.notebooks.ui.workspace.export_local_document', side_effect=PermissionError('Synthetic export denied')):
                probe.action('export')
            assert exported.read_bytes() == exported_before and probe.panel.document is original_document
            assert 'Synthetic export denied' in probe.js("$('status').textContent")
            # The worker encodes while native timers still run; cancellation
            # must prevent publication after that encoding finishes.
            from threading import Event
            release = Event()
            encode = probe.panel.editor.notebook.to_bytes
            def slow_encode():
                assert release.wait(3), 'Native UI did not run during export'
                return encode()
            cancelled_export = root / 'cancelled-export.rmdoc'
            with patch.object(qt.QFileDialog, 'getSaveFileName', return_value=(str(cancelled_export), '')), \
                    patch.object(probe.panel.editor.notebook, 'to_bytes', slow_encode):
                probe.panel.request_command(dict(op='export'))
                probe.wait(lambda: probe.panel.busy, 'export worker startup')
                qt.QTimer.singleShot(100, lambda: (probe.panel.operation.request_cancel(), release.set()))
                probe.idle()
            assert not cancelled_export.exists() and probe.panel.document is original_document
            probe.stroke(25)
            probe.idle()
            report['checks']['export_worker_responsive_cancel_failure_copy_and_continue'] = True
            with patch('services.documents.ui.editors.choose_editor_resource', return_value=None):
                probe.action('save-as')
            probe.stroke(26)
            probe.idle()
            assert probe.panel.document.dirty
            with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Cancel):
                assert not probe.window.close()
            probe.stroke(27)
            probe.idle()
            save_as('retarget.rmdoc')
            assert probe.panel.document.resource.path == 'retarget.rmdoc'
            report['checks']['cancel_save_as_cancel_close_continue_drawing_retarget'] = True
            print('Save, failure, retry, cancel and retarget passed', flush=True)

            probe.panel.request_ui('zoom', '1')
            probe.wait(lambda: probe.js("$('zoom').value") == '1', 'baseline zoom')
            probe.idle()
            # Zoom redraws native-decoded model ink. Compare that canonical raster
            # on both sides; live-preview parity has its own brush pixel checks.
            probe.js('(()=>{draw();return true})()')
            raster = probe.raster()
            zoom_baseline = probe.js('({pixels:canvas.toDataURL(),width:canvas.width,height:canvas.height})')
            for zoom in ['fit', '1', '1.5', '2', 'page']:
                probe.panel.request_ui('zoom', zoom)
                probe.wait(lambda: probe.js("$('zoom').value") == zoom, 'zoom ' + zoom)
            probe.panel.request_ui('zoom', '1')
            probe.wait(lambda: probe.js("$('zoom').value") == '1', 'restored zoom')
            probe.idle()
            if probe.raster() != raster:
                zoom_actual = probe.js('({pixels:canvas.toDataURL(),width:canvas.width,height:canvas.height})')
                for name, value in [('before', zoom_baseline), ('after', zoom_actual)]:
                    (output / ('zoom-' + name + '.png')).write_bytes(base64.b64decode(value.pop('pixels').split(',', 1)[1]))
                report['zoom_raster'] = dict(before=zoom_baseline, after=zoom_actual)
            assert probe.raster() == raster
            probe.panel.request_ui('zoom', 'page')
            probe.idle()
            count = probe.count()
            probe.action('add-page')
            assert probe.count() == 0
            probe.stroke()
            probe.idle()
            probe.action('page', index=0)
            assert probe.count() == count
            probe.action('save')
            saved = Notebook.read((root / 'retarget.rmdoc').read_bytes())
            assert len(saved.pages) == 2 and len(saved.page(0).strokes) == count
            assert len(saved.page(1).strokes) == 1
            (output / 'verified.rmdoc').write_bytes(saved.to_bytes())
            report['checks']['zoom_redraw_page_navigation_and_saved_pages'] = True

            probe.panel.dispose()
            probe.panel.open_resource(NotebookDocument(saved))
            probe.ready()
            assert probe.count() == count
            probe.stroke(28)
            probe.idle()
            assert probe.count() == count + 1, dict(expected=count + 1, actual=probe.count(),
                canvas=probe.js('({busy,queue:queue.length,active,mode,warning:state.warning,read_only:state.read_only})'))
            report['checks']['reopened_archive_remains_editable'] = True
            probe.js("(()=>{window.qaSmallGap=0;window.qaSmallFrames=0;window.qaSmallPrevious=performance.now();window.qaSmallLoop=true;function frame(now){qaSmallFrames++;qaSmallGap=Math.max(qaSmallGap,now-qaSmallPrevious);qaSmallPrevious=now;if(qaSmallLoop)requestAnimationFrame(frame)}requestAnimationFrame(frame);$('tool').value='23';$('tool').onchange();return true})()")
            probe.stroke(2, samples=200, pace_ms=5)
            probe.idle()
            report['small_page_metrics'] = probe.js('({frames:qaSmallFrames,max_frame_gap:qaSmallGap})')
            probe.js('qaSmallLoop=false')
            # A substantial page catches accidental whole-scene replay in the
            # pointer path, which small synthetic documents can conceal.
            large = Notebook.new('Large-page responsiveness')
            ink = large.page(0)
            for index in range(1000):
                ink.add([[30 + point * 4, 25 + index % 1750 + point % 3, .5] for point in range(40)],
                        tool=17, color=6, width=2)
            probe.panel.dispose()
            probe.panel.open_resource(NotebookDocument(large))
            probe.ready()
            probe.js("""(()=>{window.qaCosts={};window.qaLongTasks=[];
                function measured(name,fn){return function(...args){let t=performance.now();try{return fn.apply(this,args)}finally{let ms=performance.now()-t,row=qaCosts[name]||(qaCosts[name]={calls:0,total:0,max:0});row.calls++;row.total+=ms;row.max=Math.max(row.max,ms)}}}
                preview=measured('preview',preview);line=measured('line',line);clearDraft=measured('clearDraft',clearDraft);sample=measured('sample',sample);finish=measured('finish',finish);
                coord=measured('coord',coord);flushPreview=measured('flushPreview',flushPreview);commitDraft=measured('commitDraft',commitDraft);
                canvas.onpointermove=measured('pointermove',canvas.onpointermove);
                if(PerformanceObserver.supportedEntryTypes.includes('longtask'))new PerformanceObserver(list=>{for(let e of list.getEntries())qaLongTasks.push({start:e.startTime,duration:e.duration,name:e.name,attribution:Array.from(e.attribution||[],a=>({name:a.name,containerType:a.containerType}))})}).observe({entryTypes:['longtask']});return true})()""")
            host_costs = []
            perform = probe.panel.perform
            def timed_perform(action):
                started = time.monotonic()
                try:
                    return perform(action)
                finally:
                    host_costs.append(dict(op=action['op'], ms=(time.monotonic() - started) * 1000))
            probe.panel.perform = timed_perform
            probe.js("(()=>{window.qaDraws=0;window.qaFrames=0;window.qaGap=0;window.qaGapEvents=[];window.qaDeferred=0;window.qaFramePrevious=performance.now();let base=draw;draw=function(){qaDraws++;return base()};let ack=window.notebookStrokeUpdate;window.notebookStrokeUpdate=function(...args){if(active!==null)qaDeferred++;return ack(...args)};window.qaFrameLoop=true;function frame(now){qaFrames++;let gap=now-qaFramePrevious;qaGap=Math.max(qaGap,gap);if(gap>=80&&qaGapEvents.length<100)qaGapEvents.push({start:qaFramePrevious,end:now,duration:gap,active:active!==null,busy,queued:queue.length,visibility:document.visibilityState});qaFramePrevious=now;if(qaFrameLoop)requestAnimationFrame(frame)}requestAnimationFrame(frame);$('tool').value='23';$('tool').onchange();return true})()")
            delivered = probe.panel.deliver
            pending_commands = []
            probe.panel.deliver = lambda page, action: pending_commands.append((page, action))
            probe.stroke(3, samples=2)
            probe.wait(lambda: bool(pending_commands), 'held stroke command')
            def acknowledge_while_drawing():
                probe.wait(lambda: probe.js('active!==null'), 'active native gesture')
                while pending_commands:
                    delivered(*pending_commands.pop(0))
                probe.wait(lambda: probe.js('qaDeferred>0'), 'mid-gesture acknowledgement')
            duration = probe.stroke(4, samples=500, pause_ms=220, while_down=acknowledge_while_drawing)
            probe.panel.deliver = delivered
            while pending_commands:
                delivered(*pending_commands.pop(0))
            probe.idle()
            metrics = probe.js('({draws:qaDraws,frames:qaFrames,max_frame_gap:qaGap,deferred:qaDeferred})')
            report['large_page_metrics'] = metrics
            report['render_costs'] = probe.js('({functions:qaCosts,long_tasks:qaLongTasks})')
            report['native_command_costs'] = host_costs
            assert probe.count() == 1002, probe.count()
            assert metrics['draws'] == 0 and metrics['deferred'] > 0, metrics
            report['checks']['forty_thousand_existing_points_no_full_redraw_during_ink'] = True
            report['checks']['mid_stroke_acknowledgement_deferred_without_loss'] = True
            report['timings_ms'].update(large_page_500_moves=duration, large_page_max_frame_gap=metrics['max_frame_gap'])
            report['large_page_metrics'] = metrics
            # Windows' native QTest mouse delay can round down to zero. Also
            # measure a paced gesture, yielding the UI loop between samples,
            # to distinguish an artificial event flood from steady input.
            paced_runs = []
            for gesture in range(3):
                scheduler_before = scheduler_sample()
                host_start = len(host_costs)
                probe.js('(()=>{qaDraws=0;qaFrames=0;qaGap=0;qaGapEvents=[];window.qaGestureStarted=performance.now();qaFramePrevious=qaGestureStarted;return true})()')
                duration = probe.stroke(6 + gesture, samples=200, pace_ms=5)
                probe.idle()
                row = probe.js('({draws:qaDraws,frames:qaFrames,max_frame_gap:qaGap,started_ms:qaGestureStarted,finished_ms:performance.now(),frame_gaps:qaGapEvents,function_costs_cumulative:qaCosts,long_tasks:qaLongTasks.filter(task=>task.start+task.duration>=qaGestureStarted)})')
                row.update(duration_ms=duration, scheduler_before=scheduler_before,
                           scheduler_after=scheduler_sample(), native_command_costs=host_costs[host_start:])
                paced_runs.append(row)
            paced = dict(draws=sum(row['draws'] for row in paced_runs), frames=sum(row['frames'] for row in paced_runs),
                         max_frame_gap=max(row['max_frame_gap'] for row in paced_runs))
            probe.js('qaFrameLoop=false')
            report['paced_large_page_metrics'] = paced
            report['paced_gestures'] = paced_runs
            report['render_costs'] = probe.js('({functions:qaCosts,long_tasks:qaLongTasks})')
            report['native_command_costs'] = host_costs
            assert probe.count() == 1005 and paced['draws'] == 0 and paced['frames'] > 5, paced
            # Keep exercising history, saving and zoom after a latency failure;
            # the final assertion still fails acceptance without hiding that coverage.
            assert not report['render_costs']['functions'].get('line', {}).get('calls'), 'Pen-up replayed vector geometry'
            report['timings_ms']['large_page_200_paced_moves'] = [row['duration_ms'] for row in paced_runs]
            report['checks']['paced_large_page_drawing_retains_ink_without_full_redraw'] = True
            probe.action('stroke', points=[[20, 30, .5]], tool=17, width=999)
            assert probe.count() == 1005
            probe.stroke(5)
            probe.idle()
            assert probe.count() == 1006
            report['checks']['rejected_stroke_recovers_bridge_and_retains_ink'] = True
            probe.action('undo')
            assert probe.count() == 1005
            probe.action('redo')
            assert probe.count() == 1006
            for zoom in ['fit', '1', 'page']:
                probe.panel.request_ui('zoom', zoom)
                probe.wait(lambda: probe.js("$('zoom').value") == zoom, 'large page zoom')
                probe.idle()
            save_as('large-page.rmdoc')
            probe.stroke(10, samples=60, pace_ms=5)
            probe.idle()
            assert probe.count() == 1007 and probe.panel.document.dirty
            probe.action('save')
            assert len(Notebook.read((root / 'large-page.rmdoc').read_bytes()).page(0).strokes) == 1007
            report['checks']['large_page_undo_redo_zoom_and_verified_file_save'] = True
            print('Large-page rendering and mid-stroke acknowledgements passed: ' + repr(metrics), flush=True)
            probe.window.grab().save(str(output / 'desktop-stress.png'))
            assert report['source_hashes'] == source_hashes(), 'Sources changed during acceptance; rerun required'
            report['latency'] = dict(mode=latency_mode, limit_ms=80,
                                     passed=paced['max_frame_gap'] < 80,
                                     max_frame_gap_ms=paced['max_frame_gap'])
            if latency_mode == 'enforce':
                assert report['latency']['passed'], ('Paced drawing stalled', paced)
            report['status'] = 'passed'
        except Exception as error:
            report.update(status='failed', error=repr(error))
            probe.window.grab().save(str(output / 'failure.png'))
            raise
        finally:
            (output / 'desktop-stress.json').write_text(json.dumps(report, indent=2))
            probe.close()
    del app
    print('Desktop stress/save/recovery acceptance passed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--latency-mode', choices=('enforce', 'diagnostic'), default='enforce',
                        help='Enforce the 80 ms guard on controlled hosts; diagnostic records it without failing functional acceptance.')
    args = parser.parse_args()
    main(args.output, latency_mode=args.latency_mode)
