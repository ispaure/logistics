"""Exercise the mobile notebook HTML in WebEngine at phone/tablet dimensions.

This checks real browser layout, pointer input and shared bridge round trips;
it does not certify an Android or iOS native host or physical stylus behavior.
"""
import argparse
import json
from pathlib import Path

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
from logistics_build.build_retention import scratch
from tests.notebooks.webengine_driver import javascript, wait_until
from mobile_build.native_tests.tests.logisticsmobile.notebook_pointer_checks import (
    POINTER_CHECKS, POINTER_READY, POINTER_FINGER_CHECKS, POINTER_CLEANUP,
    pointer_report as decode_pointer_report,
)
from mobile_build.native_tests.tests.logisticsmobile.notebook_chrome_checks import CHROME_CHECKS
from mobile_build.native_tests.tests.logisticsmobile.notebook_input_checks import INPUT_CHECKS
from features.notebooks.previews import page_previews
from mobile.palette import EINK_CSS


def check_pointer_input(js):
    """Use the shared two-phase fixture and wait for the real release guard."""
    failure, owned = None, True
    try:
        initial = decode_pointer_report(js(POINTER_CHECKS))
        assert initial.get('release_grace_blocked') is True, initial
        wait_until(lambda: decode_pointer_report(js(POINTER_READY)).get('blocked') is False,
                   'notebook pen-release grace to expire', timeout=3)
        return decode_pointer_report(js(POINTER_FINGER_CHECKS))
    except BaseException as error:
        failure = error
        owned = getattr(error, 'pointer_fixture_owned', True)
        raise
    finally:
        try:
            if owned:
                js(POINTER_CLEANUP)
        except BaseException as cleanup_error:
            if failure is None:
                raise
            failure.add_note('Pointer fixture cleanup also failed: ' + repr(cleanup_error))


def check_toolbar_layout(view, js, wait, output):
    """Keep real controls large and reachable in narrow embedded WebViews."""
    reports = []
    for width, height in [(320, 640), (375, 812), (382, 595), (390, 844)]:
        view.resize(width, height)
        wait(lambda: js('innerWidth') == width)
        dimensions = json.loads(js("""JSON.stringify((()=>{
            const dock=document.querySelector('.mobile-dock'),header=document.querySelector('header');
            dock.scrollLeft=0;
            return {width:innerWidth,overflow:document.body.scrollWidth>innerWidth,
                header:header.getBoundingClientRect().toJSON(),
                buttons:[...document.querySelectorAll('.mobile-tools button')].map(b=>({
                    label:b.getAttribute('aria-label'),rect:b.getBoundingClientRect().toJSON()}))};
        })())"""))
        assert not dimensions['overflow'], dimensions
        assert 0 <= dimensions['header']['left'] and dimensions['header']['right'] <= width, dimensions
        assert len(dimensions['buttons']) == 5, dimensions
        assert all(row['rect']['width'] >= 44 and row['rect']['height'] >= 44
                   for row in dimensions['buttons']), dimensions
        reachable = json.loads(js("""JSON.stringify([...document.querySelectorAll('.mobile-tools button')].map(b=>{
            b.scrollIntoView({block:'nearest',inline:'nearest',behavior:'instant'});
            const dock=document.querySelector('.mobile-dock'),r=b.getBoundingClientRect(),d=dock.getBoundingClientRect();
            return {width:innerWidth,label:b.getAttribute('aria-label'),rect:r.toJSON(),dock:d.toJSON(),
                scrollLeft:dock.scrollLeft,scrollWidth:dock.scrollWidth,clientWidth:dock.clientWidth,
                fullyVisible:r.left>=d.left&&r.right<=d.right,
                hit:document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)?.closest('button')===b};
        }))"""))
        assert all(row['fullyVisible'] and row['hit'] for row in reachable), dict(width=width, initial=dimensions, reachable=reachable)
        assert not js('document.body.scrollWidth>innerWidth')
        dimensions['reachable'] = reachable
        reports.append(dimensions)
        view.grab().save(str(output / f'toolbar-{width}.png'))
    return reports


def main(output, *, palm_only=False, laptop_only=False, native_only=False, toolbar_only=False):
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
                    elif action['op'] != 'document-location':
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
            wait_until(predicate, 'browser state; console errors: ' + repr(failures))

        def js(script):
            result = javascript(view, script)
            if failures:
                raise AssertionError(failures)
            return result

        loaded = []
        view.loadFinished.connect(loaded.append)
        initial_state = editor.state()
        initial_state['native_actions'] = native_only
        view.setHtml(mobile_editor_html(initial_state, bridge.url, console_bridge=True))
        wait(lambda: bool(loaded))
        assert loaded[-1]
        toolbar_reports = []
        if toolbar_only:
            try:
                toolbar_reports = check_toolbar_layout(view, js, wait, output)
                (output / 'toolbar-result.json').write_text(json.dumps(
                    dict(success=True, layouts=toolbar_reports), indent=2))
            finally:
                view.close()
                view.deleteLater()
                qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            return
        if not (native_only or laptop_only or palm_only):
            toolbar_reports = check_toolbar_layout(view, js, wait, output)
            assert js("!document.querySelector('.mobile-tools #capture') && !!document.querySelector('.mobile-tools #select')")
            js("window.notebookNativeAction('view')")
            assert js("$('capture').getClientRects().length>0 && $('mobileSheet').contains($('capture'))")
            js("$('capture').click()")
            assert js("mode==='capture' && $('mobileSheet').hidden")
            js("window.notebookNativeAction('view');$('capture').click()")
            assert js("mode==='ink' && $('mobileSheet').hidden")
        if native_only:
            assert js("document.querySelector('[aria-label=\"Notebook actions\"]').hidden")
            js("window.notebookNativeAction('pages')")
            wait(lambda: js("document.querySelectorAll('.page-previews button').length === 1"))
            assert js("!$('mobileSheet').hidden && $('mobileSheet').dataset.panel === 'pages'")
            js("window.notebookNativeAction('layers')")
            assert js("$('mobileSheet').dataset.panel === 'layers' && !$('layer').hidden")
            js("window.notebookNativeAction('view')")
            assert js("$('mobileSheet').dataset.panel === 'view'")
            js("window.notebookNativeAction('add-page')")
            wait(lambda: len(editor.notebook.pages) == 2)
            wait(lambda: js('!busy'))
            js("active=42;window.notebookNativeAction('add-page');active=null")
            QTest.qWait(100)
            assert len(editor.notebook.pages) == 2
            js("window.notebookNativeAction('hide-tools')")
            assert js("document.body.classList.contains('tools-hidden')")
            js("window.notebookNativeAction('pages')")
            wait(lambda: js("document.querySelectorAll('.page-previews button').length === 2"))
            assert js("!$('mobileSheet').hidden && $('mobileSheet').dataset.panel === 'pages'")
            QTest.qWait(150)
            view.grab().save(str(output / 'native-pages.png'))
            (output / 'native-result.json').write_text(json.dumps(dict(success=True,
                thumbnails=True, layers=True, view=True, queued_add_page=True, pen_contact_guard=True)))
            view.close()
            view.deleteLater()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            return
        if laptop_only:
            from mobile_build.native_tests.tests.logisticsmobile.notebook_laptop_checks import LAPTOP_CHECKS
            assert js("$('zoomControls').hidden"), 'Zoom feedback must start hidden'
            reports = []
            for width, height in [(466, 678), (951, 669), (820, 1180)]:
                view.resize(width, height)
                js('window.notebookFold([.48,.52])')
                QTest.qWait(150)
                viewport_before = json.loads(js("JSON.stringify($('viewport').getBoundingClientRect().toJSON())"))
                js('zoomBy(1.2)')
                assert not js("$('zoomControls').hidden"), 'Actual zoom did not reveal feedback'
                assert json.loads(js("JSON.stringify($('viewport').getBoundingClientRect().toJSON())")) == viewport_before
                reports.append(json.loads(js(LAPTOP_CHECKS)))
                wait(lambda: js("$('zoomControls').hidden"))
                assert json.loads(js("JSON.stringify($('viewport').getBoundingClientRect().toJSON())")) == viewport_before
                reports[-1]['zoom_auto_hidden_without_viewport_shift'] = True
                QTest.qWait(150)
                view.grab().save(str(output / f'laptop-{width}x{height}.png'))
                js('window.notebookFold(null)')
                QTest.qWait(100)
                assert js("$('laptopTools').hidden && $('viewport').getBoundingClientRect().top>=document.querySelector('header').getBoundingClientRect().bottom && $('viewport').getBoundingClientRect().bottom===innerHeight"), js(
                    "JSON.stringify({hidden:$('laptopTools').hidden,classes:document.body.className,viewport:$('viewport').clientHeight,height:innerHeight,body:document.body.getBoundingClientRect().toJSON()})")
                js("$('brushToggle').click()")
                js("window.absentFoldProof=null;window.notebookFold(null);requestAnimationFrame(()=>{window.absentFoldProof=JSON.stringify({open:!$('mobileSheet').hidden,focused:document.activeElement.matches('.brush-card[aria-pressed=true]')})})")
                wait(lambda: bool(js('window.absentFoldProof')))
                assert json.loads(js('window.absentFoldProof')) == dict(open=True, focused=True)
                assert js("!$('mobileSheet').hidden && $('mobileSheet').contains($('tool'))")
                js("document.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))")
            (output / 'laptop-result.json').write_text(json.dumps(dict(success=True, layouts=reports), indent=2))
            view.close()
            view.deleteLater()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            return
        assert js("getComputedStyle(canvas).userSelect") == 'none'
        assert js("(()=>{let event=new Event('contextmenu',{bubbles:true,cancelable:true});canvas.dispatchEvent(event);return event.defaultPrevented})()")
        assert js("(()=>{active=99;let event=new PointerEvent('pointerdown',{pointerId:100,pointerType:'touch',bubbles:true,cancelable:true});canvas.dispatchEvent(event);let blocked=event.defaultPrevented&&active===99;active=null;return blocked})()")
        js("document.activeElement?.blur();let range=document.createRange();range.selectNode($('paperWrap'));let selection=getSelection();selection.removeAllRanges();selection.addRange(range)")
        wait(lambda: js('getSelection().isCollapsed'))
        assert js("let field=document.createElement('input');field.type='text';field.value='Rename me';document.body.append(field);field.focus();field.select();let editable=getComputedStyle(field).userSelect==='text'&&field.selectionEnd===9;field.remove();editable")
        js("""window.probeTitlePointer = (type, x = 10) => $('title').dispatchEvent(
            new PointerEvent(type, {bubbles:true, pointerType:'touch', pointerId:1, isPrimary:true, clientX:x, clientY:10}))""")
        menu = """document.querySelector('header button[aria-label="Notebook actions"]').click()"""
        js(menu)
        for cancel in ("probeTitlePointer('pointerup')", "probeTitlePointer('pointermove', 35)",
                       "window.dispatchEvent(new Event('blur'))", menu):
            js("probeTitlePointer('pointerdown');" + cancel)
            QTest.qWait(600)
            assert not any(action['op'] == 'document-location' for action in received)
        js(menu)
        js("probeTitlePointer('pointerdown')")
        wait(lambda: any(action['op'] == 'document-location' for action in received))
        js("probeTitlePointer('pointerup')")
        js(menu)
        if palm_only:
            pointer = check_pointer_input(js)
            (output / 'palm-result.json').write_text(json.dumps(dict(success=True,
                page_selection_blocked=True, extra_contact_consumed=True, text_fields_editable=True,
                pointer=pointer)))
            view.close()
            view.deleteLater()
            qt.QCoreApplication.sendPostedEvents(None, qt.QEvent.Type.DeferredDelete)
            return
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
                    expected = dict(tool=tool, color=color, enabled=tool in (15, 17))
                    if expected['enabled']:
                        rgb = [int(PALETTE[color][i:i + 2], 16) for i in (1, 3, 5)]
                        if grayscale:
                            rgb = [math.floor(sum(c * w for c, w in zip(rgb, (.2126, .7152, .0722))) + .5)] * 3
                        expected['argb'] = 0xff000000 + (rgb[0] << 16) + (rgb[1] << 8) + rgb[2]
                    js("$('tool').value=" + repr(str(tool)) + ";$('tool').onchange();$('color').value=" + repr(str(color)) + ";$('grayscale').checked=" + str(grayscale).lower() + ";document.dispatchEvent(new Event('change'))")
                    # The native preview producer publishes on a later frame.
                    wait(lambda: js('(()=>{const actual=window.booxPreviewConfiguration;return !!actual&&Object.entries('
                        + json.dumps(expected) + ').every(([key,value])=>actual[key]===value)})()'))
                    config = json.loads(js('JSON.stringify(window.booxPreviewConfiguration)'))
                    assert {key: config[key] for key in expected} == expected, config
                    native_previews.append(dict(tool=tool, color=color, grayscale=grayscale, enabled=config['enabled']))
        js("$('tool').value='17';$('tool').onchange();$('color').value='0';$('grayscale').checked=false;document.dispatchEvent(new Event('change'))")
        pointer_report = check_pointer_input(js)
        assert pointer_report['palm_motion_ignored']
        input_report = json.loads(js(INPUT_CHECKS))
        assert js('document.querySelectorAll(".brush-card").length') == len(editor.state()['tools'])
        assert js('document.querySelectorAll(".swatch").length') == len(editor.state()['brushes'][17]['colors'])
        reports = []
        for width, height in [(320, 640), (360, 800), (390, 844), (393, 852), (419, 844), (420, 844), (844, 390), (820, 1180), (1180, 820), (320, 390)]:
            view.resize(width, height)
            QTest.qWait(100)
            wait(lambda: js("document.getElementById('viewport').getBoundingClientRect().top>=document.querySelector('header').getBoundingClientRect().bottom && document.getElementById('viewport').getBoundingClientRect().bottom===innerHeight && document.getElementById('viewport').scrollWidth<=document.getElementById('viewport').clientWidth"))
            dimensions = json.loads(js('''JSON.stringify({width:innerWidth,height:innerHeight,
                overflow:document.body.scrollWidth>innerWidth,
                page:document.getElementById('viewport').clientHeight,
                bounds:document.getElementById('viewport').getBoundingClientRect().toJSON(),paper:document.getElementById('paper').getBoundingClientRect().toJSON(),scrollWidth:document.getElementById('viewport').scrollWidth,
                controlArea:[...document.querySelectorAll('header')].reduce((area,b)=>{let r=b.getBoundingClientRect();return area+r.width*r.height},0)/(innerWidth*innerHeight),
                targets:[...document.querySelectorAll('.mobile-tools button')].every(b=>b.getBoundingClientRect().width>=44&&b.getBoundingClientRect().height>=44)})'''))
            assert not dimensions['overflow'], dimensions
            assert dimensions['bounds']['top'] >= js("document.querySelector('header').getBoundingClientRect().bottom"), dimensions
            assert dimensions['bounds']['bottom'] == height, dimensions
            assert dimensions['page'] >= height - dimensions['bounds']['top'] - 1, dimensions
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
            assert js("getComputedStyle($('inkLayers')).backgroundColor") == 'rgba(0, 0, 0, 0)', 'E-ink styling must preserve the transparent ink blend group'
            js("document.getElementById('probeContrast').remove()")
            js("document.getElementById('brushToggle').click()")
            js("window.absentFoldProof=null;window.notebookFold(null);requestAnimationFrame(()=>{window.absentFoldProof=JSON.stringify({open:!$('mobileSheet').hidden,focused:document.activeElement.matches('.brush-card[aria-pressed=true]')})})")
            wait(lambda: bool(js('window.absentFoldProof')))
            assert json.loads(js('window.absentFoldProof')) == dict(open=True, focused=True), 'An absent fold update dismissed the brush picker'
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
        # The full-scene canvas can extend left of the phone in Move view;
        # place native mouse input inside its visible clipped paper instead.
        rect = json.loads(js("JSON.stringify(document.getElementById('paperWrap').getBoundingClientRect())"))
        target = view.focusProxy() or view
        point = qt.QPoint(int(rect['x'] + 60), int(rect['y'] + 60))
        assert js(f'document.elementFromPoint({point.x()},{point.y()})===canvas'), \
            ('Native mouse fixture does not hit visible ink', rect)
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
        (output / 'mobile-ui.json').write_text(json.dumps(dict(status='passed', sizes=reports, toolbar=toolbar_reports,
            brush=12, color=6, real_mouse_input=True, undo=True, redo=True,
            focus_mode=True, view_preserved=True, full_viewport=True, error_visible=True,
            absent_fold_preserves_picker=True,
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
    parser.add_argument('--palm-only', action='store_true', help='Only check canvas selection and extra-contact handling.')
    parser.add_argument('--laptop-only', action='store_true', help='Check split tools, drawing coordinates and unfold restoration.')
    parser.add_argument('--native-only', action='store_true', help='Check native toolbar routing to canvas panels and commands.')
    parser.add_argument('--toolbar-only', action='store_true', help='Check actual narrow toolbar targets and scroll reachability only.')
    args = parser.parse_args()
    main(args.output, palm_only=args.palm_only, laptop_only=args.laptop_only, native_only=args.native_only, toolbar_only=args.toolbar_only)
