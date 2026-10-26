"""Reusable native Qt canvas/input probe; writes only synthetic local evidence."""
import argparse
import json
from pathlib import Path
import sys
import time

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from features.notebooks.ui.workspace import NotebookWorkspace, NotebookWindow
from features.notebooks.ui.menus import NotebookMenus
from features.notebooks.protocol import update_script
from unittest.mock import patch
from Scripts.build_retention import scratch


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    failed = []
    with scratch() as temporary:
        from desktop.documents import DocumentsPage, register_document_host, show_document
        host = qt.QMainWindow()
        host.setWindowTitle('Logistics host')
        documents = DocumentsPage(lambda: None, host)
        host.setCentralWidget(documents)
        host.resize(1000, 850)
        host.show()
        register_document_host(documents)
        window = NotebookWindow()
        workspace = NotebookWorkspace(window, root=temporary / 'notebooks')
        window.setCentralWidget(workspace)
        window.notebook_menus = NotebookMenus(window)
        show_document(window)
        workspace.new()
        assert window in documents.records
        assert window.windowTitle() == workspace.editor.notebook.name
        assert host.windowTitle() == 'Logistics host'
        started = time.monotonic()

        def fail(error):
            failed.append(str(error))
            app.quit()

        def until(predicate, next_step):
            try:
                if time.monotonic() - started > 25:
                    raise RuntimeError('Native canvas probe timed out; state=' + repr(workspace.editor.state()))
                if predicate():
                    next_step()
                else:
                    qt.QTimer.singleShot(50, lambda: until(predicate, next_step))
            except Exception as error:
                fail(error)

        def draw(bounds):
            try:
                if isinstance(bounds, str):
                    bounds = json.loads(bounds)
                target = workspace.web.focusProxy() or workspace.web
                x, y = int(bounds['x'] + 120), int(bounds['y'] + 80)
                QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x, y))
                QTest.mouseMove(target, qt.QPoint(x + 40, y + 40), delay=20)
                QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=qt.QPoint(x + 40, y + 40))
                until(lambda: len(workspace.editor.notebook.page(0).strokes) == 1, undo)
            except Exception as error:
                fail(error)

        def undo():
            print('Native stroke captured', flush=True)
            stroke = workspace.editor.notebook.page(0).strokes[0]
            if stroke.tool != 12 or stroke.color != 6:
                return fail('Native drawing did not retain the selected brush/color.')
            window.notebook_menus.actions['undo'].trigger()
            until(lambda: not workspace.editor.notebook.page(0).strokes, redo)

        def redo():
            print('Undo completed', flush=True)
            window.notebook_menus.actions['redo'].trigger()
            until(lambda: len(workspace.editor.notebook.page(0).strokes) == 1, add_page)

        def add_page():
            print('Redo completed', flush=True)
            window.notebook_menus.actions['add-page'].trigger()
            until(lambda: len(workspace.editor.notebook.pages) == 2, rename)

        def rename():
            workspace.web.page().runJavaScript("document.getElementById('notebookName').value='Native canvas';document.getElementById('renameNotebook').click()")
            until(lambda: workspace.editor.notebook.name == 'Native canvas', add_layer)

        def add_layer():
            workspace.web.page().runJavaScript("document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
            until(lambda: len(workspace.editor.notebook.page(1).layers) == 2, finish)

        def finish():
            print('Page created', flush=True)
            try:
                book = workspace.repository.open(workspace.key)
                assert len(book.pages) == 2 and len(book.page(0).strokes) == 1
                assert host.windowTitle() == 'Logistics host'
                assert window.windowTitle() == 'Native canvas'
                assert book.name == 'Native canvas' and book.page(1).layers[-1][1] == 'Details'
                data = book.to_bytes()
                (output / 'native-canvas.rmdoc').write_bytes(data)
                workspace.editor.index = 0
                workspace.web.page().runJavaScript("send({op:'page',index:0});send({op:'library'})")
                def capture():
                    workspace.grab().save(str(output / 'desktop-canvas.png'))
                    check_save_shortcut()
                qt.QTimer.singleShot(300, capture)
            except Exception as error:
                fail(error)

        def check_save_shortcut():
            picker_patch = patch('services.documents.ui.editors.choose_editor_resource', return_value=None)
            picker = picker_patch.start()
            # Qt's standard keys map to Command on macOS and Ctrl elsewhere.
            keys = [qt.QKeySequence(qt.QKeySequence.StandardKey.Save)[0],
                    qt.QKeySequence(qt.QKeySequence.StandardKey.SaveAs)[0]]
            host.raise_()
            host.activateWindow()
            workspace.web.setFocus()
            def press(index):
                target = workspace.web.focusProxy() or workspace.web
                key = keys[index]
                QTest.keyClick(target, key.key(), key.keyboardModifiers())
                qt.QTimer.singleShot(250, lambda: checked(index))
            def checked(index):
                if picker.call_count != index + 1:
                    picker_patch.stop()
                    return fail('Native Save/Save As shortcut did not open exactly one save picker: ' + str(picker.call_count))
                if index == 0:
                    return press(1)
                picker_patch.stop()
                workspace.web.page().runJavaScript(update_script(workspace.state(), ''))
                check_zoom_shortcuts()
            qt.QTimer.singleShot(200, lambda: press(0))

        def zoom_snapshot(callback):
            workspace.web.page().runJavaScript("JSON.stringify({zoom:document.getElementById('zoom').value,scale:canvas.getBoundingClientRect().width/state.width,paper:canvas.getBoundingClientRect().toJSON(),viewport:document.getElementById('viewport').getBoundingClientRect().toJSON()})", lambda encoded: callback(json.loads(encoded)))

        def check_zoom_shortcuts():
            def baseline(data):
                initial = data['scale']
                steps = [('Ctrl+=', initial * 1.2),
                         (qt.QKeySequence.StandardKey.ZoomOut, initial),
                         (qt.QKeySequence.StandardKey.ZoomIn, initial * 1.2), ('Ctrl+0', initial)]
                def press(index):
                    key = qt.QKeySequence(steps[index][0])[0]
                    QTest.keyClick(workspace.web.focusProxy() or workspace.web, key.key(), key.keyboardModifiers())
                    qt.QTimer.singleShot(150, lambda: zoom_snapshot(lambda data: checked(index, data)))
                def checked(index, data):
                    if abs(data['scale'] - steps[index][1]) > .0002:
                        return fail('Zoom shortcut changed scale incorrectly: ' + repr((steps[index], data)))
                    if index + 1 < len(steps):
                        return press(index + 1)
                    if data['zoom'] != 'page':
                        return fail('Ctrl/Cmd+0 did not restore Fit Page')
                    workspace.request_ui('zoom', '1')
                    qt.QTimer.singleShot(150, lambda: zoom_snapshot(wheel))
                press(0)
            def wheel(before):
                box = before['viewport']
                x, y = box['left'] + box['width'] / 2, box['top'] + box['height'] / 2
                target = workspace.web.focusProxy() or workspace.web
                event = qt.QWheelEvent(qt.QPointF(x, y), qt.QPointF(target.mapToGlobal(qt.QPoint(int(x), int(y)))),
                    qt.QPoint(), qt.QPoint(0, 120), qt.Qt.MouseButton.NoButton,
                    qt.Qt.KeyboardModifier.ControlModifier, qt.Qt.ScrollPhase.NoScrollPhase, False)
                qt.QApplication.sendEvent(target, event)
                def checked(after):
                    old, new = before['paper'], after['paper']
                    for coordinate, edge, size in [(x, 'left', 'width'), (y, 'top', 'height')]:
                        if abs((coordinate-old[edge])/old[size] - (coordinate-new[edge])/new[size]) > .003:
                            return fail('Modified wheel lost its page anchor: ' + repr((before, after)))
                    if after['scale'] <= before['scale'] or workspace.web.zoomFactor() != 1:
                        return fail('Modified wheel did not zoom only the notebook page: ' + repr(after))
                    script = """(()=>{
let v=document.getElementById('viewport'),r=v.getBoundingClientRect(),x=r.left+v.clientWidth/2,y=r.top+v.clientHeight/2;
let before=canvas.getBoundingClientRect().width;
v.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:120,clientX:x,clientY:y}));
let plain=canvas.getBoundingClientRect().width===before;
for(let modifier of ['ctrlKey','metaKey']){let size=canvas.getBoundingClientRect().width;v.dispatchEvent(new WheelEvent('wheel',{bubbles:true,cancelable:true,deltaY:-80,clientX:x,clientY:y,[modifier]:true}));if(canvas.getBoundingClientRect().width<=size)return false}
setZoom(20);let upper=document.getElementById('zoom').value==='4';setZoom(.001);let lower=document.getElementById('zoom').value==='0.1';setZoom('page');return plain&&upper&&lower;
})()"""
                    def finished(ok):
                        if not ok:
                            return fail('Zoom modifier, ordinary scroll or zoom bounds regression')
                        check_layouts([(1280, 900), (720, 760)])
                    workspace.web.page().runJavaScript(script, finished)
                qt.QTimer.singleShot(200, lambda: zoom_snapshot(checked))
            zoom_snapshot(baseline)

        def check_layouts(sizes):
            if not sizes:
                return check_overview()
            width, height = sizes[0]
            host.resize(width, height)
            def measure():
                workspace.web.page().runJavaScript("JSON.stringify({width:innerWidth,zoom:document.getElementById('zoom').value,toolbarHeight:document.querySelector('header').getBoundingClientRect().height,brushRows:new Set([...document.querySelectorAll('#brushes button')].map(button=>button.offsetTop)).size,swatches:[...document.querySelectorAll('.swatch')].map(b=>({w:b.offsetWidth,h:b.offsetHeight})),inline:Math.abs(document.getElementById('swatches').getBoundingClientRect().top-document.getElementById('brushes').getBoundingClientRect().top)<8,overflow:document.body.scrollWidth>innerWidth,viewport:document.getElementById('viewport').getBoundingClientRect().toJSON(),paper:document.getElementById('paper').getBoundingClientRect().toJSON()})", measured)
            def measured(encoded):
                data = json.loads(encoded)
                if any(dot['w'] != dot['h'] or dot['w'] != 24 for dot in data['swatches']):
                    return fail('Stretched color swatches: ' + encoded)
                if width == 1280 and not data['inline']:
                    return fail('Colors did not share the desktop toolbar row: ' + encoded)
                if (data['overflow'] or data['brushRows'] != 1 or data['toolbarHeight'] > 90
                        or data['viewport']['height'] < 150 or data['zoom'] != 'page'
                        or data['paper']['right'] > data['viewport']['right'] + 1
                        or data['paper']['bottom'] > data['viewport']['bottom'] + 1):
                    return fail('Notebook layout overflow: ' + encoded)
                workspace.grab().save(str(output / f'desktop-{width}.png'))
                if width == 1280:
                    host.grab().save(str(output / 'desktop-host.png'))
                workspace.web.page().runJavaScript("window.notebookUI('toolbar')")
                def focused():
                    workspace.web.page().runJavaScript("JSON.stringify({hidden:getComputedStyle(document.querySelector('header')).display==='none'})", focus_checked)
                def focus_checked(encoded):
                    if json.loads(encoded) != dict(hidden=True):
                        return fail('Focus layout failed: ' + encoded)
                    workspace.web.page().runJavaScript("window.notebookUI('toolbar')")
                    check_layouts(sizes[1:])
                qt.QTimer.singleShot(150, focused)
            qt.QTimer.singleShot(250, measure)

        def check_overview():
            original = [page.id for page in workspace.editor.notebook.pages]
            window.notebook_menus.actions['pages-overview'].trigger()
            def inspect():
                workspace.web.page().runJavaScript("JSON.stringify({open:document.getElementById('pagesDialog').open,count:document.querySelectorAll('#pagePreviews img').length,loaded:[...document.querySelectorAll('#pagePreviews img')].every(img=>img.complete&&img.naturalWidth>0),busy})", inspected)
            def inspected(encoded):
                data = json.loads(encoded)
                if data != dict(open=True, count=2, loaded=True, busy=False):
                    if time.monotonic() - started > 25:
                        return fail('Pages Overview did not load thumbnails: ' + encoded)
                    return qt.QTimer.singleShot(100, inspect)
                workspace.grab().save(str(output / 'desktop-pages-overview.png'))
                workspace.web.page().runJavaScript("document.querySelector('#pagePreviews [data-page=\"1\"]').click()")
                until(lambda: workspace.editor.index == 1, select_first)
            def select_first():
                workspace.request_command(dict(op='page', index=0))
                until(lambda: workspace.editor.index == 0, insert)
            def insert():
                workspace.request_ui('pagesOverview')
                qt.QTimer.singleShot(200, lambda: workspace.web.page().runJavaScript("document.getElementById('overviewAdd').click()"))
                until(lambda: len(workspace.editor.notebook.pages) == 3, inserted)
            def inserted():
                order = [page.id for page in workspace.editor.notebook.pages]
                if order[0] != original[0] or order[2] != original[1] or workspace.editor.index != 1:
                    return fail('Add Page did not insert after current page')
                workspace.request_command(dict(op='undo'))
                until(lambda: len(workspace.editor.notebook.pages) == 2, completed)
            def completed():
                (output / 'desktop-canvas.json').write_text(json.dumps(dict(status='passed',
                    native_mouse_input=True, brush=12, color=6, visual_controls=True, undo=True, redo=True,
                    recovered_pages=2, rename=True, add_layer=True, document_host=True,
                    responsive_widths=[720, 1280], horizontal_toolbar=True, native_menus=True, default_fit_page=True,
                    save_shortcut=True, hidden_toolbar=True, keyboard_modes=True, brush_number_shortcuts=True,
                    zoom_shortcuts=True, anchored_modifier_wheel=True, zoom_bounds=[.1, 4],
                    round_inline_swatches=True, pages_overview=True, thumbnail_selection=True, insert_after_current=True,
                    export_bytes=len(workspace.editor.notebook.to_bytes())), indent=2))
                return app.quit()
            qt.QTimer.singleShot(200, inspect)

        loaded_once = False
        def loaded(ok):
            nonlocal loaded_once
            if loaded_once:
                return  # Intercepted command URLs are intentionally cancelled.
            if not ok:
                return fail('Notebook HTML did not load.')
            loaded_once = True
            def ready():
                workspace.web.page().runJavaScript("document.querySelector('details').open=true;JSON.stringify({header:document.querySelector('header').getBoundingClientRect().height,body:document.body.clientHeight,page:document.getElementById('viewport').clientHeight})", toolbar)
            def toolbar(encoded):
                sizes = json.loads(encoded)
                if sizes['page'] <= 0 or sizes['header'] > sizes['body'] * .18:
                    return fail('Expanded notebook toolbar hides the page: ' + encoded)
                workspace.web.page().runJavaScript("document.querySelector('details').open=false;JSON.stringify({brushes:document.querySelectorAll('#brushes button').length,colors:document.querySelectorAll('#swatches button').length,shortcuts:(()=>{for(let key of ['e','v','b']){document.dispatchEvent(new KeyboardEvent('keydown',{key}));if(eraserDialog.open)$('closeEraser').click()}let draw=document.getElementById('ink').getAttribute('aria-pressed');for(let key of ['9','6'])document.dispatchEvent(new KeyboardEvent('keydown',{key}));return draw==='true'&&Number(document.getElementById('tool').value)===Object.values(state.tools)[5]})()})", check_chrome)
            def check_chrome(encoded):
                chrome = json.loads(encoded)
                if chrome != dict(brushes=9, colors=9, shortcuts=True):
                    return fail('Visual notebook controls failed: ' + encoded)
                workspace.web.page().runJavaScript("send({op:'stroke',points:[],padding:'x'.repeat(8*1024*1024)});document.getElementById('status').textContent", rejected)
            def rejected(status):
                if 'too large' not in str(status):
                    return fail('Oversized canvas command did not report an error.')
                workspace.web.page().runJavaScript("document.querySelector('#brushes [data-value=\"12\"]').click();document.querySelector('#swatches [data-value=\"6\"]').click();document.querySelector('#widths [data-value=\"3\"]').click();JSON.stringify(document.getElementById('paper').getBoundingClientRect())", draw)
            qt.QTimer.singleShot(300, ready)

        workspace.web.loadFinished.connect(loaded)
        qt.QTimer.singleShot(30000, lambda: fail('Native canvas probe timed out.'))
        app.exec()
        window.close()
        host.close()
    if failed:
        raise RuntimeError('; '.join(failed))
    print('Native desktop drawing, undo/redo, page creation, recovery and export passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
