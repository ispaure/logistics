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
  const r=canvas.getBoundingClientRect();
  // This fixture's PDF is 300×600 and fills the notebook height. Its
  // link rectangles are centered within that narrower rendered area.
  const b={x:(state.width-state.height/2)/2,y:0,width:state.height/2,height:state.height};
  canvas.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerType:kind,pointerId:9,button:0,
    clientX:r.left+(b.x+b.width*.3)/state.width*r.width+dx,
    clientY:r.top+(b.y+b.height*.2)/state.height*r.height+dy,pressure:.5,...keys}))
};
const reset=()=>{queue=[];busy=false;commands.length=0;active=null;pan=null;points=[];linkGesture=null;
  touchContacts.clear();touchPinch=null;touchZoomBlocked=false;pageTouch=null;hideSwipePage();addingSwipePage=false;resetPenRejection();clearPageFeedback();pendingPageFeedback=null;linkFeedback.hidden=true;state.index=0;state.native_pen=false};
const tap=(kind,keys={})=>{event('pointerdown',kind,0,0,keys);event('pointerup',kind,0,0,keys)};
const mobile=mobileViewport();
if(mobile){
  for(const finger of [false,true]){
    reset();$('finger').checked=finger;tap('touch');
    check(commands.length===1&&commands[0].op==='page'&&commands[0].index===2,'Finger link with drawing '+finger);
    check(!linkFeedback.hidden && linkFeedback.getBoundingClientRect().width > 0,'Link bounds show feedback while loading');
    window.notebookUpdate({...state,index:2});
    check(linkFeedback.hidden && !undoPageJump.hidden&&linkReturn===0,'Undo shown after navigation acknowledgement');
    undoPageJump.click();check(commands.at(-1).index===0,'Undo returns to originating page');
  }
  reset();$('finger').checked=false;
  const marginX=(state.width-state.height/2)/2;
  const offset=(marginX*.8-marginX-state.height*.15)/state.width*canvas.getBoundingClientRect().width;
  event('pointerdown','touch',offset);event('pointerup','touch',offset);
  check(!commands.some(a=>a.op==='page'),'Blank margin beside the PDF never follows a link');
  reset();tap('pen');check(!commands.some(a=>a.op==='page'),'Pen never follows link');
  reset();event('pointerdown');event('pointermove','touch',70);event('pointermove');event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Move out and back never follows link');
  reset();event('pointerdown');event('pointercancel');event('pointerup');
  check(linkFeedback.hidden && !commands.some(a=>a.op==='page'),'Cancelled contact never shows feedback or follows link');
  reset();event('pointerdown');event('pointerdown','touch',30,0,{pointerId:10});event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Multitouch never follows link');
  reset();event('pointerdown');linkGesture.time-=1000;event('pointerup');
  check(!commands.some(a=>a.op==='page'),'Long hold never follows link');
  reset();notePenContact(true);tap('touch');check(commands.length===0,'Palm never follows link');
  reset();tap('touch');window.notebookUpdate({...state,index:0},'Navigation failed');
  check(linkFeedback.hidden && undoPageJump.hidden,'Failed navigation clears feedback and has no undo');
  const originalLinks=state.links;
  const navReset=()=>{reset();state.links=[];state.count=3;$('finger').checked=false;setZoom('2');
    $('viewport').scrollLeft=100;$('viewport').scrollTop=150};
  const navEvent=(type,dx=0,dy=0,id=41,target=canvas)=>{
    const b=$('viewport').getBoundingClientRect();
    target.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerType:'touch',
      pointerId:id,button:0,clientX:b.left+b.width/2+dx,clientY:b.top+b.height/2+dy}))
  };
  const navSwipe=(dx,dy=0,target=canvas)=>{navEvent('pointerdown',0,0,41,target);
    navEvent('pointermove',dx,dy,41,target);navEvent('pointerup',dx,dy,41,target)};
  navReset();let before=[$('viewport').scrollLeft,$('viewport').scrollTop];navSwipe(-100);
  check(commands.length===1&&commands[0].index===1,'Zoomed horizontal finger swipe pages');
  check($('viewport').scrollLeft===before[0]&&$('viewport').scrollTop===before[1],'Page swipe never pans');
  navReset();before=[$('viewport').scrollLeft,$('viewport').scrollTop];navSwipe(0,-100);
  check(!commands.length&&$('viewport').scrollTop===before[1],'Vertical finger drag never pans');
  navReset();navSwipe(-100,0,$('viewport'));
  check(commands[0]?.index===1,'Viewport-margin swipe pages');
  navReset();state.index=2;navSwipe(-100);
  check(!commands.length&&!swipeAddPage.hidden,'Final-page swipe offers explicit creation');
  const offer=swipeAddPage.getBoundingClientRect(),viewBox=$('viewport').getBoundingClientRect();
  check(offer.width>=44&&offer.right<=viewBox.right&&offer.left>viewBox.left+viewBox.width/2,
    'Page creation button is usable on right side of page view');
  swipeAddPage.click();check(commands.length===1&&commands[0].op==='add-page','Page button requests creation');
  window.notebookUpdate({...state,index:3,count:4});check(swipeAddPage.hidden,'Creation acknowledgment hides offer');
  navReset();before=[$('viewport').scrollLeft,$('viewport').scrollTop];
  navEvent('pointerdown',-50,0,41);navEvent('pointerdown',50,0,42);
  navEvent('pointermove',-20,20,41);navEvent('pointermove',80,20,42);navEvent('pointerup',80,20,42);
  check(Math.abs($('viewport').scrollLeft-(before[0]-30))<2&&
    Math.abs($('viewport').scrollTop-(before[1]-20))<2&&!commands.length,'Two fingers pan in both axes');
  navEvent('pointerup',-20,20,41);state.links=originalLinks;

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
        (args.output / 'workspace.json').write_text(json.dumps(dict(path=str(workspace), owned=True)))
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
                wait_until(lambda: javascript(view, "typeof undoPageJump !== 'undefined' && !!$('zoomLevel') && $('pdfBackground').naturalWidth > 0"), 'link editor ready')
                result = javascript(view, CHECKS)
                assert result, 'JavaScript checks failed; inspect console'
                reports.append(dict(mobile=mobile, checks=json.loads(result)))
                if mobile:
                    # Sample the compositor output while the outgoing page is still visible.
                    javascript(view, "resetViewportZoom();$('viewport').scrollTop=0;showLinkFeedback(state.links[0])")
                    x, y = json.loads(javascript(view, '''JSON.stringify((() => {
                      const r = linkFeedback.getBoundingClientRect();
                      return [r.left + r.width/2, r.top + r.height/2]
                    })())'''))
                    assert 0 <= x < view.width() and 0 <= y < view.height(), (x, y)
                    QTest.qWait(80)
                    pressed = view.grab()
                    scale = pressed.devicePixelRatio()
                    sample = (round(x * scale), round(y * scale))
                    pressed_color = pressed.toImage().pixelColor(*sample)
                    pressed.save(str(args.output / 'mobile-link-feedback.png'))
                    javascript(view, "linkFeedback.hidden=true")
                    QTest.qWait(80)
                    idle_color = view.grab().toImage().pixelColor(*sample)
                    assert max(pressed_color.red(), pressed_color.green(), pressed_color.blue()) < 80, pressed_color.name()
                    assert min(idle_color.red(), idle_color.green(), idle_color.blue()) > 180, idle_color.name()
                # Use the real browser timer for link return and the mobile page badge.
                javascript(view, "navigateWithPageFeedback(2,0);window.notebookUpdate({...state,index:2})")
                assert javascript(view, '!undoPageJump.hidden')
                QTest.qWait(3150)
                assert javascript(view, 'pageFeedback.hidden && undoPageJump.hidden && linkReturn===null')
                if mobile:
                    javascript(view, "navigateWithPageFeedback(1);window.notebookUpdate({...state,index:1})")
                    assert javascript(view, "!pageFeedback.hidden && undoPageJump.hidden && pageFeedbackLabel.textContent.startsWith('Page 2 ')")
                    QTest.qWait(3150)
                    assert javascript(view, 'pageFeedback.hidden')
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
