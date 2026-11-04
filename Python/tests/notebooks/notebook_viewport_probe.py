"""Real-browser notebook viewport acceptance across phone, tablet and fold layouts.

Optional Qt WebEngine probe: this checks measured layout and bridge behavior,
not physical hinge, stylus or native UIKit/Android acceptance.
"""
import argparse
import json
from pathlib import Path
import traceback

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.bridge import Bridge
from features.notebooks.editor import Editor
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.notebook import Notebook
from features.notebooks.protocol import update_script
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import javascript, wait_until


SNAPSHOT = r"""JSON.stringify((()=>{
 const v=$('viewport'), box=v.getBoundingClientRect(), r=canvas.getBoundingClientRect(),
   wrap=$('paperWrap').getBoundingClientRect(), css=getComputedStyle(v), b=paperBounds();
 const reset=$('zoomFit'), button=reset.getBoundingClientRect();
 return {paper:b,scale:r.width/state.width,index:state.index,view:paperView,innerWidth,innerHeight,
   focal:[(box.left+v.clientWidth/2-r.left)/r.width,(box.top+v.clientHeight/2-r.top)/r.height],
   moveCenter:r.left+r.width*.5,
   canvas:r.toJSON(),wrap:wrap.toJSON(),viewport:box.toJSON(),
   laptopTools:$('laptopTools').getBoundingClientRect().toJSON(),
   clientWidth:v.clientWidth,clientHeight:v.clientHeight,clientLeft:v.clientLeft,clientTop:v.clientTop,
   contentCenter:[box.left+v.clientLeft+v.clientWidth/2,box.top+v.clientTop+v.clientHeight/2],
   scrollWidth:v.scrollWidth,scrollHeight:v.scrollHeight,scrollLeft:v.scrollLeft,scrollTop:v.scrollTop,
   maxScrollLeft:Math.max(0,v.scrollWidth-v.clientWidth),maxScrollTop:Math.max(0,v.scrollHeight-v.clientHeight),
   layoutKey:viewportLayoutKey(),zoomMemory:viewportZoomMemory,
   resizeFrame,viewportResizePending,active,seq,busy,queue,
   availableWidth:v.clientWidth-parseFloat(css.paddingLeft)-parseFloat(css.paddingRight),
   availableHeight:v.clientHeight-parseFloat(css.paddingTop)-parseFloat(css.paddingBottom),
   reset:{label:reset.getAttribute('aria-label'),visible:!!reset.getClientRects().length,
     inert:!!reset.closest('[inert]'),rect:button.toJSON()}};
})())"""


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    with scratch() as workspace:
        book = Notebook.new('Synthetic viewport acceptance')
        book.add_page(1)
        editor, bridge = Editor(book), Bridge()
        failures, context, received = [], {}, []

        class Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                previous_sequence = bridge.sequence
                action = bridge.command(message)
                if message.startswith('logistics-notebook://'):
                    received.append(dict(bridge_url=bridge.url, sequence_before=previous_sequence,
                        sequence_after=bridge.sequence, accepted=action is not None,
                        action=action, message=message))
                if action:
                    try:
                        editor.apply(action)
                        self.runJavaScript(update_script(dict(editor.state(), **context)))
                    except Exception as error:
                        failures.append(repr(error))
                elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    failures.append(message)

        view = QWebEngineView()
        view.setPage(Page(view))
        view.show()
        loaded = []
        view.loadFinished.connect(loaded.append)

        def js(script):
            result = javascript(view, script)
            assert not failures, failures
            return result

        def settle():
            js('window.viewportProbeSettled=false;requestAnimationFrame(()=>requestAnimationFrame(()=>window.viewportProbeSettled=true))')
            wait_until(lambda: js('window.viewportProbeSettled'), 'viewport layout frames')
            # A frame fence can precede the ResizeObserver callback. Wait for
            # the real layout owner to acknowledge this geometry; never invoke
            # resize() here, since that would hide a missing production update.
            wait_until(lambda: js(f'innerWidth==={view.width()}&&innerHeight==={view.height()}&&viewportZoomMemory!==null&&viewportZoomMemory.layout===viewportLayoutKey()&&resizeFrame===null&&!viewportResizePending&&active===null'),
                       'viewport layout acknowledgement')

        def snapshot():
            settle()
            return json.loads(js(SNAPSHOT))

        def load(width, height, *, tablet=False, native_actions=False, extra_state=None):
            nonlocal bridge
            # A remounted HTML canvas starts at JavaScript sequence zero and
            # must own a fresh protocol bridge, just like the native host.
            bridge.retire()
            bridge = Bridge()
            failures.clear()
            loaded.clear()
            view.resize(width, height)
            context.clear()
            context.update(tablet=tablet, native_actions=native_actions)
            context.update(extra_state or {})
            state = dict(editor.state(), **context)
            view.setHtml(mobile_editor_html(state, bridge.url, console_bridge=True))
            wait_until(lambda: bool(loaded), 'viewport HTML load')
            assert loaded[-1]
            return snapshot()

        def check_default(value, kind):
            b, wrap = value['paper'], value['wrap']
            if kind == 'move':
                assert abs(821 * value['scale'] - value['availableWidth']) < 2, value
                assert abs(value['moveCenter'] - value['contentCenter'][0]) < 2, value
            elif kind == 'width':
                assert b['x'] == 0 and b['width'] == 1404, value
                assert abs(wrap['width'] - value['availableWidth']) < 2, value
            else:
                assert b['x'] == 0 and b['width'] == 1404, value
                assert wrap['width'] <= value['availableWidth'] + 2, value
                assert wrap['height'] <= value['availableHeight'] + 2, value
            if kind != 'move':
                assert abs((wrap['left'] + wrap['right']) / 2 - value['contentCenter'][0]) < 2, value
            reset = value['reset']
            assert reset['visible'] and not reset['inert'] and reset['label'] == 'Reset zoom', value
            assert 0 <= reset['rect']['left'] < reset['rect']['right'] <= view.width() + 1, value
            assert 0 <= reset['rect']['top'] < reset['rect']['bottom'] <= view.height() + 1, value

        report = dict(success=False, defaults=[], transitions=[], physical_hardware=False)
        try:
            for name, width, height, tablet, kind in [
                ('closed-phone-portrait', 390, 844, False, 'move'),
                ('closed-phone-landscape', 844, 390, False, 'width'),
                ('ipad-portrait', 820, 1180, True, 'page'),
                ('narrow-ipad-portrait', 600, 1000, True, 'page'),
                ('duo-open-portrait', 951, 1340, False, 'page'),
                ('duo-open-landscape', 1340, 951, False, 'width'),
                ('wide-ipad-landscape', 1690, 1180, True, 'width'),
            ]:
                value = load(width, height, tablet=tablet, native_actions=True)
                check_default(value, kind)
                report['defaults'].append(dict(name=name, measured=value))
                QTest.qWait(100)
                view.grab().save(str(output / (name + '.png')))

            # Ink outside the narrow Move strip remains accessible but must not
            # silently shrink its default writing scale or shift its center.
            ink = book.page(0)
            ink.add([[10, 10, .5], [20, 20, .5]])
            value = load(390, 844, native_actions=True)
            assert abs(value['scale'] * 821 - value['availableWidth']) < 2, value
            assert abs(value['moveCenter'] - value['contentCenter'][0]) < 2, value
            report['move_with_surrounding_ink'] = value
            ink.strokes.pop()

            value = load(390, 844, native_actions=True, extra_state=dict(
                template_editable=False, pdf_paper=dict(x=0, y=0, width=1404, height=1872)))
            assert abs(value['scale'] * 821 - value['availableWidth']) < 2, value
            assert abs(value['moveCenter'] - value['contentCenter'][0]) < 2, value
            report['move_imported_pdf_page'] = value

            load(390, 844, native_actions=True)
            js("$('paperView').value='move';$('paperView').onchange()")
            value = snapshot()
            assert value['view'] == 'move', value
            assert abs(value['paper']['width'] - 821) < 1 and abs(value['paper']['x'] - 291.5) < 1, value
            report['explicit_move_view_preserves_crop'] = value

            load(390, 844, native_actions=True)
            js('setZoom(1.6)')
            previous = snapshot()
            assert previous['view'] == 'pro' and previous['paper']['width'] == 1404, previous
            assert abs(previous['focal'][0] * 1404 - 702) < 2, previous
            promoted = [dict(name='zoom-promotes-full-paper', measured=previous)]
            for name, width, height in [('promoted-landscape', 844, 390), ('promoted-portrait', 390, 844)]:
                view.resize(width, height)
                current = snapshot()
                assert current['view'] == 'pro' and current['paper']['width'] == 1404, current
                assert abs(current['scale'] / previous['scale'] - 1) < .02, (name, previous, current)
                assert all(abs(a - b) < .01 for a, b in zip(current['focal'], previous['focal'])), (name, previous, current)
                assert abs(current['focal'][0] * 1404 - 702) < 2, current
                promoted.append(dict(name=name, measured=current))
                previous = current
            report['manual_move_promotion'] = promoted

            load(951, 669, native_actions=True)
            js('window.notebookFold([.48,.52])')
            wait_until(lambda: js("document.body.classList.contains('notebook-laptop')"), 'laptop fold')
            value = snapshot()
            check_default(value, 'width')
            assert value['viewport']['top'] >= value['innerHeight'] * .52 - 2, value
            assert value['laptopTools']['bottom'] <= value['innerHeight'] * .48 + 2, value
            assert value['wrap']['top'] >= value['viewport']['top'] - 2, value
            assert value['reset']['rect']['top'] >= value['viewport']['top'] - 2, value
            report['defaults'].append(dict(name='duo-laptop', measured=value))
            QTest.qWait(100)
            view.grab().save(str(output / 'duo-laptop.png'))
            js('window.notebookFold(null)')
            wait_until(lambda: js("!document.body.classList.contains('notebook-laptop')"), 'unfold')

            # A large manual zoom avoids scroll-edge clamping, allowing the
            # document focal point to be compared independently of screen size.
            load(844, 390, native_actions=True)
            js("setZoom(1.6);$('viewport').scrollLeft=canvas.getBoundingClientRect().width*.5-$('viewport').clientWidth/2;$('viewport').scrollTop=canvas.getBoundingClientRect().height*.5-$('viewport').clientHeight/2")
            previous = snapshot()
            for name, width, height, fold in [
                ('rotate-portrait', 390, 844, None),
                ('open-portrait', 951, 1340, None),
                ('rotate-open-landscape', 1340, 951, None),
                ('enter-laptop', 951, 669, [.48, .52]),
                ('leave-laptop', 951, 669, None),
            ]:
                view.resize(width, height)
                settle()
                js('window.notebookFold(' + json.dumps(fold) + ')')
                current = snapshot()
                assert abs(current['scale'] / previous['scale'] - 1) < .02, (name, previous, current)
                assert all(abs(a - b) < .01 for a, b in zip(current['focal'], previous['focal'])), (name, previous, current)
                report['transitions'].append(dict(name=name, measured=current))
                previous = current

            js("$('zoomFit').click()")
            reset = snapshot()
            check_default(reset, 'width')
            report['reset_default'] = reset
            js('setZoom(1.6);send({op:"page",index:1})')
            wait_until(lambda: editor.index == 1 and js('!busy'), 'page two bridge acknowledgement')
            check_default(snapshot(), 'width')
            js('setZoom(1.6);send({op:"page",index:0})')
            wait_until(lambda: editor.index == 0 and js('!busy'), 'page one bridge acknowledgement')
            check_default(snapshot(), 'width')
            report['page_away_and_back_reset'] = True

            load(844, 390, native_actions=True, extra_state=dict(native_pen=True))
            before = len(book.page(0).strokes)
            js(r"""window.viewportPalmProbe=(()=>{
              const check=(ok,message)=>{if(!ok)throw Error(message)};
              const v=$('viewport'), r=canvas.getBoundingClientRect(), box=v.getBoundingClientRect(),
                x=(Math.max(r.left,box.left)+Math.min(r.right,box.right))/2,
                y=(Math.max(r.top,box.top)+Math.min(r.bottom,box.bottom))/2;
              check(document.elementFromPoint(x,y)===canvas,'Palm fixture must hit visible canvas');
              const capture=canvas.setPointerCapture, viewportCapture=v.setPointerCapture;
              // DOM-dispatched pointers do not own an OS pointer capture. Only
              // capture allocation is stubbed; real listeners/bridge stay live.
              canvas.setPointerCapture=v.setPointerCapture=()=>{};
              resetPenRejection();state.native_pen=true;$('finger').checked=false;
              const baselineScroll=[v.scrollLeft,v.scrollTop];
              const touch=(type,id,dx=0,dy=0)=>canvas.dispatchEvent(new PointerEvent(type,
                {bubbles:true,cancelable:true,pointerType:'touch',pointerId:id,
                 clientX:x+dx,clientY:y+dy,pressure:.5,buttons:type==='pointerup'?0:1}));
              const pen=(action,id,dx=0)=>window.logisticsNativePen(action,id,
                [[x+dx,y,.6]],innerWidth,innerHeight);
              const blocked=(message,penId=null)=>{
                check(!touchContacts.size&&!pan&&!touchPinch,'Palm reached gesture state: '+message);
                check(active===penId,'Palm changed active contact: '+message);
                check(v.scrollLeft===baselineScroll[0]&&v.scrollTop===baselineScroll[1],'Palm scrolled page: '+message);
              };
              const touchAttempt=(id)=>{
                touch('pointerdown',id);touch('pointerdown',id+1,30);
                touch('pointermove',id,-20,15);touch('pointermove',id+1,45,15);
                touch('pointerup',id,-20,15);touch('pointercancel',id+1,45,15);
              };
              window.logisticsPenProximity(true,x,y,innerWidth,innerHeight);
              check(penTouchBlocked(),'Native hover did not block touch');
              touchAttempt(41);blocked('hover');
              window.logisticsPenProximity(false,x,y,innerWidth,innerHeight);
              check(penTouchBlocked(),'Hover-exit grace missing');
              touchAttempt(51);blocked('hover-exit grace');
              return {check,touch,pen,blocked,touchAttempt,x,y,restore(){
                resetPenRejection();canvas.setPointerCapture=capture;v.setPointerCapture=viewportCapture;
              }};
            })()""")
            QTest.qWait(400)
            js(r"""(()=>{
              const p=window.viewportPalmProbe;
              p.check(!penTouchBlocked(),'Touch did not recover after hover grace');
              p.touch('pointerdown',61);
              p.check(touchContacts.size===1&&pan?.id===61,'Finger pan not available before pen');
              p.pen('down',92);
              p.check(penTouchBlocked(),'Native pen contact did not reject touch');
              p.blocked('pen preempted finger pan',100092);
              p.touchAttempt(71);p.blocked('drawing',100092);
              p.pen('move',92,20);p.pen('up',92,30);
              p.check(penTouchBlocked(),'Pen-up grace missing');
              p.touchAttempt(81);p.blocked('pen-up grace');
            })()""")
            wait_until(lambda: len(book.page(0).strokes) == before + 1 and js('!busy'), 'pen stroke bridge acknowledgement')
            QTest.qWait(400)
            js(r"""(()=>{
              const p=window.viewportPalmProbe;
              p.check(!penTouchBlocked(),'Touch did not recover after pen-up grace');
              p.touch('pointerdown',101);
              p.check(touchContacts.size===1&&pan?.id===101,'Finger gestures did not recover');
              p.touch('pointercancel',101);
              p.pen('down',93);p.pen('move',93,15);p.pen('cancel',93,20);
              p.check(active===null&&points.length===0,'Cancelled pen left ink preview');
              p.check(penTouchBlocked(),'Cancelled pen grace missing');
              resetPenRejection();p.blocked('cancellation reset');
              window.logisticsPenProximity(true,p.x,p.y,innerWidth,innerHeight);
              window.dispatchEvent(new Event('blur'));
              p.check(!penTouchBlocked(),'Window blur left stale pen rejection');
              p.restore();
            })()""")
            assert len(book.page(0).strokes) == before + 1
            report['palm_rejection'] = dict(synthetic_native_hover_bridge=True, hover_exit_grace=True,
                contact_preempts_finger_pan=True, drawing_blocks_pinch_pan=True,
                pen_up_grace=True, finger_recovery=True, cancelled_pen_not_saved=True,
                blur_clears_proximity=True, physical_stylus=False)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            report['failed_bridge_sequence'] = bridge.sequence
            try:
                report['failed_browser_state'] = json.loads(javascript(view, SNAPSHOT))
            except Exception as diagnostic_error:
                report['diagnostic_error'] = repr(diagnostic_error)
            raise
        finally:
            report['bridge_sequence'] = bridge.sequence
            report['received_actions'] = received
            (output / 'viewport-result.json').write_text(json.dumps(report, indent=2))
            view.close()
            view.deleteLater()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
