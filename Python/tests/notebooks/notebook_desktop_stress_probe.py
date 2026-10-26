"""Native desktop burst, history, publication failure, recovery and zoom acceptance.

Uses synthetic notebooks and manager scratch; saves only concise evidence outside it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
from unittest.mock import patch

from commonUtils.ui import pyside as qt
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.selection import ResourceChoice
from PySide6.QtTest import QTest
from Scripts.build_retention import scratch
from features.notebooks.notebook import Notebook
from features.notebooks.storage import NotebookDocument
from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
from features.notebooks.ui.menus import NotebookMenus


class Probe:
    def __init__(self, root):
        self.window = NotebookWindow()
        self.panel = NotebookWorkspace(self.window, root=root / 'recovery', library=False)
        self.window.setCentralWidget(self.panel)
        self.window.notebook_menus = NotebookMenus(self.window)
        self.window.resize(1100, 900)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.panel.open_resource(NotebookDocument(Notebook.new('Desktop acceptance')))
        self.wait(lambda: self.js("typeof window.notebookUI==='function'"), 'canvas loading')

    def wait(self, predicate, label, timeout=15):
        start = time.monotonic()
        while not predicate():
            if time.monotonic() - start > timeout:
                raise AssertionError('Timed out: ' + label)
            QTest.qWait(5)

    def js(self, expression):
        values = []
        self.panel.web.page().runJavaScript('JSON.stringify((()=>{try{return {ok:true,value:(' + expression
            + ')}}catch(error){return {ok:false,error:String(error)}}})())', values.append)
        self.wait(lambda: bool(values), 'JavaScript callback')
        result = json.loads(values[0])
        assert result['ok'], result
        return result.get('value')

    def idle(self):
        self.wait(lambda: not self.panel.busy and self.js('!busy&&!queue.length&&active===null'), 'bridge idle')
        QTest.qWait(35)  # Let progress-widget layout and resize observers settle.

    def action(self, op, **fields):
        self.panel.request_command(dict(op=op, **fields))
        self.idle()

    def stroke(self, row=0, samples=8, pause_ms=0):
        box = self.js('canvas.getBoundingClientRect().toJSON()')
        target = self.panel.web.focusProxy() or self.panel.web
        x, y = int(box['left'] + box['width'] * .1), int(box['top'] + box['height'] * (.1 + (row % 35) * .02))
        start = time.monotonic()
        QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x, y))
        for index in range(samples):
            if pause_ms and index == samples // 2:
                QTest.qWait(pause_ms)
            QTest.mouseMove(target, qt.QPoint(x + int((index % 60) * max(1, box['width'] / 180)), y + index % 4), delay=1)
        QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x + 2 * samples, y + 2))
        return (time.monotonic() - start) * 1000

    def count(self):
        return len(self.panel.editor.notebook.page(self.panel.editor.index).strokes)

    def raster(self):
        return hashlib.sha256(self.js('canvas.toDataURL()').encode()).hexdigest()

    def close(self):
        with patch.object(qt.QMessageBox, 'question', return_value=qt.QMessageBox.StandardButton.Discard):
            self.window.close()
        QTest.qWait(50)


def source_hashes():
    owner = Path(__file__).resolve().parents[2] / 'features' / 'notebooks'
    return {name: hashlib.sha256((owner / name).read_bytes()).hexdigest()
            for name in ('canvas.py', 'assets/drawing.js', 'assets/desktop.js', 'ui/workspace.py')}


def main(output):
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    report = dict(status='running', platform=platform.platform(), source_hashes=source_hashes(), checks={}, timings_ms={})
    with scratch() as root:
        probe = Probe(root)
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
            def edit_first(mode, dx=0, dy=0):
                probe.panel.request_ui(mode)
                probe.idle()
                box = probe.js('canvas.getBoundingClientRect().toJSON()')
                x = int(box['left'] + point[0] / 1404 * box['width'])
                y = int(box['top'] + point[1] / 1872 * box['height'])
                target = probe.panel.web.focusProxy() or probe.panel.web
                QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x, y))
                QTest.mouseMove(target, qt.QPoint(x + dx, y + dy), delay=1)
                QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x + dx, y + dy))
                probe.idle()
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
            probe.idle()
            raster = probe.raster()
            for zoom in ['fit', '1', '1.5', '2', 'page']:
                probe.panel.request_ui('zoom', zoom)
                probe.wait(lambda: probe.js("$('zoom').value") == zoom, 'zoom ' + zoom)
            probe.panel.request_ui('zoom', '1')
            probe.idle()
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
            probe.wait(lambda: probe.js("typeof window.notebookUI==='function'"), 'reopened canvas')
            assert probe.count() == count
            probe.stroke(28)
            probe.idle()
            assert probe.count() == count + 1
            report['checks']['reopened_archive_remains_editable'] = True
            # A substantial page catches accidental whole-scene replay in the
            # pointer path, which small synthetic documents can conceal.
            large = Notebook.new('Large-page responsiveness')
            ink = large.page(0)
            for index in range(1000):
                ink.add([[30 + point * 4, 25 + index % 1750 + point % 3, .5] for point in range(40)],
                        tool=17, color=6, width=2)
            probe.panel.dispose()
            probe.panel.open_resource(NotebookDocument(large))
            probe.wait(lambda: probe.js("typeof window.notebookUI==='function'"), 'large canvas')
            probe.idle()
            probe.js("(()=>{window.qaDraws=0;window.qaFrames=0;window.qaGap=0;window.qaDeferred=0;let previous=performance.now(),base=draw;draw=function(){qaDraws++;return base()};let ack=window.notebookStrokeUpdate;window.notebookStrokeUpdate=function(...args){if(active!==null)qaDeferred++;return ack(...args)};window.qaFrameLoop=true;function frame(now){qaFrames++;qaGap=Math.max(qaGap,now-previous);previous=now;if(qaFrameLoop)requestAnimationFrame(frame)}requestAnimationFrame(frame);$('tool').value='23';$('tool').onchange();return true})()")
            delivered = probe.panel.deliver
            probe.panel.deliver = lambda page, action: qt.QTimer.singleShot(120, lambda: delivered(page, action))
            probe.stroke(3, samples=2)
            duration = probe.stroke(4, samples=500, pause_ms=220)
            probe.idle()
            probe.panel.deliver = delivered
            metrics = probe.js('({draws:qaDraws,frames:qaFrames,max_frame_gap:qaGap,deferred:qaDeferred})')
            probe.js('qaFrameLoop=false')
            assert probe.count() == 1002, probe.count()
            assert metrics['draws'] == 0 and metrics['deferred'] > 0 and metrics['frames'] > 5, metrics
            report['checks']['forty_thousand_existing_points_no_full_redraw_during_ink'] = True
            report['checks']['mid_stroke_acknowledgement_deferred_without_loss'] = True
            report['timings_ms'].update(large_page_500_moves=duration, large_page_max_frame_gap=metrics['max_frame_gap'])
            report['large_page_metrics'] = metrics
            probe.action('stroke', points=[[20, 30, .5]], tool=17, width=999)
            assert probe.count() == 1002
            probe.stroke(5)
            probe.idle()
            assert probe.count() == 1003
            report['checks']['rejected_stroke_recovers_bridge_and_retains_ink'] = True
            print('Large-page rendering and mid-stroke acknowledgements passed: ' + repr(metrics), flush=True)
            probe.window.grab().save(str(output / 'desktop-stress.png'))
            assert report['source_hashes'] == source_hashes(), 'Sources changed during acceptance; rerun required'
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
    main(parser.parse_args().output)
