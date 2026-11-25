"""Native WebView acceptance for fitting formatted notebooks and retaining ink."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
from time import monotonic
import traceback

from .notebook_acceptance_checks import signature
from .notebook_probe import NotebookProbe
from .rotation_checks import rotate
from .web_checks import wait_for_text
from .fixtures import capture_window, choose_creation_type


async def wait_for_form(web):
    deadline = monotonic() + 15
    observed = {}
    while monotonic() < deadline:
        observed = json.loads(await web.evaluate_javascript("""JSON.stringify({
            artwork:!!$('pdfBackground').naturalWidth, queued:resizeFrame !== null,
            pending:viewportResizePending, measured:viewportZoomMemory?.layout, current:viewportLayoutKey()
        })"""))
        if (observed['artwork'] and not observed['queued'] and not observed['pending']
                and observed.get('measured') == observed['current']):
            return
        await asyncio.sleep(.1)
    raise AssertionError(f'Notebook form layout did not settle: {observed}')


MEASURE = """JSON.stringify((()=>{
  const {x,width,height}=paperBounds(), r=canvas.getBoundingClientRect();
  const room=pageViewportSpace(), s=r.width/state.width;
  return {bounds:[x,width,height], scale:s, room,
    artwork:backgroundContentBounds(), landscape:innerWidth>innerHeight,
    scrollLeft:$('viewport').scrollLeft, scrollTop:$('viewport').scrollTop,
    mark:coord({clientX:r.left+600*s,clientY:r.top+173*r.height/state.height,
      pointerType:'mouse'}).slice(0,2), ink:state.strokes[0].points[0].slice(0,2)};
})())"""

TOOLBAR = """JSON.stringify((()=>{
  const header=document.querySelector('header'), dock=header.querySelector('.mobile-dock');
  const title=$('notebookIdentity').getBoundingClientRect(), brush=$('brushToggle').getBoundingClientRect();
  const bounds=dock.getBoundingClientRect(), tools=[...dock.querySelectorAll('button')].filter(b=>!b.hidden);
  return {layout:header.dataset.titleLayout, titleVisible:!!title.width,
    beside:title.right<=brush.left && Math.abs(title.y-brush.y)<=4,
    above:title.bottom<=brush.top, count:tools.length, fits:tools.every(b=>{
      const r=b.getBoundingClientRect();
      return r.width>=44 && r.height>=44 && r.top===brush.top &&
        r.left>=bounds.left && r.right<=bounds.right;
    })};
})())"""


HIGH_CONTRAST_TOOLBAR = """JSON.stringify((()=>{
  const header=document.querySelector('header.mobile-head');
  const groups=[...header.querySelectorAll('.mobile-tool-group')];
  const buttons=[...header.querySelectorAll('button.icon')].filter(b=>b.getClientRects().length);
  const active=buttons.find(b=>b.getAttribute('aria-pressed')==='true');
  const style=getComputedStyle(active);
  return {groups:groups.map(group=>group.getAttribute('aria-label')),
    dividers:groups.slice(1).map(group=>getComputedStyle(group,'::before').borderInlineStartWidth),
    flat:buttons.every(b=>getComputedStyle(b).borderTopColor==='rgba(0, 0, 0, 0)'),
    touch:buttons.every(b=>b.getBoundingClientRect().width>=44 && b.getBoundingClientRect().height>=44),
    active:[style.color,style.backgroundColor]};
})())"""


async def capture_contrast_toolbar(app, panel, captures):
    from mobile.appearance import configure_android_eink

    previous = app.preferences.values['android_eink']
    app.preferences.values['android_eink'] = 'true'
    try:
        configure_android_eink(app)
        app.refresh_native_theme()
        for _ in range(40):
            if await panel.web.evaluate_javascript("!!document.querySelector('#logistics-eink')"):
                break
            await asyncio.sleep(.05)
        toolbar = json.loads(await panel.web.evaluate_javascript(HIGH_CONTRAST_TOOLBAR))
        assert toolbar['groups'] == ['Brushes', 'Editing tools', 'Edit history'], toolbar
        assert toolbar['dividers'] == ['1px', '1px'] and toolbar['flat'] and toolbar['touch'], toolbar
        assert toolbar['active'] == ['rgb(255, 255, 255)', 'rgb(0, 0, 0)'], toolbar
        await capture_window(app, captures / 'notebook-toolbar-high-contrast.png')
        return toolbar
    finally:
        app.preferences.values['android_eink'] = previous
        configure_android_eink(app)
        app.refresh_native_theme()


class NotebookGeometryProbe(NotebookProbe):
    async def check(self, app):
        from features.notebooks.mobile.documents import open_notebook
        from features.notebooks.notebook import Notebook
        from services.documents.locations import collection_path

        result = dict(success=False, cases=[])
        try:
            deadline = monotonic() + 40
            while getattr(app, '_startup_in_progress', False) and monotonic() < deadline:
                await asyncio.sleep(.1)
            assert not app._startup_in_progress
            task = getattr(app, 'cloud_startup_task', None)
            if task is not None:
                await task
            app.show_home()
            app.set_feature_enabled('notebooks', True, refresh=False)
            captures = Path(self.paths.cache) / 'notebook-ui'
            captures.mkdir(exist_ok=True)
            await choose_creation_type(app, 'rmdoc')
            picker = app.editor_picker()
            picker.show_notebook_template_panel()
            layout, controls = picker.creation_layout, picker.notebook_templates
            assert layout.template_panel is not None and controls.parent is layout.template_fields
            controls.set_selection('Logistics Restaurant review', 'move')
            for _ in range(80):
                if controls.preview.image is not None:
                    break
                await asyncio.sleep(.05)
            assert controls.preview.image is not None
            report_layout = 'list' if controls.template_list.parent is controls.choices else 'dropdown'
            await capture_window(self, captures / 'new-notebook-template.png')
            layout.close_templates(apply=True)
            assert 'Restaurant review' in picker.notebook_template_button.text
            picker.cancel_text_destination()
            result['creation_template_layout'] = report_layout
            assert await open_notebook(app)
            from features.notebooks.mobile.brush_presets import PREFERENCE
            app.preferences.values[PREFERENCE] = json.dumps([
                dict(id='blue', brush=[17, 6, 2]), dict(id='yellow', brush=[18, 13, 1])])
            root = collection_path(app.private_root)
            root.mkdir(parents=True, exist_ok=True)
            for form, paper_format, bounds in [
                ('Restaurant review', 'move', [291.5, 821, 1460]),
                ('Restaurant review', 'pro', [0, 1404, 1872]),
                ('Checklist', 'move', [291.5, 821, 1460]),
            ]:
                book = Notebook.new(f'{form} {paper_format}', template='Logistics ' + form, paper_format=paper_format)
                book.page(0).add([[600, 173, .5], [700, 173, .5]])
                original = signature(book)
                archive = book.to_bytes()
                source = root / (book.name + '.rmdoc')
                source.write_bytes(archive)
                for stage in ('create', 'reopen'):
                    if stage == 'create':
                        assert await app.notebook_panel.load(lambda: book)
                    else:
                        assert await open_notebook(app, path=source)
                    panel = app.notebook_panel
                    await wait_for_text(panel.web, book.name)
                    if 'high_contrast_toolbar' not in result and type(panel.web._impl).__module__.startswith('toga_android.'):
                        result['high_contrast_toolbar'] = await capture_contrast_toolbar(app, panel, captures)
                    for index, orientation in enumerate(('portrait', 'landscape-left', 'portrait')):
                        await rotate(app, orientation)
                        await wait_for_form(panel.web)
                        if form == 'Restaurant review' and paper_format == 'move' and stage == 'reopen':
                            toolbar = json.loads(await panel.web.evaluate_javascript(TOOLBAR))
                            result.setdefault('toolbar', []).append(dict(orientation=orientation, **toolbar))
                            await capture_window(self, captures / f'notebook-toolbar-{index}.png')
                            if type(panel.web._impl).__module__.startswith('toga_iOS.'):
                                layout = panel.view._notebook_title_layout
                                assert toolbar['layout'] == layout, toolbar
                                controller = app.native_host.adapter.content_controller(app.native_host.state.destination)
                                if layout == 'native':
                                    assert not toolbar['titleVisible'], toolbar
                                    assert controller.navigationItem.titleView == panel.view._document_title_view
                                elif layout == 'inline':
                                    assert toolbar['titleVisible'] and toolbar['beside'], toolbar
                                else:
                                    assert layout == 'stacked' and toolbar['titleVisible'] and toolbar['above'], toolbar
                                    assert toolbar['count'] == 7 and toolbar['fits'], toolbar
                            if index == 0:
                                await panel.web.evaluate_javascript("window.notebookNativeAction('view');"
                                    "$('paperAppearance').value='dark';$('paperAppearance').dispatchEvent(new Event('change'));true")
                                for _ in range(40):
                                    if await panel.web.evaluate_javascript("window.notebookIdle() && darkNotebookPaper()"):
                                        break
                                    await asyncio.sleep(.05)
                                assert panel.paper_appearance == 'dark'
                                assert await panel.web.evaluate_javascript("window.notebookIdle() && darkNotebookPaper()")
                                assert signature(panel.editor.notebook) == original
                                await capture_window(self, captures / 'notebook-dark-paper.png')
                                await panel.web.evaluate_javascript("$('paperAppearance').value='system';"
                                    "$('paperAppearance').dispatchEvent(new Event('change'));true")
                                for _ in range(40):
                                    if await panel.web.evaluate_javascript(
                                            "window.notebookIdle() && $('paperAppearance').value === 'system'"):
                                        break
                                    await asyncio.sleep(.05)
                                assert panel.paper_appearance == 'system'
                                await panel.web.evaluate_javascript("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}));true")
                                assert await panel.web.evaluate_javascript("$('mobileSheet').hidden")
                                result['paper_appearance'] = True
                        value = json.loads(await panel.web.evaluate_javascript(MEASURE))
                        result['cases'].append(dict(form=form, format=paper_format, stage=stage,
                                                    orientation=orientation, **value))
                        assert value['landscape'] == (orientation == 'landscape-left'), value
                        assert value['bounds'] == bounds and value['scrollLeft'] == value['scrollTop'] == 0, value
                        expected = min(value['room']['width'] / bounds[1], value['room']['height'] / bounds[2])
                        assert abs(value['scale'] - expected) < .002, value
                        assert value['artwork'] == dict(x=0, y=0, width=1404, height=1872), value
                        assert value['ink'] == [600, 173] and all(
                            abs(a - b) < .01 for a, b in zip(value['mark'], value['ink'])), value
                        assert signature(panel.editor.notebook) == original
                    result['backend'] = type(panel.web._impl).__module__
                assert source.read_bytes() == archive
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notebook-geometry-result.json').write_text(json.dumps(result, indent=2))


def main():
    return NotebookGeometryProbe('Notebook geometry QA', 'io.github.ispaure.logisticsnotebookqa')
