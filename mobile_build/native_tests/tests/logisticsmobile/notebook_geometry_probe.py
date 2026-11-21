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


async def wait_for_form(web):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        ready = await web.evaluate_javascript(
            "JSON.stringify(!!$('pdfBackground').naturalWidth && resizeFrame === null && !viewportResizePending"
            " && viewportZoomMemory?.layout === viewportLayoutKey())"
        )
        if json.loads(ready):
            return
        await asyncio.sleep(.1)
    raise AssertionError('Notebook form layout did not settle')


MEASURE = """JSON.stringify((()=>{
  const {x,width,height}=paperBounds(), r=canvas.getBoundingClientRect();
  const room=pageViewportSpace(), s=r.width/state.width;
  return {bounds:[x,width,height], scale:s, room,
    artwork:backgroundContentBounds(), landscape:innerWidth>innerHeight,
    scrollLeft:$('viewport').scrollLeft, scrollTop:$('viewport').scrollTop,
    mark:coord({clientX:r.left+600*s,clientY:r.top+173*r.height/state.height,
      pointerType:'mouse'}).slice(0,2), ink:state.strokes[0].points[0].slice(0,2)};
})())"""


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
            assert await open_notebook(app)
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
                    for orientation in ('portrait', 'landscape-left', 'portrait'):
                        await rotate(app, orientation)
                        await wait_for_form(panel.web)
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
