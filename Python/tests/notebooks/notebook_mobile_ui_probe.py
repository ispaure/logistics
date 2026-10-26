"""Exercise the mobile notebook HTML in WebEngine at phone/tablet dimensions.

This checks real browser layout, pointer input and shared bridge round trips;
it does not certify an Android or iOS native host or physical stylus behavior.
"""
import argparse
import json
from pathlib import Path
import time

from commonUtils.ui import pyside as qt
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from features.notebooks.bridge import Bridge
from features.notebooks.protocol import update_script
from features.notebooks.mobile.surface import mobile_editor_html
from features.notebooks.notebook import Notebook
from features.notebooks.editor import Editor
from features.notebooks.recovery import Repository
from Scripts.build_retention import scratch
from mobile_build.native_tests.tests.logisticsmobile.notebook_pointer_checks import POINTER_CHECKS
from mobile_build.native_tests.tests.logisticsmobile.notebook_chrome_checks import CHROME_CHECKS
from mobile.palette import EINK_CSS


def main(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    app = qt.QApplication.instance() or qt.QApplication([])
    with scratch() as root:
        repository = Repository(root / 'notebooks')
        book = Notebook.new('Field notes')
        key = repository.create(book)
        editor = Editor(book, lambda book: repository.save(key, book))
        bridge = Bridge()
        failures, received = [], []

        class Page(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, line, source):
                action = bridge.command(message)
                if action:
                    received.append(action)
                    editor.apply(action)
                    self.runJavaScript(update_script(editor.state()))
                elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    failures.append(message)

        view = QWebEngineView()
        page = Page(view)
        view.setPage(page)
        view.resize(390, 844)
        view.show()

        def wait(predicate):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                QTest.qWait(20)
            raise AssertionError('Browser probe timed out: ' + repr(failures))

        def js(script):
            results = []
            page.runJavaScript(script, results.append)
            wait(lambda: bool(results))
            if failures:
                raise AssertionError(failures)
            return results[0]

        loaded = []
        view.loadFinished.connect(loaded.append)
        view.setHtml(mobile_editor_html(editor.state(), bridge.url, console_bridge=True))
        wait(lambda: bool(loaded))
        assert loaded[-1]
        pointer_report = json.loads(js(POINTER_CHECKS))
        assert pointer_report['palm_motion_ignored']
        assert js('document.querySelectorAll(".brush-card").length') == len(editor.state()['tools'])
        assert js('document.querySelectorAll(".swatch").length') == len(editor.state()['brushes'][17]['colors'])
        reports = []
        for width, height in [(320, 640), (390, 844), (844, 390), (820, 1180), (1180, 820), (320, 390)]:
            view.resize(width, height)
            QTest.qWait(100)
            wait(lambda: js("document.getElementById('viewport').clientHeight===innerHeight && document.getElementById('viewport').scrollWidth<=document.getElementById('viewport').clientWidth"))
            dimensions = json.loads(js('''JSON.stringify({width:innerWidth,height:innerHeight,
                overflow:document.body.scrollWidth>innerWidth,
                page:document.getElementById('viewport').clientHeight,
                bounds:document.getElementById('viewport').getBoundingClientRect().toJSON(),paper:document.getElementById('paper').getBoundingClientRect().toJSON(),scrollWidth:document.getElementById('viewport').scrollWidth,
                controlArea:[...document.querySelectorAll('header button,.mobile-dock')].reduce((area,b)=>{let r=b.getBoundingClientRect();return area+r.width*r.height},0)/(innerWidth*innerHeight),
                targets:[...document.querySelectorAll('.mobile-tools button')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)})'''))
            assert not dimensions['overflow'], dimensions
            assert dimensions['page'] == height, dimensions
            assert dimensions['targets'] and dimensions['controlArea'] < .17, dimensions
            reports.append(dimensions)
            chrome = json.loads(js(CHROME_CHECKS))
            assert chrome['top_toolbar'] and chrome['compact_shortcuts']
            js("var probeContrastStyle=document.createElement('style');probeContrastStyle.id='probeContrast';probeContrastStyle.textContent=" + json.dumps(EINK_CSS) + ";document.head.append(probeContrastStyle)")
            contrast = json.loads(js(CHROME_CHECKS))
            assert contrast['painted_swatches'] == chrome['painted_swatches']
            js("document.getElementById('probeContrast').remove()")
            js("document.getElementById('brushToggle').click()")
            assert js("document.activeElement.getAttribute('aria-label')") == 'Close panel'
            assert js("document.querySelector('#mobileSheet').getBoundingClientRect().right<=innerWidth")
            view.grab().save(str(output / f'brushes-{width}x{height}.png'))
            js("document.querySelector('[data-tool=\"12\"]').click();document.querySelector('[data-color=\"6\"]').click();document.querySelector('[data-width=\"3\"]').click()")
            assert js("document.getElementById('tool').value+' / '+document.getElementById('color').value+' / '+document.getElementById('width').value") == '12 / 6 / 3'
            js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            assert js("document.getElementById('mobileSheet').hidden")
            assert js("document.activeElement.id") == 'brushToggle'
            view.grab().save(str(output / f'canvas-{width}x{height}.png'))
            js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
            view.grab().save(str(output / f'notebook-{width}x{height}.png'))
            js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            js("document.getElementById('hideTools').click()")
            assert js("document.body.classList.contains('tools-hidden')")
            assert js("[...document.querySelectorAll('button')].filter(b=>b.getClientRects().length).length") == 1
            assert js("document.getElementById('viewport').clientHeight") == height
            view.grab().save(str(output / f'focus-{width}x{height}.png'))
            js("document.getElementById('restoreTools').click()")
            assert not js("document.body.classList.contains('tools-hidden')")
            assert js("document.getElementById('tool').value+' / '+document.getElementById('color').value+' / '+document.getElementById('width').value") == '12 / 6 / 3'
        view.resize(390, 844)
        QTest.qWait(100)
        js("document.getElementById('zoom').value='1.5';document.getElementById('zoom').onchange();document.getElementById('viewport').scrollLeft=90;document.getElementById('viewport').scrollTop=130")
        snapshot = js("JSON.stringify({zoom:document.getElementById('zoom').value,x:document.getElementById('viewport').scrollLeft,y:document.getElementById('viewport').scrollTop})")
        js("document.getElementById('hideTools').click();document.getElementById('restoreTools').click()")
        assert js("JSON.stringify({zoom:document.getElementById('zoom').value,x:document.getElementById('viewport').scrollLeft,y:document.getElementById('viewport').scrollTop})") == snapshot
        js("document.getElementById('zoom').value='fit';document.getElementById('zoom').onchange();document.getElementById('viewport').scrollLeft=0;document.getElementById('viewport').scrollTop=0")
        rect = json.loads(js("JSON.stringify(document.getElementById('paper').getBoundingClientRect())"))
        target = view.focusProxy() or view
        point = qt.QPoint(int(rect['x'] + 60), int(rect['y'] + 60))
        QTest.mousePress(target, qt.Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseMove(target, point + qt.QPoint(30, 40), delay=30)
        QTest.mouseRelease(target, qt.Qt.MouseButton.LeftButton, pos=point + qt.QPoint(30, 40))
        wait(lambda: len(book.page(0).strokes) == 1)
        stroke = book.page(0).strokes[0]
        assert stroke.tool == 12 and stroke.color == 6
        wait(lambda: js('busy') is False)
        js("document.getElementById('undo').click()")
        wait(lambda: not book.page(0).strokes)
        wait(lambda: js('busy') is False)
        js("document.getElementById('redo').click()")
        wait(lambda: len(book.page(0).strokes) == 1)
        wait(lambda: js('busy') is False)
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('pagesToggle').click();document.querySelector('#mobileSheet button[onclick*=add-page]').click()")
        wait(lambda: len(book.pages) == 2)
        wait(lambda: js('busy') is False)
        assert js("document.getElementById('mobileSheet').hidden")
        # Every secondary control survives reparenting; layer/rename actions go
        # through the actual command bridge and durable checkpoint.
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('layersToggle').click();document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
        wait(lambda: len(book.page(1).layers) == 2)
        wait(lambda: js('busy') is False)
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('notebookName').value='Mobile field notes';document.getElementById('renameNotebook').click()")
        wait(lambda: book.name == 'Mobile field notes')
        wait(lambda: js('busy') is False)
        restored = repository.open(key)
        assert restored.name == book.name and len(restored.page(0).strokes) == 1
        assert len(restored.page(1).layers) == 2
        # Titles remain plain text even with HTML/template-looking input.
        book.metadata['visibleName'] = '<img src=x onerror=alert(1)> __ICONS__'
        js(update_script(editor.state()))
        assert js("document.getElementById('title').textContent") == book.name
        assert not js("!!document.querySelector('#title img')")
        js("document.getElementById('hideTools').click()")
        js(update_script(editor.state(), 'Synthetic save failure'))
        assert js("!document.getElementById('mobileNotice').hidden")
        js("document.querySelector('#mobileNotice button').click()")
        assert js("document.getElementById('mobileNotice').hidden")
        js("document.getElementById('restoreTools').click()")
        (output / 'mobile-ui.json').write_text(json.dumps(dict(status='passed', sizes=reports,
            brush=12, color=6, real_mouse_input=True, undo=True, redo=True,
            focus_mode=True, view_preserved=True, full_viewport=True, error_visible=True,
            pointer=pointer_report,
            pages=2, layers=True, rename=True, recovery=True, errors=failures), indent=2))
        view.close()
        view.deleteLater()
        qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    print('Mobile HTML layout, brush choices, pointer drawing, undo/redo, page/layer/rename and recovery passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
