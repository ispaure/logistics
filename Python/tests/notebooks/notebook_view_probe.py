"""Real WebEngine checks for notebook chrome, shared zoom and touch arbitration.

Synthetic browser gestures cover the shared engine, not physical device drivers.
"""
import argparse
import json
from pathlib import Path
import time

from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.theme import configured_colors, theme_palette
from commonUtils.ui.appearance.colors import argb, contrast_ratio
from PySide6.QtTest import QTest
from PySide6.QtGui import QNativeGestureEvent, QPointingDevice
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.editor import Editor
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.notebook import Notebook
from features.notebooks.ui.workspace import NotebookWorkspace
from logistics_build.build_retention import scratch
from mobile.palette import css_variables


CHECKS = r'''(()=>{try{
const check=(value,message)=>{if(!value)throw Error(message)};
const scale=()=>canvas.getBoundingClientRect().width/state.width;
const shown=()=>parseInt($('zoomLevel').textContent)/100;
const originalSend=send,originalCapture=canvas.setPointerCapture,originalFinger=$('finger').checked;
const viewportCapture=$('viewport').setPointerCapture;
const commands=[];send=action=>commands.push(action);canvas.setPointerCapture=()=>{};
$('viewport').setPointerCapture=()=>{};
try{
  setZoom(1);$('zoomIn').click();check(Math.abs(scale()-1.2)<.001,'Zoom in button');
  $('zoomOut').click();check(Math.abs(scale()-1)<.001,'Zoom out button');
  check(Math.abs(shown()-scale())<.006,'Visible zoom percentage');
  setZoom(100);check(scale()===4&&$('zoomIn').disabled,'Upper zoom bound');
  setZoom(.001);check(Math.abs(scale()-.1)<.001&&$('zoomOut').disabled,'Lower zoom bound');
  $('zoomFit').click();check($('zoom').value==='page','Fit page button');
  check(Math.abs(shown()-scale())<.006,'Fit page shows actual percentage');
  setZoom(1);
  const viewport=$('viewport'),box=viewport.getBoundingClientRect();
  const x=box.left+box.width/2,y=box.top+box.height/2;
  const point=()=>{const r=canvas.getBoundingClientRect();return [(x-r.left)/r.width,(y-r.top)/r.height]};
  const before=point(),old=scale();
  const wheel=new WheelEvent('wheel',{bubbles:true,cancelable:true,ctrlKey:true,deltaY:-100,clientX:x,clientY:y});
  viewport.dispatchEvent(wheel);
  check(wheel.defaultPrevented&&scale()>old,'Trackpad Ctrl+wheel zoom');
  check(point().every((value,i)=>Math.abs(value-before[i])<.004),'Wheel anchor drift');
  const zoomed=scale();
  const ordinary=new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:20});viewport.dispatchEvent(ordinary);
  check(!ordinary.defaultPrevented&&scale()===zoomed,'Ordinary scrolling intercepted');
  const gesture=(name,scale)=>{const e=new Event(name,{bubbles:true,cancelable:true});
    Object.assign(e,{scale,clientX:x,clientY:y});viewport.dispatchEvent(e)};
  gesture('gesturestart',1);gesture('gesturechange',1.25);gesture('gestureend',1.25);
  check(Math.abs(scale()/zoomed-1.25)<.001,'Safari trackpad zoom');
  const contact=(type,id,px,py)=>canvas.dispatchEvent(new PointerEvent(type,{
    pointerType:'touch',pointerId:id,clientX:px,clientY:py,bubbles:true,cancelable:true}));
  for(const finger of [false,true]){
    setZoom(1);$('finger').checked=finger;
    const rect=canvas.getBoundingClientRect(),paperPoint=[(x-rect.left)/rect.width,(y-rect.top)/rect.height];
    contact('pointerdown',501,x-40,y);contact('pointerdown',502,x+40,y);
    check(active===null&&pan===null,'Pinch failed to cancel finger ink/pan');
    contact('pointermove',501,x-60,y+15);contact('pointermove',502,x+100,y+15);
    // Pointer-up flushes a pending animation frame before releasing the pair.
    contact('pointerup',502,x+100,y+15);
    check(Math.abs(scale()-2)<.001,'Two-finger pinch scale');
    check(Math.abs(shown()-scale())<.006,'Pinch percentage');
    const after=canvas.getBoundingClientRect();
    check(Math.abs(after.left+paperPoint[0]*after.width-x-20)<2&&
      Math.abs(after.top+paperPoint[1]*after.height-y-15)<2,'Moving pinch anchor drift');
    contact('pointermove',501,x-70,y);contact('pointerup',501,x-70,y);
    check(commands.length===0&&active===null&&pan===null,'Pinch saved ink or changed pages');
    check(!touchPinch&&!touchContacts.size,'Pinch contacts leaked');
  }
  setZoom(1);$('finger').checked=false;
  contact('pointerdown',501,x-40,y);contact('pointerdown',502,x+40,y);
  contact('pointercancel',502,x+40,y);contact('pointercancel',501,x-40,y);
  check(!touchPinch&&!touchContacts.size&&!touchZoomBlocked,'Cancelled pinch leaked state');
  // Pen input owns the canvas; an additional palm must not start a pinch.
  active=700;
  contact('pointerdown',501,x-40,y);contact('pointerdown',502,x+40,y);
  check(active===700&&!touchPinch&&!touchContacts.size,'Palm hijacked pen');active=null;
  setZoom(1);active=700;$('zoom').value='1.5';$('zoom').onchange();
  check($('zoom').value==='1'&&Math.abs(scale()-1)<.001,'Zoom preset changed during pen stroke');active=null;
  // Touching the workspace margins must pan/pinch, including with finger drawing on.
  $('finger').checked=true;
  const margin=(type,id,px,py)=>viewport.dispatchEvent(new PointerEvent(type,{
    pointerType:'touch',pointerId:id,clientX:px,clientY:py,bubbles:true,cancelable:true}));
  viewport.scrollLeft=100;viewport.scrollTop=100;
  const scroll=[viewport.scrollLeft,viewport.scrollTop];
  margin('pointerdown',801,x,y);margin('pointermove',801,x-10,y-20);
  check(viewport.scrollLeft===scroll[0]+10&&viewport.scrollTop===scroll[1]+20,'Margin finger pan failed');
  margin('pointerup',801,x-10,y-20);
  margin('pointerdown',801,x-40,y);margin('pointerdown',802,x+40,y);
  margin('pointermove',801,x-80,y);margin('pointermove',802,x+80,y);
  margin('pointerup',802,x+80,y);margin('pointerup',801,x-80,y);
  check(Math.abs(scale()-2)<.001&&commands.length===0,'Margin pinch drew ink or failed to zoom');
  margin('pointerdown',801,x,y);
  window.dispatchEvent(new Event('blur'));
  check(!pan&&!touchContacts.size&&!touchPinch,'Focus loss left a finger pan active');
  gesture('gesturestart',1);window.dispatchEvent(new Event('blur'));
  check(!trackpadGesture,'Focus loss left a trackpad gesture active');
  mode='ink';$('finger').checked=true;
  contact('pointerdown',501,x,y);
  check(active===501,'Finger ink fixture failed to start');
  const pen={pointerId:901,pointerType:'pen',nativePen:true,clientX:x,clientY:y,pressure:.6,preventDefault(){}};
  canvas.onpointerdown(pen);
  check(active===901&&!touchContacts.size&&!pan,'Finger ink prevented stylus takeover');
  finish(pen);
  check(commands.length===1&&commands[0].op==='stroke'&&commands[0].points.every(p=>Math.abs(p[2]-.6)<.001),
    'Stylus takeover saved the finger preview or lost pen pressure');
  commands.length=0;
  if(document.body.classList.contains('notebook-desktop')){
    $('erase').click();document.dispatchEvent(new KeyboardEvent('keydown',{key:'b'}));
    check(mode==='ink'&&!eraserDialog.open,'Eraser dropdown blocked Draw shortcut');
    $('erase').click();window.notebookUI('select');
    check(mode==='select'&&!eraserDialog.open,'Tool menu left eraser settings open');
    $('erase').click();window.notebookUI('toolbar');
    check(!eraserDialog.open,'Hidden toolbar left eraser dropdown open');
    window.notebookUI('toolbar');$('ink').click();
  }else{
    $('layersToggle').click();
    check($('zoomControls').inert&&viewport.inert,'Modal panel left zoom controls keyboard-accessible');
    $('mobileSheet').querySelector('.sheet-heading button').click();
    check(!$('zoomControls').inert&&!viewport.inert,'Closing modal did not restore zoom controls');
  }
  setZoom('page');
  check(canvas.width*canvas.height<=canvasPixelLimit,'Canvas bitmap budget');
  check(getComputedStyle($('paperWrap')).backgroundColor==='rgb(255, 255, 255)','Paper changed color');
  const bar=$('zoomControls').getBoundingClientRect();
  check(bar.width>0&&bar.left>=0&&bar.right<=innerWidth&&bar.bottom<=innerHeight,'Zoom controls outside viewport');
  if(document.body.classList.contains('notebook-mobile')){
    const paper=canvas.getBoundingClientRect(),header=document.querySelector('header').getBoundingClientRect();
    check(paper.top>=header.bottom&&paper.bottom<=bar.top,'Fit page is covered by the floating mobile controls');
    check([...$('zoomControls').querySelectorAll('button')].every(button=>{
      const r=button.getBoundingClientRect();return r.width>=44&&r.height>=44
    }),'Mobile zoom tap targets are smaller than 44px');
  }
  return JSON.stringify({success:true,scale:scale(),percentage:$('zoomLevel').textContent,
    chrome:getComputedStyle(document.querySelector('header')).backgroundColor,
    error_color:getComputedStyle(document.documentElement).getPropertyValue('--destructive').trim(),
    controls_radius:getComputedStyle($('zoomIn')).borderRadius,
    gestures:['ctrl-wheel','safari-gesture','two-finger-pinch'],finger_drawing_safe:true,palm_safe:true});
}finally{
  active=null;pan=null;cancelTouchZoom();send=originalSend;canvas.setPointerCapture=originalCapture;
  $('viewport').setPointerCapture=viewportCapture;
  $('finger').checked=originalFinger;
}
}catch(error){return JSON.stringify({success:false,error:String(error),stack:error.stack})}})()'''


def main(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    app.setStyle('Fusion')
    original_palette = app.palette()
    reports = []

    def wait(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(20)
        raise AssertionError('WebEngine timeout')

    def js(view, code):
        result = []
        view.page().runJavaScript(code, result.append)
        wait(lambda: bool(result))
        return result[0]

    def check_blend_commit(view, name):
        """Compare actual browser-composited pixels, including translucent ink edges."""
        for tool in (18, 23):
            for background in ('white', '#f6e8cd'):
                # Let the numeric zoom's scrollbar/layout resize finish before
                # painting fixture-only ink which is deliberately absent from state.
                js(view, 'setZoom(1)')
                QTest.qWait(100)
                bounds = json.loads(js(view, """(()=>{
                    mode='ink';points=[];clearDraft();
                    ctx.clearRect(0,0,state.width,state.height);
                    ctx.save();ctx.fillStyle='rgba(120,154,188,.6)';ctx.fillRect(20,40,160,50);ctx.restore();
                    inkSettings={tool:TOOL,color:TOOL===18?13:1,width:3,layer:state.layers[0][0]};
                    for(const p of [[30,60,.15],[85,60,.85],[130,110,.85],[185,60,.4],[240,60,.7]]){
                        const before=points.at(-1);points.push(p);preview(before?[before,p]:[p])
                    }
                    $('paperWrap').style.backgroundColor=BACKGROUND;
                    $('viewport').scrollLeft=0;$('viewport').scrollTop=0;
                    return JSON.stringify(canvas.getBoundingClientRect().toJSON())
                })()""".replace('TOOL', str(tool)).replace('BACKGROUND', json.dumps(background))))
                crop = qt.QRect(round(bounds['left']) + 10, round(bounds['top']) + 30, 260, 110)
                QTest.qWait(100)
                before = view.grab(crop).toImage()
                js(view, 'commitDraft(' + str(tool) + ')')
                QTest.qWait(100)
                after = view.grab(crop).toImage()
                label = f'{name}-{tool}-' + ('white' if background == 'white' else 'background')
                before.save(str(output / (label + '-preview.png')))
                after.save(str(output / (label + '-committed.png')))
                differences = [abs(a - b) for a, b in zip(before.constBits(), after.constBits())]
                # The mobile bitmap budget requires fractional resampling: GPU
                # resampling of two live layers can differ at a few edge pixels
                # from resampling the merged Canvas2D bitmap. Keep mean error tiny.
                difference, mean = max(differences), sum(differences) / len(differences)
                assert difference <= 8 and mean < .01, (label, difference, mean)
        js(view, "points=[];$('paperWrap').style.removeProperty('background-color');draw();setZoom('page')")

    with scratch() as root:
        for desktop in (True, False):
            owner = NotebookWorkspace(root=root, library=False) if desktop else QWebEngineView()
            if desktop:
                owner.open(Notebook.new('Notebook appearance and zoom'), 'probe')
                view = owner.web
            else:
                view = owner
                view.setHtml(mobile_editor_html(Editor(Notebook.new('Notebook appearance and zoom')).state(),
                                               'logistics-notebook://view-probe/', console_bridge=True))
            try:
                owner.resize(1200, 900)
                owner.show()
                wait(lambda: js(view, "!!document.getElementById('zoomLevel')"))
                name = 'desktop' if desktop else 'mobile'
                check_blend_commit(view, name)
                for dark in (False, True):
                    mode = 'dark' if dark else 'light'
                    app.setPalette(theme_palette(configured_colors(dark)))
                    QTest.qWait(100)
                    if not desktop:
                        js(view, 'window.notebookAppearance(' + json.dumps(css_variables(mode)) + ')')
                    for width, height in ([(1200, 900), (720, 700)] if desktop else
                                          [(390, 844), (320, 568), (820, 1180), (900, 650), (844, 390), (320, 390)]):
                        owner.resize(width, height)
                        QTest.qWait(150)
                        report = json.loads(js(view, CHECKS))
                        assert report['success'], report
                        expected_surface = configured_colors(dark).surface if desktop else (
                            '#2d3035' if dark else '#fafbfc')
                        assert report['chrome'] == 'rgb' + str(qt.QColor(expected_surface).getRgb()[:3]), report
                        assert contrast_ratio(argb(report['error_color']), argb(expected_surface)) >= 4.5, report
                        # A real viewport resize during a pen stroke waits for cancellation/pen-up.
                        paper_width = js(view, "setZoom('page');active=700;canvas.getBoundingClientRect().width")
                        owner.resize(width - 40, height - 100)
                        QTest.qWait(150)
                        assert js(view, 'viewportResizePending&&canvas.getBoundingClientRect().width') == paper_width
                        clears = js(view, """(()=>{
                            const clear=ctx.clearRect;let count=0;
                            ctx.clearRect=function(...args){count++;return clear.apply(this,args)};
                            try{finish({pointerId:700},true);return count}
                            finally{ctx.clearRect=clear}
                        })()""")
                        assert clears == 1, ('Cancellation with a pending viewport resize replayed the page', clears)

                        assert js(view, '!viewportResizePending&&canvas.getBoundingClientRect().width') != paper_width
                        owner.resize(width, height)
                        QTest.qWait(150)
                        if desktop:
                            data = json.loads(js(view, "JSON.stringify({scale:canvas.getBoundingClientRect().width/state.width,box:$('viewport').getBoundingClientRect().toJSON()})"))
                            box = data['box']
                            local = qt.QPointF(box['left'] + box['width'] / 2, box['top'] + box['height'] / 2)
                            target = view.focusProxy() or view
                            event = QNativeGestureEvent(qt.Qt.NativeGestureType.ZoomNativeGesture,
                                QPointingDevice.primaryPointingDevice(), 2, local, local,
                                qt.QPointF(view.mapToGlobal(local.toPoint())), .25, qt.QPointF())
                            qt.QApplication.sendEvent(target, event)
                            QTest.qWait(80)
                            actual = js(view, 'canvas.getBoundingClientRect().width/state.width')
                            assert abs(actual / data['scale'] - 1.25) < .001, actual
                            assert view.zoomFactor() == 1
                            report['native_qt_pinch'] = True
                            js(view, "setZoom('page')")
                        report.update(presentation=name, mode=mode, width=width, height=height)
                        reports.append(report)
                        # Capture expanded drawing controls as well as the white page.
                        js(view, "$('erase').click()" if desktop else "$('brushToggle').click()")
                        QTest.qWait(80)
                        view.grab().save(str(output / f'{name}-{mode}-{width}x{height}.png'))
                        js(view, "$('closeEraser').click()" if desktop else
                           "$('mobileSheet').querySelector('.sheet-heading button').click()")
            finally:
                if desktop:
                    owner.dispose()
                owner.close()
                owner.deleteLater()
                qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    app.setPalette(original_palette)
    (output / 'view-checks.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(json.dumps(dict(success=True,layouts=len(reports),output=str(output))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
