"""Optional real-WebEngine lasso/editor acknowledgement and native-save probe.

Run only in a granted browser slot. Events are synthetic DOM PointerEvents;
physical pointer capture, hardware input and native mobile SDKs are not tested.
The controller bounds total work to 110 seconds and uses off-record profiles.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import time
import traceback

from commonUtils.ui import pyside as qt
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from features.notebooks.canvas import editor_html
from features.notebooks.editor import Editor
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.notebook import Notebook
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import composited_image, javascript, wait_until


SETUP = r'''(()=>{
window.qaCheck=(ok,message)=>{if(!ok)throw Error(message)};
window.qaSelectionClearance=()=>{
 const p=pasteStrokes.getBoundingClientRect(),a=selectionActions.getBoundingClientRect();
 qaCheck(!pasteStrokes.hidden,'Copied strokes must expose Paste');
 qaCheck(p.left>=0&&p.top>=0&&p.right<=innerWidth&&p.bottom<=innerHeight,'Paste leaves viewport');
 for(const bar of [$('zoomControls'),document.querySelector('footer')].filter(b=>b&&!b.hidden&&b.getClientRects().length))
  qaCheck(p.bottom+8<=bar.getBoundingClientRect().top,'Paste overlaps zoom dock/footer');
 qaCheck(!(a.left<p.right&&p.left<a.right&&a.top<p.bottom&&p.top<a.bottom),'Paste overlaps selection actions');
 qaCheck(getComputedStyle(selectionActions).zIndex<getComputedStyle(document.querySelector('header')).zIndex,'Selection actions cover menus');
 return true
};
window.qaPointer=(kind,path,cancel=false)=>{
 const id=876,rect=canvas.getBoundingClientRect();
 const emit=(type,p)=>canvas.dispatchEvent(new PointerEvent(type,{
  bubbles:true,cancelable:true,pointerId:id,pointerType:kind,isPrimary:true,
  clientX:rect.left+p[0]/state.width*rect.width,
  clientY:rect.top+p[1]/state.height*rect.height,
  pressure:.5,button:0,buttons:type==='pointerup'||type==='pointercancel'?0:1}));
 emit('pointerdown',path[0]);
 for(const p of path.slice(1))emit('pointermove',p);
 emit(cancel?'pointercancel':'pointerup',path.at(-1));
 qaCheck(active===null,'Gesture did not release active pointer');
};
// Synthetic DOM events have no OS capture identity. Keep every other listener,
// including viewport capture-phase finger handling and palm guards, intact.
canvas.setPointerCapture=()=>{};
canvas.releasePointerCapture=()=>{};
$('finger').checked=false;
paperView='pro';setZoom('page');
$('select').click();
qaCheck(mode==='select','Select button did not activate selection');
const oldRows=state.strokes,oldSelection=selected;
try {
 state.strokes=[{...oldRows[0],id:'qa-tiny',points:[[700,700,.5,.5]]}];selected=new Set(['qa-tiny']);draw();
 const corner=selectionHandles(selectionBounds())[0];qaPointer('mouse',[corner,corner]);
 qaCheck(queue.length===0,'A tiny-dot corner tap emitted a scale edit')
} finally {state.strokes=oldRows;selected=oldSelection;draw()}
return true;
})()'''


def fixture():
    book = Notebook.new('Original synthetic lasso acceptance')
    engine = Editor(book)
    for points in (
        [[300, 500, .4], [450, 550, .8]],
        [[440, 580, .5], [650, 580, .5]],
        [[800, 700, .5], [880, 720, .5]],
    ):
        engine.apply(dict(op='stroke', points=points, tool=17, color=0, width=2))
    book.add_page()
    return book, engine


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    deadline = time.monotonic() + 110
    report = dict(success=False, presentations={}, synthetic_dom_input=True,
                  physical_pointer_capture=False, native_mobile_sdk=False)

    def js(view, code):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Selection browser probe exceeded its 110-second work bound')
        return javascript(view, code, timeout=min(8, remaining))

    def ack(view, engine, expected):
        action = json.loads(js(view, 'JSON.stringify(queue[0]||null)'))
        assert action and action['op'] == expected, (expected, action)
        engine.apply(action)
        js(view, 'window.notebookUpdate(' + json.dumps(engine.state()) + ',null)')
        assert js(view, 'window.notebookIdle()'), 'Acknowledgement did not drain queue'
        return action

    def screenshot(view, name):
        # The shared compositor fence has its own 15-second timeout. Leave
        # room for it instead of starting an unbounded final screenshot.
        if deadline - time.monotonic() < 16:
            raise TimeoutError('Not enough probe time remains for the compositor fence')
        rectangle = qt.QRect(8, 8, view.width() - 8, view.height() - 8)
        assert composited_image(view, rectangle).save(str(output / name))

    with scratch() as workspace:
        report['workspace'] = str(workspace)
        try:
            for name, desktop, batched in [('desktop', True, True), ('mobile', False, False), ('mobile-ios', False, True)]:
                book, engine = fixture()
                original = deepcopy(book.page(0).strokes)
                view = QWebEngineView()
                profile = QWebEngineProfile(view)
                page = QWebEnginePage(profile, view)
                view.setPage(page)
                view.resize(1200 if desktop else 390 if name == 'mobile' else 760, 900)
                view.show()
                result = dict(success=False, actions=[])
                report['presentations'][name] = result
                try:
                    loaded = []
                    view.loadFinished.connect(loaded.append)
                    state = dict(engine.state(), frame_batched_ink=batched)
                    html = (editor_html(state, 'logistics-notebook://selection/', desktop=True, console_bridge=True)
                            if desktop else mobile_editor_html(state, 'logistics-notebook://selection/', console_bridge=True))
                    view.setHtml(html)
                    wait_until(lambda: bool(loaded), 'selection HTML load', timeout=8)
                    assert loaded[-1]
                    assert js(view, SETUP)
                    js(view, "qaPointer('touch',[[250,450],[500,450],[500,620],[250,620],[250,450]])")
                    chosen = json.loads(js(view, 'JSON.stringify([...selected])'))
                    assert chosen == [original[0].id], ('Full containment/finger disabled', chosen)
                    assert len(book.page(0).strokes) == 3
                    assert js(view, "getComputedStyle(selectionActions).display==='flex' && !$('copyStrokes').disabled")
                    screenshot(view, name + '-lasso-light.png')
                    # Pen movement goes through actual production preview and
                    # queue, then the Python Editor supplies its durable ack.
                    js(view, "(()=>{const b=selectionBounds(),x=(b[0]+b[2])/2,y=(b[1]+b[3])/2;qaPointer('pen',[[x,y],[x+30,y+20]])})()")
                    result['actions'].append(ack(view, engine, 'transform'))
                    assert abs(result['actions'][-1]['dx'] - 30) < 1e-6
                    moved = deepcopy(book.page(0).strokes[0].points)
                    js(view, "(()=>{const b=selectionBounds(),p=selectionHandles(b)[2],cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2;qaPointer('mouse',[p,[cx+(p[0]-cx)*1.2,cy+(p[1]-cy)*1.2]])})()")
                    result['actions'].append(ack(view, engine, 'transform'))
                    assert abs(result['actions'][-1]['scale'] - 1.2) < 1e-6
                    assert all(abs(new[3] - old[3] * 1.2) < 1e-6 for old, new in zip(moved, book.page(0).strokes[0].points))
                    js(view, "(()=>{const b=selectionBounds(),p=selectionHandles(b)[4],cx=(b[0]+b[2])/2,cy=(b[1]+b[3])/2,x=p[0]-cx,y=p[1]-cy,a=.3;qaPointer('pen',[p,[cx+x*Math.cos(a)-y*Math.sin(a),cy+x*Math.sin(a)+y*Math.cos(a)]])})()")
                    result['actions'].append(ack(view, engine, 'transform'))
                    assert abs(result['actions'][-1]['angle'] - .3) < 1e-6
                    committed = deepcopy(book.page(0).strokes[0].points)
                    js(view, "(()=>{const b=selectionBounds(),x=(b[0]+b[2])/2,y=(b[1]+b[3])/2;qaPointer('mouse',[[x,y],[x+20,y+10]],true)})()")
                    assert js(view, 'queue.length===0'), 'Cancelled movement was committed'
                    assert json.loads(js(view, 'JSON.stringify(state.strokes.find(s=>selected.has(s.id)).points)')) == committed
                    assert book.page(0).strokes[1:] == original[1:]
                    js(view, "$('copyStrokes').click()")
                    result['actions'].append(ack(view, engine, 'copy-strokes'))
                    assert js(view, "!pasteStrokes.disabled && pasteStrokes.parentElement===document.body"), 'Mobile paste must stay outside hidden panels'
                    assert js(view, 'qaSelectionClearance()'), 'Light presentation controls must not overlap'
                    js(view, "send({op:'page',index:1})")
                    result['actions'].append(ack(view, engine, 'page'))
                    assert js(view, 'selected.size===0')
                    js(view, 'pasteStrokes.click()')
                    result['actions'].append(ack(view, engine, 'paste-strokes'))
                    assert book.page(1).strokes[0].points == committed
                    assert book.page(1).strokes[0].id != original[0].id
                    js(view, "$('cutStrokes').click()")
                    result['actions'].append(ack(view, engine, 'cut-strokes'))
                    assert not book.page(1).strokes
                    js(view, 'pasteStrokes.click()')
                    result['actions'].append(ack(view, engine, 'paste-strokes'))
                    js(view, "$('deleteStrokes').click()")
                    result['actions'].append(ack(view, engine, 'erase'))
                    assert not book.page(1).strokes
                    js(view, 'pasteStrokes.click()')
                    result['actions'].append(ack(view, engine, 'paste-strokes'))
                    js(view, "document.documentElement.style.cssText+=';--surface:#202329;--window:#16191e;--text:#f0f1f3;--border:#69727d;--hover:#353c48;--muted:#c0c5cc;--panel-bg:#202329;--text-color:#f0f1f3';draw()")
                    assert js(view, 'qaSelectionClearance()'), 'Dark presentation controls must not overlap'
                    screenshot(view, name + '-pasted-dark.png')
                    data = book.to_bytes()
                    archive = output / (name + '-saved.rmdoc')
                    archive.write_bytes(data)
                    reopened = Notebook.read(archive.read_bytes())
                    for index in (0, 1):
                        before = book.page(index).strokes
                        after = reopened.page(index).strokes
                        assert len(before) == len(after)
                        for a, b in zip(before, after):
                            assert a.tool == b.tool and a.color == b.color
                            assert len(a.points) == len(b.points)
                            for row_a, row_b in zip(a.points, b.points):
                                assert abs(row_a[0] - row_b[0]) < .0001 and abs(row_a[1] - row_b[1]) < .0001
                                assert abs(row_a[2] - row_b[2]) <= 1 / 255
                                assert abs(row_a[3] - row_b[3]) <= .125
                    result.update(success=True, archive_sha256=sha256(data).hexdigest(),
                                  finger_selection_with_draw_disabled=True,
                                  pointer_types=['touch', 'pen', 'mouse'], saved_reopened_pages=2,
                                  light_and_dark_native_screenshots=True)
                except Exception:
                    if deadline - time.monotonic() >= 16:
                        try:
                            screenshot(view, name + '-failure.png')
                        except Exception:
                            result['failure_screenshot_error'] = traceback.format_exc()
                    raise
                finally:
                    view.close()
                    page.deleteLater()
                    qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    profile.deleteLater()
                    qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
                    view.deleteLater()
                    qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            raise
        finally:
            report['elapsed_seconds'] = 110 - (deadline - time.monotonic())
            (output / 'selection-result.json').write_text(json.dumps(report, indent=2))
    assert app is not None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
