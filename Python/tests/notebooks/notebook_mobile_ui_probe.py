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
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
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
from mobile_build.native_tests.tests.logisticsmobile.notebook_input_checks import INPUT_CHECKS
from features.notebooks.previews import page_previews
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
                    if action['op'] == 'page-previews':
                        self.runJavaScript('window.notebookPagePreviews(' + json.dumps(page_previews(book, action['start'])) + ')')
                    else:
                        editor.apply(action)
                    self.runJavaScript(update_script(editor.state()))
                elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                    failures.append(message)

        view = QWebEngineView()
        page = Page(view)
        native = QWebEngineScript()
        native.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        native.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        native.setSourceCode('window.LogisticsBooxInk={configure(value){window.booxPreviewConfiguration=JSON.parse(value)}};')
        page.scripts().insert(native)
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
        assert json.loads(js("JSON.stringify([...document.querySelectorAll('.brush-card')].map(b=>Number(b.dataset.tool)))")) == [15, 17, 18, 14, 13, 21, 16, 23, 12]
        # Exercise the real mobile config producer without a physical tablet.
        # Android's companion probe checks this boundary against TouchHelper.
        from features.notebooks.brushes import BRUSHES, PALETTE, PEN_COLORS
        import math
        native_previews = []
        for tool in BRUSHES:
            colors = PEN_COLORS if tool in (17, 15) else (BRUSHES[tool]['colors'][0],)
            for color in colors:
                for grayscale in ((False, True) if tool in (17, 15) else (False,)):
                    js("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value=" + repr(str(color)) + ";$('grayscale').checked=" + str(grayscale).lower() + ";document.dispatchEvent(new Event('change'))")
                    QTest.qWait(80)
                    config = json.loads(js('JSON.stringify(window.booxPreviewConfiguration)'))
                    assert config['tool'] == tool and config['color'] == color, config
                    assert config['enabled'] == (tool in (15, 17)), config
                    if config['enabled']:
                        rgb = [int(PALETTE[color][i:i + 2], 16) for i in (1, 3, 5)]
                        if grayscale:
                            rgb = [math.floor(sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722))) + .5)] * 3
                        assert config['argb'] == 0xff000000 + (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]
                    native_previews.append(dict(tool=tool, color=color, grayscale=grayscale, enabled=config['enabled']))
        js("$('tool').value='17';$('tool').onchange();$('color').value='0';$('grayscale').checked=false;document.dispatchEvent(new Event('change'))")
        pointer_report = json.loads(js(POINTER_CHECKS))
        assert pointer_report['palm_motion_ignored']
        input_report = json.loads(js(INPUT_CHECKS))
        assert js('document.querySelectorAll(".brush-card").length') == len(editor.state()['tools'])
        assert js('document.querySelectorAll(".swatch").length') == len(editor.state()['brushes'][17]['colors'])
        reports = []
        for width, height in [(320, 640), (360, 800), (390, 844), (393, 852), (419, 844), (420, 844), (844, 390), (820, 1180), (1180, 820), (320, 390)]:
            view.resize(width, height)
            QTest.qWait(100)
            wait(lambda: js("document.getElementById('viewport').clientHeight===innerHeight && document.getElementById('viewport').scrollWidth<=document.getElementById('viewport').clientWidth"))
            dimensions = json.loads(js('''JSON.stringify({width:innerWidth,height:innerHeight,
                overflow:document.body.scrollWidth>innerWidth,
                page:document.getElementById('viewport').clientHeight,
                bounds:document.getElementById('viewport').getBoundingClientRect().toJSON(),paper:document.getElementById('paper').getBoundingClientRect().toJSON(),scrollWidth:document.getElementById('viewport').scrollWidth,
                controlArea:[...document.querySelectorAll('header')].reduce((area,b)=>{let r=b.getBoundingClientRect();return area+r.width*r.height},0)/(innerWidth*innerHeight),
                targets:[...document.querySelectorAll('.mobile-tools button')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)})'''))
            assert not dimensions['overflow'], dimensions
            assert dimensions['page'] == height, dimensions
            assert dimensions['targets'] and dimensions['controlArea'] < .17, dimensions
            reports.append(dimensions)
            chrome = json.loads(js(CHROME_CHECKS))
            assert chrome['top_toolbar'] and chrome['compact_shortcuts']
            # iOS supplies its close button in the native reader instead.
            js("state.native_close=true;document.querySelector('header button').hidden=true")
            ios_chrome = json.loads(js(CHROME_CHECKS))
            assert ios_chrome['top_toolbar']
            view.grab().save(str(output / f'ios-canvas-{width}x{height}.png'))
            js("state.native_close=false;document.querySelector('header button').hidden=false")
            js("var probeContrastStyle=document.createElement('style');probeContrastStyle.id='probeContrast';probeContrastStyle.textContent=" + json.dumps(EINK_CSS) + ";document.head.append(probeContrastStyle)")
            contrast = json.loads(js(CHROME_CHECKS))
            assert contrast['painted_swatches'] == chrome['painted_swatches']
            js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
            QTest.qWait(80)  # Let Chromium present the opened menu before capturing it.
            view.grab().save(str(output / f'dropdown-eink-{width}x{height}.png'))
            js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
            assert js("getComputedStyle(document.getElementById('draft')).backgroundColor") == 'rgba(0, 0, 0, 0)', 'E-ink styling must not cover saved ink with an opaque drawing overlay'
            js("document.getElementById('probeContrast').remove()")
            js("document.getElementById('brushToggle').click()")
            assert js("document.activeElement.matches('.brush-card[aria-pressed=true]')")
            assert js("[...$('mobileSheet').querySelectorAll('button')].filter(b=>b.getClientRects().length).every(b=>b.getAttribute('aria-label')!=='Close panel')")
            assert js("[...document.querySelectorAll('#mobileSheet .sheet-panel:not([hidden]) h3')].map(h=>h.textContent).join('/')") == 'Brush/Stroke width/Ink color'
            assert js("getComputedStyle(document.querySelector('.brush-grid')).gridTemplateColumns.split(' ').length===3 && getComputedStyle(document.querySelector('.swatches')).gridTemplateColumns.split(' ').length===3")
            assert js("document.querySelector('#mobileSheet').getBoundingClientRect().right<=innerWidth")
            assert js("$('mobileBackdrop').hidden && !$('viewport').inert && !document.querySelector('header').inert")
            assert js("$('mobileSheet').getBoundingClientRect().bottom<=innerHeight && $('mobileSheet').getBoundingClientRect().top>=document.querySelector('header').getBoundingClientRect().bottom")
            view.grab().save(str(output / f'brushes-{width}x{height}.png'))
            js("document.querySelector('[data-tool=\"12\"]').click();document.querySelector('[data-color=\"6\"]').click();document.querySelector('[data-width=\"3\"]').click()")
            assert js("document.getElementById('tool').value+' / '+document.getElementById('color').value+' / '+document.getElementById('width').value") == '12 / 6 / 3'
            js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            assert js("document.getElementById('mobileSheet').hidden")
            assert js("document.activeElement.id") == 'brushToggle'
            view.grab().save(str(output / f'canvas-{width}x{height}.png'))
            js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click()")
            assert js("!$('mobileSheet').style.top && !$('mobileSheet').style.left"), 'Tool anchor must not leak into other panels'
            view.grab().save(str(output / f'notebook-{width}x{height}.png'))
            js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('hideTools').click()")
            assert js("document.body.classList.contains('tools-hidden')")
            assert js("[...document.querySelectorAll('button')].filter(b=>b.getClientRects().length).length") == 1
            assert js("document.getElementById('viewport').clientHeight") == height
            view.grab().save(str(output / f'focus-{width}x{height}.png'))
            js("document.getElementById('restoreTools').click()")
            assert not js("document.body.classList.contains('tools-hidden')")
            assert js("document.getElementById('tool').value+' / '+document.getElementById('color').value+' / '+document.getElementById('width').value") == '12 / 6 / 3'
        # Real hit-tested clicks close either popout, including its own icon.
        view.resize(390, 844)
        QTest.qWait(100)
        def click_element(element):
            center = json.loads(js("JSON.stringify((()=>{const r=(" + element + ").getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})())"))
            QTest.mouseClick(view.focusProxy(), qt.Qt.MouseButton.LeftButton,
                             qt.Qt.KeyboardModifier.NoModifier, qt.QPoint(*map(int, center)))
            QTest.qWait(30)

        for opener, closed in [("$('brushToggle')", "$('mobileSheet').hidden"),
                               ("$('erase')", "!eraserDialog.open")]:
            click_element(opener)
            assert not js(closed)
            if 'erase' in opener:
                assert js("!$('closeEraser').getClientRects().length")
            click_element(opener)
            assert js(closed), 'Tapping the opener must close its panel'
            click_element(opener)
            click_element("$('undo')")
            assert js(closed), 'Outside toolbar click must close the panel'
            for native in (False, True):
                click_element(opener)
                result = js('''(()=>{
                    const capture=canvas.setPointerCapture, originalSend=send, actions=[];
                    canvas.setPointerCapture=()=>{};send=action=>actions.push(action);
                    try {
                        const event=new PointerEvent('pointerdown',{bubbles:true,cancelable:true,
                            pointerId:901,pointerType:'pen',clientX:innerWidth/2,clientY:innerHeight-4,pressure:.5});
                        if (''' + str(native).lower() + ''') canvas.onpointerdown(event);
                        else canvas.dispatchEvent(event);
                        const started=active===901;
                        finish(event);
                        return JSON.stringify({started,op:actions[0]?.op,closed:''' + closed + '''})
                    } finally {canvas.setPointerCapture=capture;send=originalSend}
                })()''')
                result = json.loads(result)
                assert result == dict(started=True, op='stroke' if 'brushToggle' in opener else 'erase', closed=True), result
        js("$('tool').onchange()")
        js("document.getElementById('zoom').value='1.5';document.getElementById('zoom').onchange();document.getElementById('viewport').scrollLeft=90;document.getElementById('viewport').scrollTop=130")
        snapshot = js("JSON.stringify({zoom:document.getElementById('zoom').value,x:document.getElementById('viewport').scrollLeft,y:document.getElementById('viewport').scrollTop})")
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('hideTools').click();document.getElementById('restoreTools').click()")
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
        # Every secondary control survives reparenting; layer/page actions go
        # through the actual command bridge and durable checkpoint.
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('layersToggle').click();document.getElementById('layerName').value='Details';document.getElementById('addLayer').click()")
        wait(lambda: len(book.page(1).layers) == 2)
        wait(lambda: js('busy') is False)
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('pagesToggle').click()")
        wait(lambda: js("document.querySelectorAll('.page-previews button').length") == 2)
        wait(lambda: js('busy') is False)
        js("document.getElementById('prev').click()")
        wait(lambda: editor.index == 0 and js('busy') is False)
        assert js("document.querySelector('.page-previews [aria-current=true]').dataset.page") == '0'
        assert js("document.querySelector('.page-jump input').value") == '1'
        js("document.querySelector('.page-previews [data-page=\"0\"]').click()")
        wait(lambda: editor.index == 0 and js('busy') is False)
        previous_second = book.pages[1].id
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.querySelector('.menu-add-page').click()")
        wait(lambda: len(book.pages) == 3 and js('busy') is False)
        assert editor.index == 1 and book.pages[2].id == previous_second
        assert not js("!!document.getElementById('renameNotebook')")
        restored = repository.open(key)
        assert restored.name == book.name and len(restored.page(0).strokes) == 1
        assert len(restored.page(2).layers) == 2
        # Titles remain plain text even with HTML/template-looking input.
        book.metadata['visibleName'] = '<img src=x onerror=alert(1)> __ICONS__'
        js(update_script(editor.state()))
        assert js("document.getElementById('title').textContent") == book.name
        assert not js("!!document.querySelector('#title img')")
        js("document.querySelector('header button[aria-label=\"Notebook actions\"]').click();document.getElementById('hideTools').click()")
        js(update_script(editor.state(), 'Synthetic save failure'))
        assert js("!document.getElementById('mobileNotice').hidden")
        js("document.querySelector('#mobileNotice button').click()")
        assert js("document.getElementById('mobileNotice').hidden")
        js("document.getElementById('restoreTools').click()")
        (output / 'mobile-ui.json').write_text(json.dumps(dict(status='passed', sizes=reports,
            brush=12, color=6, real_mouse_input=True, undo=True, redo=True,
            focus_mode=True, view_preserved=True, full_viewport=True, error_visible=True,
            pointer=pointer_report,
            input=input_report, native_previews=native_previews, pages=3, thumbnails=True, insert_after_current=True,
            layers=True, browser_owns_rename=True, recovery=True, errors=failures), indent=2))
        view.close()
        view.deleteLater()
        qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
    print('Mobile layout, pressure/history, swipes, dropdown, thumbnails, page insertion, undo/redo and recovery passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    main(parser.parse_args().output)
