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
from features.notebooks.remarkable_export import export_rmdoc
from features.notebooks.protocol import update_script, stroke_script
from features.notebooks.templates import FORM_TEMPLATES, CATALOG
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import javascript, wait_until


def pdf_highlighter(view, desktop):
    book = Notebook.new('PDF highlighter order')
    editor = Editor(book)
    editor.apply(dict(op='template', name='Logistics Restaurant review', format='pro', visible=True))
    # The first writing rule is at y=173. Cross it with native yellow, with
    # black ink below the highlight in scene order and white ink above it.
    for tool, color, points in (
        (17, 0, [[600, 150, .5], [600, 200, .5]]),
        (18, 13, [[500, 173, .5], [900, 173, .5]]),
        (17, 2, [[730, 150, .5], [730, 200, .5]]),
        (18, 13, [[650, 173, .5], [770, 173, .5]]),
        (17, 2, [[800, 150, .5], [800, 200, .5]]),
    ):
        editor.apply(dict(op='stroke', tool=tool, color=color, width=3, points=points))
    source_ink = book.page(0).to_bytes()
    reopened = Notebook.read(export_rmdoc(book))
    assert reopened.content['fileType'] == 'pdf'
    assert reopened.page(0).to_bytes() == source_ink
    view.setHtml(editor_html(Editor(reopened).state(), 'logistics-notebook://pdf-highlight/',
                             console_bridge=True, desktop=desktop, mobile=not desktop, paper_preview=False))
    wait_until(lambda: javascript(view, "typeof state !== 'undefined' && state.name === 'PDF highlighter order' && "
                                  "!!$('pdfBackground').naturalWidth"))
    pixels = json.loads(javascript(view, r"""(()=>{
      draw();
      function pixel(x,y){
        return [...ctx.getImageData(Math.floor(x*canvas.width/state.width),
                                    Math.floor(y*canvas.height/state.height),1,1).data];
      }
      const plain = pixel(700, 166);
      const rule = [171,172,173,174,175].map(y=>pixel(700,y)).reduce((a,b)=>a[0]<b[0]?a:b);
      const black = pixel(600,173), white = pixel(800,173);
      const overlap = pixel(690,166), single = pixel(560,166), intervening = pixel(730,173);
      const singleRule = [171,172,173,174,175].map(y=>pixel(560,y)).reduce((a,b)=>a[0]<b[0]?a:b);
      const crossSection = () => {
        const sy = canvas.height / state.height, x = Math.floor(700 * canvas.width / state.width);
        const top = Math.floor(156 * sy), bottom = Math.floor(190 * sy);
        const rgba = ctx.getImageData(x, top, 1, bottom - top + 1).data;
        return Array.from({length: 35}, (_, i) => {
          const offset = 4 * (Math.floor((156 + i) * sy) - top);
          return [...rgba.subarray(offset, offset + 4)];
        });
      };
      const beforeLive = crossSection();
      inkSettings = {tool:18,color:13,width:1};
      points = [[650,173,.5],[770,173,.5]];
      const retrace = points;
      flushPreview();
      const live = crossSection();
      points = [];
      queue.push({op:'stroke', ...inkSettings, points:retrace});
      draw();
      const queued = crossSection();
      queue.pop();
      draw();
      const fill = document.createElement('canvas');
      fill.width = 128; fill.height = 96;
      const g = fill.getContext('2d', {willReadFrequently: true});
      g.fillStyle = 'white';
      g.fillRect(0, 0, fill.width, fill.height);
      const pass = points => ({tool:18, color:16, points:points.map(([x,y]) => [x,y,.5,26])});
      paintOrderedInk([
        pass([[8,30],[115,30],[115,50],[8,50],[8,30],[115,30]]),
        pass([[8,43.25],[115,43.25]]),
      ], g, false);
      const fillSection = Array.from({length: 40}, (_, i) => [...g.getImageData(60,20+i,1,1).data]);
      return JSON.stringify({plain,rule,black,white,overlap,single,intervening,singleRule,fillSection,
        liveChanges: beforeLive.flatMap((pixel, i) => String(pixel) === String(live[i]) ? [] : [[i,pixel,live[i]]]),
        queuedChanges: beforeLive.flatMap((pixel, i) => String(pixel) === String(queued[i]) ? [] : [[i,pixel,queued[i]]])});
    })()"""))
    plain, rule, black, white = (pixels[key] for key in ('plain', 'rule', 'black', 'white'))
    assert plain[0] >= 245 and plain[2] <= 130, pixels
    assert rule[0] < plain[0] - 10 and rule[2] < plain[2] - 5, pixels
    assert max(black[:3]) <= 20 and min(white[:3]) >= 235, pixels
    assert pixels['overlap'] == pixels['single'] == pixels['intervening'], pixels
    assert pixels['singleRule'] == rule, pixels
    # Chromium can resample the underlying PDF bitmap by a few color levels
    # on readback. A second coat of the highlight changes much more than this.
    for key in ('liveChanges', 'queuedChanges'):
        assert all(max(abs(a - b) for a, b in zip(before, after)) <= 3
                   for _, before, after in pixels[key]), (desktop, pixels[key])
    assert all(rgba == [199, 199, 198, 255] for rgba in pixels['fillSection']), pixels
    return pixels


def main(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    reports = []
    wait = wait_until
    js = javascript

    with scratch():
        for desktop in (True, False):
            pdf_view = QWebEngineView()
            pdf_view.resize(1200 if desktop else 390, 900 if desktop else 844)
            pdf_view.show()
            try:
                highlight = pdf_highlighter(pdf_view, desktop)
                pdf_view.grab().save(str(output / f'pdf-highlight-{"desktop" if desktop else "mobile"}.png'))
            finally:
                pdf_view.close()
                pdf_view.deleteLater()
                qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
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
                if desktop:
                    assert js(view, "window.notebookUI('template');$('layerOptions').open&&document.activeElement===$('pageTemplate')"), 'Desktop Page Template entry'
                else:
                    assert js(view, "$('pageTemplateButton').click();$('mobileSheet').dataset.panel==='layers'&&!$('mobileSheet').hidden"), 'Mobile Page Template entry'
                assert js(view, "$('templateCompatibility').textContent.includes('not affiliated with or endorsed by reMarkable')"), 'Compatibility notice'
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
                        assert js(view, "getComputedStyle($('templateFormatControl')).display!=='none'") == (template in FORM_TEMPLATES)
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
                # Select the document view through its real control, not just
                # the derived paperView variable. Drain layout work before
                # measuring the subsequent incremental acknowledgement.
                js(view, "$('paperView').value='move';$('paperView').dispatchEvent(new Event('change'))")
                assert before == editor.snapshot() and js(view,
                    "documentPaperView==='move'&&paperView==='move'&&$('paperView').value==='move'&&queue.length===0"), 'Move view selection mutated notebook or lost its choice'
                js(view, r"""(()=>{
                    window.templateFenceReady=false;window.templateFenceError='';
                    window.templateFenceFrame=null;
                    const deadline=performance.now()+14000;
                    let previous=null,stable=0;
                    function frame(){
                        window.templateFenceFrame=null;
                        const background=$('pdfBackground');
                        const idle=active===null&&!busy&&!queue.length&&resizeFrame===null&&!viewportResizePending&&
                            (background.hidden||(background.complete&&background.naturalWidth>0));
                        const geometry=JSON.stringify([viewportLayoutKey(),canvas.width,canvas.height,
                            canvas.style.width,canvas.style.height,paperBounds(),paperView,documentPaperView]);
                        stable=idle?(geometry===previous?stable+1:1):0;previous=geometry;
                        if(stable>=2){window.templateFenceReady=true;return}
                        if(performance.now()>=deadline){window.templateFenceError='Viewport did not reach two stable idle frames';return}
                        window.templateFenceFrame=requestAnimationFrame(frame)
                    }
                    window.templateFenceFrame=requestAnimationFrame(frame)
                })()""")
                try:
                    wait(lambda: js(view, 'window.templateFenceReady||!!window.templateFenceError'),
                         'two stable template viewport frames')
                    assert js(view, 'window.templateFenceReady'), js(view, 'window.templateFenceError')
                    js(view, r"""(()=>{
                        window.templateClears=0;window.templateClearEvents=[];
                        window.templateClear=ctx.clearRect;
                        window.templateObservation=()=>({clears:window.templateClears,
                            events:window.templateClearEvents,paperView,documentPaperView,defaultViewportZoom,
                            resizeFrame,viewportResizePending,bounds:paperBounds(),layout:viewportLayoutKey(),
                            backing:[canvas.width,canvas.height],strokes:state.strokes.length});
                        ctx.clearRect=function(...args){
                            window.templateClears++;
                            if(window.templateClearEvents.length<16)
                                window.templateClearEvents.push({args,stack:new Error('canvas clear').stack,
                                    paperView,documentPaperView,resizeFrame,viewportResizePending,
                                    bounds:paperBounds(),layout:viewportLayoutKey()});
                            return window.templateClear.apply(this,args)
                        }
                    })()""")
                    before_ack=json.loads(js(view,'JSON.stringify(window.templateObservation())'))
                    editor.apply(dict(op='stroke', points=[[500, 100, .5], [600, 100, .5]]))
                    js(view, stroke_script(editor, None))
                    after_ack=json.loads(js(view,'JSON.stringify(window.templateObservation())'))
                    assert after_ack['clears'] == 0, ('Interior ink acknowledgement replayed the page',
                                                     dict(before=before_ack,after=after_ack))
                    assert after_ack['strokes'] == before_ack['strokes']+1, 'Interior acknowledgement was not applied'
                    # Positive control: a stroke outside the Move crop must
                    # redraw immediately on the same real incremental contract.
                    js(view,'window.templateClears=0;window.templateClearEvents=[]')
                    editor.apply(dict(op='stroke', points=[[20, 1800, .5], [1380, 1810, .5]]))
                    js(view, stroke_script(editor, None))
                    expanded=json.loads(js(view,'JSON.stringify(window.templateObservation())'))
                    assert expanded['clears'] > 0, ('Expanding ink acknowledgement did not redraw',expanded)
                    assert expanded['bounds']['height']>1810 and expanded['bounds']['x']<20 and expanded['bounds']['width']>1360, expanded
                    js(view, update_script(editor.state()))
                    assert js(view, "paperBounds().height>1810&&paperBounds().x<20&&paperBounds().width>1360")
                    report['interior_ack']=dict(before=before_ack,after=after_ack)
                    report['expanding_ack']=expanded
                finally:
                    js(view, "if(window.templateFenceFrame!==null)cancelAnimationFrame(window.templateFenceFrame);"
                       "window.templateFenceFrame=null;if(window.templateClear)ctx.clearRect=window.templateClear")
                editor.apply(dict(op='template', name='P Lines small', format='pro', visible=False))
                js(view, update_script(editor.state()))
                assert js(view, "$('pdfBackground').hidden"), 'Hidden template still visible'
                assert len(book.page(0).strokes) == 2, 'Background selection changed ink'
                editor.apply(dict(op='template', name='Logistics Restaurant review', format='move', visible=True))
                page = book.pages[0]
                book.members[page.template + '.template'] = b'{"foreign":"artwork"}'
                js(view, update_script(editor.state()))
                assert js(view, "$('pdfBackground').hidden&&$('templateNotice').textContent.includes('unavailable')"), 'Foreign artwork was silently replaced'
                assert js(view, "$('templateFormatControl').hidden&&$('templateFormat').disabled&&$('templateVisible').disabled&&!$('pageTemplate').disabled")
                assert js(view, "$('templateDescription').textContent.includes('Imported')"), 'Imported artwork incorrectly claimed as original'
                # Imported names which happen to match Object.prototype keys
                # still need a preserved option and an unavailable-artwork notice.
                for reference in ('toString', '__proto__', 'P Lines small Move'):
                    page.template = reference
                    js(view, update_script(editor.state()))
                    assert js(view, "$('pageTemplate').value===" + json.dumps(reference) + "&&$('templateNotice').textContent.includes('unavailable')&&$('templateFormatControl').hidden")
                # Exercise one-page changes and Add Page through the real shared
                # UI queue, including inheritance without duplicating handwriting.
                def change_template(template):
                    js(view, "$('pageTemplate').value=" + json.dumps(template)
                       + ";$('templateFormat').value='move';$('templateVisible').checked=true;"
                         "$('pageTemplate').dispatchEvent(new Event('change'))")
                    editor.apply(json.loads(js(view, 'JSON.stringify(queue[0])')))
                    js(view, update_script(editor.state()))
                change_template('Logistics Cornell notes')
                parent_id = book.pages[editor.index].id
                parent_ink = book.page(editor.index).to_bytes()
                js(view, "send({op:'add-page'})")
                editor.apply(json.loads(js(view, 'JSON.stringify(queue[0])')))
                js(view, update_script(editor.state()))
                assert js(view, "$('pageTemplate').value==='Logistics Cornell notes'&&$('templateFormat').value==='move'&&$('templateVisible').checked")
                assert not book.page(editor.index).strokes, 'New page copied handwriting'
                change_template('Logistics Checklist')
                parent = next(i for i, p in enumerate(book.pages) if p.id == parent_id)
                assert book.pages[parent].template == 'Logistics Cornell notes Move', 'Changed another page template'
                assert book.page(parent).to_bytes() == parent_ink, 'Changed another page handwriting'
                report['pdf_highlighter'] = highlight
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
