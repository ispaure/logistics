"""Real WebEngine link arbitration with synthetic contacts and retained evidence."""
import argparse
import json
from pathlib import Path
from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.canvas import editor_html
from features.notebooks.editor import Editor
from features.pdf.annotation import notebook_from_pdf
from tests.readers.test_pdf_links import linked_pdf
from tests.notebooks.webengine_driver import javascript, wait_until
from logistics_build.build_retention import scratch

CHECKS = r'''(()=>{
const results=[];
const check=(v,s)=>{if(!v)throw Error(s);results.push(s)};
const commands=[];
send = action => {commands.push(action);queue.push(action);busy=true};
canvas.setPointerCapture=()=>{};$('viewport').setPointerCapture=()=>{};
const event=(type,kind='touch',dx=0,dy=0,keys={})=>{
  const r=canvas.getBoundingClientRect(),b=state.pdf_paper||{x:0,y:0,width:state.width,height:state.height};
  canvas.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerType:kind,pointerId:9,button:0,
    clientX:r.left+(b.x+b.width*.3)/state.width*r.width+dx,
    clientY:r.top+(b.y+b.height*.2)/state.height*r.height+dy,pressure:.5,...keys}))
};
const reset=()=>{queue=[];busy=false;commands.length=0;active=null;pan=null;points=[];linkGesture=null;
  touchContacts.clear();touchPinch=null;touchZoomBlocked=false;resetPenRejection();clearLinkReturn();pendingLinkJump=null;state.index=0;state.native_pen=false};
const tap=(kind,keys={})=>{event('pointerdown',kind,0,0,keys);event('pointerup',kind,0,0,keys)};
const mobile=mobileViewport();
if(mobile){
  for(const finger of [false,true]){
    reset();$('finger').checked=finger;tap('touch');
    check(commands.length===1&&commands[0].op==='page'&&commands[0].index===2,'Finger link with drawing '+finger);
    window.notebookUpdate({...state,index:2});
    check(!undoPageJump.hidden&&linkReturn===0,'Undo shown after navigation acknowledgement');
    undoPageJump.click();check(commands.at(-1).index===0,'Undo returns to originating page');
  }
  reset();tap('pen');check(!commands.some(a=>a.op==='page'),'Pen never follows link');
  reset();event('pointerdown');event('pointermove','touch',70);event('pointermove');event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Move out and back never follows link');
  reset();event('pointerdown');event('pointercancel');event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Cancelled contact never follows link');
  reset();event('pointerdown');event('pointerdown','touch',30,0,{pointerId:10});event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Multitouch never follows link');
  reset();event('pointerdown');linkGesture.time-=1000;event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Long hold never follows link');
  reset();notePenContact(true);tap('touch');check(commands.length===0,'Palm never follows link');
  reset();tap('touch');window.notebookUpdate({...state,index:0},'Navigation failed');
  check(undoPageJump.hidden,'Failed navigation has no undo');
} else {
  for(const platform of ['MacIntel','Win32','Linux x86_64']){
    Object.defineProperty(navigator,'platform',{value:platform,configurable:true});
    const keys=platform==='MacIntel'?{metaKey:true}:{ctrlKey:true};
    reset();tap('mouse');check(!commands.some(a=>a.op==='page'),'Plain click draws on '+platform);
    reset();tap('mouse',keys);check(commands.length===1&&commands[0].op==='page','Modified click follows on '+platform);
    reset();tap('mouse',platform==='MacIntel'?{ctrlKey:true}:{metaKey:true});
    check(!commands.some(a=>a.op==='page'),'Other modifier draws on '+platform)
  }
}
reset();
return JSON.stringify(results)
})()'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    reports = []
    with scratch() as workspace:
        profile = QWebEngineProfile(app)
        profile.setCachePath(str(workspace / 'cache'))
        profile.setPersistentStoragePath(str(workspace / 'storage'))
        for mobile in (False, True):
            view = QWebEngineView()
            page = QWebEnginePage(profile, view)
            view.setPage(page)
            state = Editor(notebook_from_pdf(linked_pdf(), 'Link fixture')).state()
            view.resize(800, 1000)
            view.setHtml(editor_html(state, 'logistics-notebook://links/', console_bridge=True,
                                    mobile=mobile, desktop=not mobile))
            view.show()
            try:
                wait_until(lambda: javascript(view, "typeof undoPageJump !== 'undefined' && !!$('zoomLevel')"), 'link editor ready')
                result = javascript(view, CHECKS)
                assert result, 'JavaScript checks failed; inspect console'
                reports.append(dict(mobile=mobile, checks=json.loads(result)))
                # Use the real browser timer: acknowledgement starts a 3-second undo window.
                javascript(view, "pendingLinkJump={from:0,to:2};queue=[{op:'page',index:2}];busy=true;window.notebookUpdate({...state,index:2})")
                assert javascript(view, '!undoPageJump.hidden')
                QTest.qWait(3150)
                assert javascript(view, 'undoPageJump.hidden && linkReturn===null')
                view.grab().save(str(args.output / ('mobile.png' if mobile else 'desktop.png')))
            finally:
                view.close()
                page.deleteLater()
                view.deleteLater()
                qt.QApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
        profile.deleteLater()
        qt.QApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    (args.output / 'report.json').write_text(json.dumps(dict(success=True, results=reports, workspace_removed=not workspace.exists()), indent=2))
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
