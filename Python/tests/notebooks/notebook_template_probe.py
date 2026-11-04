"""Real WebEngine template controls, compositing and Pro/Move coordinate checks.

Run with PYTHONPATH=Python:. and the desktop interpreter. Evidence is local-only.
This exercises both shared presentations, not physical tablet firmware import.
"""
import argparse
import json
from pathlib import Path

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.canvas import editor_html
from features.notebooks.editor import Editor
from features.notebooks.notebook import Notebook
from features.notebooks.protocol import update_script, stroke_script
from features.notebooks.templates import CATALOG
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import javascript, wait_until


def main(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    reports = []
    wait = wait_until
    js = javascript

    with scratch():
        for desktop in (True, False):
            book = Notebook.new('Template validation')
            editor = Editor(book)
            view = QWebEngineView()
            view.resize(1200 if desktop else 390, 900 if desktop else 844)
            view.setHtml(editor_html(editor.state(), 'logistics-notebook://template-probe/',
                                     console_bridge=True, desktop=desktop, mobile=not desktop, paper_preview=False))
            view.show()
            try:
                wait(lambda: js(view, "typeof paperView!=='undefined'&&!!$('pageTemplate')&&!!$('zoomLevel')"))
                name = 'desktop' if desktop else 'mobile'
                # Exercise the actual HTML control and pass its queued action
                # through the same model/acknowledgement contract as both hosts.
                for template in CATALOG:
                    for paper_format in ('pro', 'move'):
                        js(view, "$('pageTemplate').value=" + json.dumps(template) + ";$('templateFormat').value="
                           + json.dumps(paper_format) + ";$('pageTemplate').dispatchEvent(new Event('change'))")
                        action = json.loads(js(view, 'JSON.stringify(queue[0])'))
                        editor.apply(action)
                        js(view, update_script(editor.state()))
                        wait(lambda: js(view, "$('pdfBackground').hidden||($('pdfBackground').complete&&$('pdfBackground').naturalWidth>0)"))
                        QTest.qWait(30)
                        assert js(view, "$('pageTemplate').value") == template
                        if template.startswith('Logistics '):
                            assert js(view, "$('templateFormat').value") == paper_format
                        assert js(view, "$('pdfBackground').hidden") == (template == 'Blank')
                        if template == 'Logistics Restaurant review':
                            view.grab().save(str(output / f'{name}-restaurant-{paper_format}.png'))
                # Crop starts centered and at the top; switching views leaves
                # model points untouched and maps pointer input to the full scene.
                editor.apply(dict(op='template', name='P Lines small', format='pro', visible=True))
                js(view, update_script(editor.state()))
                report = json.loads(js(view, r'''(()=>{
                    const check=(v,m)=>{if(!v)throw Error(m)};
                    $('paperView').value='move';$('paperView').dispatchEvent(new Event('change'));
                    setZoom('page');
                    let b=paperBounds();check(b.x===291.5&&b.width===821&&b.height===1460,'Move crop');
                    const r=canvas.getBoundingClientRect(),wrap=$('paperWrap').getBoundingClientRect();
                    const p=coord({clientX:wrap.left+wrap.width/2,clientY:wrap.top+10,pointerType:'mouse'});
                    check(Math.abs(p[0]-702)<.1,'Centered ink coordinates');
                    check(Math.abs(r.top-wrap.top)<.1,'Top alignment');
                    check(Math.abs(r.left+291.5*r.width/state.width-wrap.left)<.1,'Crop origin');
                    $('paperView').value='pro';$('paperView').dispatchEvent(new Event('change'));
                    check(paperBounds().width===1404&&paperBounds().x===0,'Pro margins');
                    $('paperView').value='move';$('paperView').dispatchEvent(new Event('change'));
                    return JSON.stringify({presentation:document.body.className,center_x:p[0],crop:b})
                })()'''))
                before = editor.snapshot()
                js(view, "$('paperView').value='pro';$('paperView').dispatchEvent(new Event('change'))")
                assert before == editor.snapshot() and js(view, 'queue.length===0'), 'View selection mutated notebook'
                js(view, "paperView='move';resize();window.templateClears=0;window.templateClear=ctx.clearRect;"
                   "ctx.clearRect=function(...args){window.templateClears++;return window.templateClear.apply(this,args)}")
                editor.apply(dict(op='stroke', points=[[500, 100, .5], [600, 100, .5]]))
                js(view, stroke_script(editor, None))
                assert js(view, 'window.templateClears') == 0, 'Interior ink acknowledgement replayed the page'
                js(view, 'ctx.clearRect=window.templateClear')
                editor.apply(dict(op='stroke', points=[[20, 1800, .5], [1380, 1810, .5]]))
                js(view, update_script(editor.state()))
                assert js(view, "paperView='move';resize();paperBounds().height>1810&&paperBounds().x<20&&paperBounds().width>1360")
                editor.apply(dict(op='template', name='P Lines small', format='pro', visible=False))
                js(view, update_script(editor.state()))
                assert js(view, "$('pdfBackground').hidden"), 'Hidden template still visible'
                assert len(book.page(0).strokes) == 2, 'Background selection changed ink'
                editor.apply(dict(op='template', name='Logistics Restaurant review', format='move', visible=True))
                page = book.pages[0]
                book.members[page.template + '.template'] = b'{"foreign":"artwork"}'
                js(view, update_script(editor.state()))
                assert js(view, "$('pdfBackground').hidden&&$('templateNotice').textContent.includes('unavailable')"), 'Foreign artwork was silently replaced'
                assert js(view, "$('templateFormat').disabled&&$('templateVisible').disabled&&!$('pageTemplate').disabled")
                # Imported names which happen to match Object.prototype keys
                # still need a preserved option and an unavailable-artwork notice.
                for reference in ('toString', '__proto__', 'P Lines small Move'):
                    page.template = reference
                    js(view, update_script(editor.state()))
                    assert js(view, "$('pageTemplate').value===" + json.dumps(reference) + "&&$('templateNotice').textContent.includes('unavailable')")
                reports.append(report)
            finally:
                view.close()
                view.deleteLater()
                qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    (output / 'templates.json').write_text(json.dumps(dict(status='passed', presentations=reports,
        templates=len(CATALOG), formats=2, scope='Qt WebEngine; no tablet firmware or physical stylus'), indent=2))
    print('Desktop/mobile template controls, vector backgrounds and stable crop coordinates passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
