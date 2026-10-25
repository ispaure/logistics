"""Reusable native Qt canvas/input probe; writes only synthetic local evidence."""
import argparse
import json
from pathlib import Path
import sys
import time

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from features.notebooks.ui.workspace import NotebookWorkspace
from Scripts.build_retention import scratch


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    failed = []
    with scratch() as temporary:
        workspace = NotebookWorkspace(root=temporary / 'notebooks')
        workspace.resize(1000, 850)
        workspace.show()
        workspace.new()
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
            workspace.web.page().runJavaScript("send({op:'undo'})")
            until(lambda: not workspace.editor.notebook.page(0).strokes, redo)

        def redo():
            print('Undo completed', flush=True)
            workspace.web.page().runJavaScript("send({op:'redo'})")
            until(lambda: len(workspace.editor.notebook.page(0).strokes) == 1, add_page)

        def add_page():
            print('Redo completed', flush=True)
            workspace.web.page().runJavaScript("send({op:'add-page'})")
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
                assert book.name == 'Native canvas' and book.page(1).layers[-1][1] == 'Details'
                data = book.to_bytes()
                (output / 'native-canvas.rmdoc').write_bytes(data)
                workspace.editor.index = 0
                workspace.web.page().runJavaScript("send({op:'page',index:0})")
                def capture():
                    workspace.grab().save(str(output / 'desktop-canvas.png'))
                    (output / 'desktop-canvas.json').write_text(json.dumps(dict(status='passed',
                        native_mouse_input=True, brush=12, color=6, undo=True, redo=True,
                        recovered_pages=2, rename=True, add_layer=True, export_bytes=len(data)), indent=2))
                    app.quit()
                qt.QTimer.singleShot(300, capture)
            except Exception as error:
                fail(error)

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
                if sizes['page'] <= 0 or sizes['header'] > sizes['body'] * .55:
                    return fail('Expanded notebook toolbar hides the page: ' + encoded)
                workspace.web.page().runJavaScript("document.querySelector('details').open=false")
                workspace.web.page().runJavaScript("send({op:'stroke',points:[],padding:'x'.repeat(8*1024*1024)});document.getElementById('status').textContent", rejected)
            def rejected(status):
                if 'too large' not in str(status):
                    return fail('Oversized canvas command did not report an error.')
                workspace.web.page().runJavaScript("document.getElementById('tool').value='12';document.getElementById('color').value='6';JSON.stringify(document.getElementById('paper').getBoundingClientRect())", draw)
            qt.QTimer.singleShot(300, ready)

        workspace.web.loadFinished.connect(loaded)
        qt.QTimer.singleShot(30000, lambda: fail('Native canvas probe timed out.'))
        app.exec()
        workspace.close()
    if failed:
        raise RuntimeError('; '.join(failed))
    print('Native desktop drawing, undo/redo, page creation, recovery and export passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output)
