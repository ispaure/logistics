"""Native Android/iOS creation controls, per-page templates and saved inheritance."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import base64
import json
from hashlib import sha256
from pathlib import Path
from time import monotonic
import traceback

from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window, choose_creation_type
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION
BUNDLE = 'io.github.ispaure.logisticsnotebookqa'


class Probe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / 'template-fixtures'
        super().startup()

    def on_running(self):
        start_native_check(self, self.check)

    async def idle(self, panel):
        for _ in range(200):
            if await panel.web.evaluate_javascript("typeof window.notebookIdle==='function'&&window.notebookIdle()"):
                return
            await asyncio.sleep(.05)
        raise TimeoutError('Notebook command did not finish')

    async def command(self, panel, action):
        await panel.web.evaluate_javascript('send(' + json.dumps(action) + ')')
        await self.idle(panel)

    async def capture_canvas(self, panel, filename):
        web = panel.web
        await web.evaluate_javascript("""window.probePainted = false;
          requestAnimationFrame(() => requestAnimationFrame(() => { window.probePainted = true; })); true""")
        for _ in range(100):
            if await web.evaluate_javascript('window.probePainted === true'):
                # WebView's next presented frame can lag the JS animation frame.
                await asyncio.sleep(.2)
                return await capture_window(self, self.evidence / filename)
            await asyncio.sleep(.05)
        raise TimeoutError('Notebook canvas did not present a frame for evidence.')

    async def template(self, panel, name, paper_format, visible=True):
        await panel.web.evaluate_javascript("window.notebookNativeAction('layers');$('changeTemplate').click();"
            "$('pageTemplate').value=" + json.dumps(name) + ";$('templateFormat').value="
            + json.dumps(paper_format) + ";$('templateVisible').checked=" + json.dumps(visible) + ";"
            "$('pageTemplate').dispatchEvent(new Event('change'));$('applyTemplate').click()")
        await self.idle(panel)
        page = panel.editor.notebook.pages[panel.editor.index]
        expected = name + (' Move' if paper_format == 'move' else ' Pro') if name.startswith('Logistics ') else name
        assert page.template == expected, dict(expected=expected, actual=page.template)

    async def create_notebook(self, title, template, paper_format, *, observe=None):
        from features.notebooks.templates import CATALOG, FORMATS
        await choose_creation_type(self, 'rmdoc')
        picker = self.editor_picker()
        picker.save_as_name.value = title
        controls = picker.notebook_templates
        backend = type(controls.template._impl).__module__
        assert backend.startswith(('toga_iOS.', 'toga_android.')), backend
        picker.show_notebook_template_panel()
        layout = picker.creation_layout
        assert layout.template_panel is not None and controls.parent is layout.template_fields
        controls.template.value = CATALOG[template]
        controls.paper_format.value = FORMATS[paper_format]
        await asyncio.sleep(.3)
        assert controls.selection() == (template, paper_format)
        assert controls.paper_format.enabled
        if template != 'Blank':
            for _ in range(100):
                if controls.preview.image is not None:
                    break
                await asyncio.sleep(.05)
            assert controls.preview.image is not None, 'Template preview did not load'
        template_control = controls.template_list if controls.template_list.parent is controls.choices else controls.template
        native = template_control._impl.native
        if backend.startswith('toga_iOS.'):
            assert native.window is not None and native.bounds.size.height > 0
            description = controls.description._impl.native
            choice_layout = controls.preview_layout._impl.native
            desc_frame = description.convertRect_toView_(description.bounds, controls._impl.native)
            choice_frame = choice_layout.convertRect_toView_(choice_layout.bounds, controls._impl.native)
            assert choice_frame.origin.y + choice_frame.size.height <= desc_frame.origin.y + 1, 'Template description overlaps choices'
        else:
            assert native.isShown() and native.getWidth() > 0 and native.getHeight() > 0
        if observe is None:
            await capture_window(self, self.evidence / (title + '-creation.png'))
        else:
            await observe(picker, controls)
        layout.close_templates(apply=True)
        await picker.choose_creation_location()
        await picker.browser_editor_location(('Local', ''))
        assert picker.picker_primary.enabled, picker.save_as_status.value
        path = picker.editor_provider('Local').root / (title + '.rmdoc')
        await picker.save_text_destination()
        panel = self.notebook_panel
        assert panel.editor.notebook.name == title, picker.save_as_status.value
        await self.idle(panel)
        return panel, path, backend

    async def settled_page(self, panel, landscape):
        web = panel.web
        deadline = monotonic() + 12
        while monotonic() < deadline:
            raw = await web.evaluate_javascript("""JSON.stringify((()=>{
                if (typeof paperBounds !== 'function' || !window.notebookIdle() || resizeFrame !== null ||
                    viewportZoomMemory?.layout !== viewportLayoutKey()) return null;
                const image = $('pdfBackground');
                if (!image.hidden && !image.naturalWidth) return null;
                return {page:paperBounds(), viewport:[innerWidth,innerHeight],
                  artwork:backgroundContentBounds(), background:image.getAttribute('src'),
                  rendered:[$('paperWrap').clientWidth,$('paperWrap').clientHeight]};
            })())""")
            result = json.loads(raw) if raw else None
            if result and (result['viewport'][0] > result['viewport'][1]) == landscape:
                return result
            await asyncio.sleep(.05)
        raise AssertionError('Notebook canvas did not settle in the requested orientation.')

    async def matrix(self, cases):
        from features.notebooks.notebook import Notebook
        from features.notebooks.templates import view_bounds
        from services.documents.mobile_notebooks import close_notebook

        for orientation in ('portrait', 'landscape-left'):
            await rotate(self, orientation)
            landscape = orientation != 'portrait'
            for label, template in [('restaurant', 'Logistics Restaurant review'),
                                    ('lined', 'P Lines medium'), ('blank', 'Blank')]:
                for paper in ('pro', 'move'):
                    title = f'{orientation}-{label}-{paper}'
                    bounds = view_bounds([], paper == 'move')
                    ratio = bounds['width'] / bounds['height']
                    record = dict(orientation=orientation, template=template, format=paper, paper=bounds)
                    cases.append(record)
                    self.show_home()

                    async def observe(picker, controls):
                        image = controls.preview.image
                        size = [int(controls.preview.style.width), int(controls.preview.style.height)]
                        assert abs(size[0] / size[1] - ratio) < .006, size
                        assert (image is None) == (template == 'Blank')
                        record['creation'] = dict(preview=size, image=list(image.size) if image else None,
                                                  image_sha256=sha256(image.data).hexdigest() if image else None)
                        if image is not None:
                            assert abs(image.size[0] / image.size[1] - ratio) < .006, image.size
                            (self.evidence / f'{title}-creation-preview.png').write_bytes(image.data)
                        record['creation']['selector_and_preview_layout'] = str(controls.preview_layout.style.direction)
                        if label == 'restaurant' and paper == 'move':
                            await asyncio.sleep(.2)
                            await capture_window(self, self.evidence / f'{title}-creation.png')

                    panel, path, backend = await self.create_notebook(title, template, paper, observe=observe)
                    record['backend'] = backend
                    created = await self.settled_page(panel, landscape)
                    assert created['page'] == bounds and all(created['rendered']), created
                    record['created'] = {key: value for key, value in created.items() if key != 'background'}
                    if created['background']:
                        record['created']['artwork_sha256'] = sha256(created['background'].encode()).hexdigest()
                    assert (created['background'] is None) == (template == 'Blank')

                    await self.command(panel, dict(op='stroke', tool=17, color=0, width=2,
                                                   points=[[660, 146, .5], [748, 146, .5]]))
                    book = panel.editor.notebook
                    ink = book.page(0).to_bytes()
                    # Change from a different installed background before comparing the staged choice.
                    other = 'P Lines large' if template == 'Blank' else 'Blank'
                    await self.template(panel, other, paper)
                    web = panel.web
                    route = 'layers' if landscape else 'pages'
                    await web.evaluate_javascript("window.notebookNativeAction(" + json.dumps(route) + ");true")
                    await self.idle(panel)
                    before = panel.editor.state()
                    members = book.members.copy()
                    sequence = panel.bridge.sequence
                    open_picker = "$('changeTemplate').click();" if landscape else "$('pageTemplateButton').click();"
                    select_choice = (open_picker + "$('pageTemplate').value=" + json.dumps(template)
                        + ";$('templateFormat').value=" + json.dumps(paper)
                        + ";$('templateVisible').checked=true;updateTemplatePreview();true")
                    await web.evaluate_javascript(select_choice)
                    deadline = monotonic() + 8
                    while monotonic() < deadline:
                        ready = await web.evaluate_javascript("""(() => {
                          const i = $('templatePreview').querySelector('img');
                          return $('templatePicker').open && (i.hidden || (i.complete && i.naturalWidth > 0));
                        })()""")
                        if ready:
                            break
                        await asyncio.sleep(.05)
                    else:
                        raise TimeoutError('Change Template preview did not settle.')
                    observation = json.loads(await web.evaluate_javascript("""JSON.stringify((() => {
                      const d = $('templatePicker'), p = $('templatePreview'), i = p.querySelector('img');
                      const r = p.getBoundingClientRect(), a = i.getBoundingClientRect(), s = $('pageTemplate');
                      return {width:r.width,height:r.height,scale:a.width/r.width,left:(a.left-r.left)/r.width,
                        horizontalOverflow:d.scrollWidth-d.clientWidth, background:i.getAttribute('src'),
                        selectWidth:s.clientWidth, dialogWidth:d.clientWidth,
                        applyEnabled:!$('applyTemplate').disabled};
                    })())"""))
                    pattern = observation.pop('background')
                    assert observation['applyEnabled'] and observation['horizontalOverflow'] <= 1, observation
                    assert abs(observation['width'] / observation['height'] - ratio) < .003, observation
                    assert pattern == created['background']
                    if pattern:
                        assert abs(observation['scale'] - 1404 / bounds['width']) < .003, observation
                        assert abs(observation['left'] + bounds['x'] / bounds['width']) < .003, observation
                    record['change_preview'] = observation
                    if label == 'restaurant' and paper == 'move':
                        await self.capture_canvas(panel, f'{title}-change.png')
                    await web.evaluate_javascript("$('cancelTemplate').click();true")
                    assert await web.evaluate_javascript("!$('templatePicker').open && window.notebookIdle()")
                    assert panel.bridge.sequence == sequence and panel.editor.state() == before and book.members == members
                    record['cancel_unchanged'] = True

                    # Reopen from the still-open sheet after Cancel, and confirm the actual action.
                    await web.evaluate_javascript(select_choice + ";$('applyTemplate').click();true")
                    await self.idle(panel)
                    assert panel.bridge.sequence == sequence + 1
                    applied = await self.settled_page(panel, landscape)
                    assert applied['page'] == bounds and applied.pop('background') == pattern
                    assert book.page(0).to_bytes() == ink and Notebook.read(book.to_bytes()).page(0).to_bytes() == ink
                    record['applied'] = applied
                    record['ink_sha256'] = sha256(ink).hexdigest()
                    if label == 'restaurant' and paper == 'move':
                        await web.evaluate_javascript("$('mobileBackdrop').click();true")
                        await self.capture_canvas(panel, f'{title}-page.png')
                    await self.command(panel, dict(op='save'))
                    assert Notebook.read(path.read_bytes()).page(0).to_bytes() == ink
                    assert close_notebook(self, panel.session.id, 'discard')
        return path.parent

    async def unavailable(self, cases, directory):
        from features.notebooks.notebook import Notebook
        from services.documents.mobile_notebooks import close_notebook, open_notebook
        self.show_home()
        book = Notebook.new('Generated imported template')
        reference = 'Synthetic unavailable restaurant card'
        book.pages[0].template = reference
        book.structure_dirty = True
        path = directory / 'generated-unknown.rmdoc'
        path.write_bytes(book.to_bytes())
        assert await open_notebook(self, path=path)
        panel = self.notebook_panel
        await self.idle(panel)
        result = json.loads(await panel.web.evaluate_javascript("""(() => {
          window.notebookNativeAction('layers');$('changeTemplate').click();
          return JSON.stringify({label:$('pageTemplate').selectedOptions[0]?.textContent,
              message:$('templatePreviewStatus').textContent, disabled:$('applyTemplate').disabled,
              open:$('templatePicker').open});
        })()"""))
        assert result == dict(label=reference + ' (preserved)', message='Template artwork unavailable.',
                              disabled=True, open=True), result
        await self.capture_canvas(panel, 'unknown-template.png')
        await panel.web.evaluate_javascript("$('cancelTemplate').click();true")
        assert panel.editor.notebook.pages[0].template == reference
        cases.append(result)
        assert close_notebook(self, panel.session.id, 'discard')

    async def save_reopen(self, panel, path):
        from features.notebooks.notebook import Notebook
        from services.documents.mobile_notebooks import close_notebook, open_notebook
        await self.command(panel, dict(op='save'))
        assert not panel.document.dirty
        original = Notebook.read(path.read_bytes())
        assert close_notebook(self, panel.session.id, 'discard')
        assert await open_notebook(self, path=path)
        replacement = self.notebook_panel
        assert replacement is not panel
        await self.idle(replacement)
        await replacement.web.evaluate_javascript('window.templateProbePainted=false;requestAnimationFrame(()=>requestAnimationFrame(()=>{window.templateProbePainted=true}));true')
        for _ in range(100):
            if await replacement.web.evaluate_javascript('window.templateProbePainted===true'):
                break
            await asyncio.sleep(.05)
        else:
            raise TimeoutError('Reopened notebook did not paint')
        await asyncio.sleep(.3)
        assert [p.template for p in replacement.editor.notebook.pages] == [p.template for p in original.pages]
        return replacement, original

    async def pdf_highlighter(self, directory):
        from features.notebooks.editor import Editor
        from features.notebooks.notebook import Notebook
        from features.notebooks.remarkable_export import export_rmdoc
        from services.documents.mobile_notebooks import open_notebook

        book = Notebook.new('PDF highlighter')
        editor = Editor(book)
        editor.apply(dict(op='template', name='Logistics Restaurant review', format='pro', visible=True))
        editor.apply(dict(op='stroke', tool=18, color=13, width=1, points=[[500, 173, .5], [900, 173, .5]]))
        data = export_rmdoc(book)
        path = directory / 'PDF highlighter.rmdoc'
        path.write_bytes(data)
        assert Notebook.read(data).page(0).to_bytes() == book.page(0).to_bytes()
        assert await open_notebook(self, path=path)
        panel = self.notebook_panel
        await self.idle(panel)
        for _ in range(100):
            if await panel.web.evaluate_javascript("!!$('pdfBackground').naturalWidth"):
                break
            await asyncio.sleep(.05)
        pixels = json.loads(await panel.web.evaluate_javascript(r"""(()=>{
          draw();
          const pixel=y=>[...ctx.getImageData(Math.floor(700*canvas.width/state.width),
            Math.floor(y*canvas.height/state.height),1,1).data];
          const rule=[171,172,173,174,175].map(pixel).reduce((a,b)=>a[0]<b[0]?a:b);
          return JSON.stringify({plain:pixel(166),rule});
        })()"""))
        assert pixels['plain'][0] >= 245 and pixels['plain'][2] <= 130, pixels
        assert pixels['rule'][0] < pixels['plain'][0] - 10 and pixels['rule'][2] < pixels['plain'][2] - 5, pixels
        await capture_window(self, self.evidence / 'pdf-highlighter.png')
        (self.evidence / path.name).write_bytes(data)
        return dict(name='PDF template rule beneath native yellow ink', pixels=pixels)

    async def check(self, app):
        self.evidence = Path(self.paths.cache) / 'notebook-ui'
        self.evidence.mkdir(exist_ok=True)
        report = dict(success=False, scope='Native creation widgets and actual Android WebView/iOS WKWebView command bridge', cases=[])
        try:
            if getattr(self, 'startup_task', None) is not None:
                await asyncio.shield(self.startup_task)
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            assert not getattr(self, '_startup_in_progress', False), 'Native startup did not finish'
            self.set_feature_enabled('notebooks', True, refresh=False)
            self.show_home()
            # Cancel after choosing paper, then require a fresh default form.
            from features.notebooks.templates import CATALOG, settings
            await choose_creation_type(self, 'rmdoc')
            picker = self.editor_picker()
            picker.notebook_templates.template.value = CATALOG['P Lines large']
            picker.cancel_text_destination()
            assert not list(Path(self.private_root).rglob('*.rmdoc'))

            directory = await self.matrix(report['cases'])
            await rotate(self, 'portrait')
            await self.unavailable(report['cases'], directory)
            self.show_home()

            panel, path, backend = await self.create_notebook('Native lined', 'P Lines medium', 'pro')
            book = panel.editor.notebook
            assert book.pages[0].template == 'P Lines medium'
            await self.command(panel, dict(op='stroke', points=[[690, 150, .5], [750, 150, .5]], tool=17, color=0, width=2))
            first_ink = book.page(0).to_bytes()
            await self.command(panel, dict(op='add-page'))
            assert book.pages[1].template == 'P Lines medium'
            assert not book.page(1).strokes
            await self.template(panel, 'Logistics Checklist', 'move', visible=False)
            assert book.pages[0].template == 'P Lines medium'
            assert book.page(0).to_bytes() == first_ink
            await self.command(panel, dict(op='undo'))
            assert book.pages[1].template == 'P Lines medium'
            await self.command(panel, dict(op='redo'))
            assert book.pages[1].template == 'Logistics Checklist Move'
            await capture_window(self, self.evidence / 'single-page-change.png')
            await self.command(panel, dict(op='add-page'))
            assert book.pages[2].template == 'Logistics Checklist Move'
            assert settings(book, book.pages[2]) == dict(format='move', visible=False)
            assert not book.page(2).strokes
            await self.command(panel, dict(op='undo'))
            assert len(book.pages) == 2
            await self.command(panel, dict(op='redo'))
            assert len(book.pages) == 3 and book.pages[2].template == 'Logistics Checklist Move'
            await capture_window(self, self.evidence / 'inherited-page.png')
            panel, saved = await self.save_reopen(panel, path)
            assert [len(saved.page(i).strokes) for i in range(3)] == [1, 0, 0]
            assert settings(saved, saved.pages[2]) == dict(format='move', visible=False)
            (self.evidence / 'native-lined.rmdoc').write_bytes(path.read_bytes())
            report['cases'].append(dict(name='native lined creation, isolated page edit, inheritance, undo/redo, save/reopen', backend=backend,
                templates=[p.template for p in saved.pages], ink_counts=[1, 0, 0]))

            self.show_home()
            panel, path, backend = await self.create_notebook('Custom Move', 'Logistics Cornell notes', 'move')
            book = panel.editor.notebook
            assert book.pages[0].template == 'Logistics Cornell notes Move'
            await self.command(panel, dict(op='add-page'))
            assert book.pages[1].template == 'Logistics Cornell notes Move'
            await self.template(panel, 'P Lines small', 'pro')
            assert book.pages[0].template == 'Logistics Cornell notes Move'
            await self.command(panel, dict(op='add-page'))
            assert book.pages[2].template == 'P Lines small'
            panel, saved = await self.save_reopen(panel, path)
            await capture_window(self, self.evidence / 'reopened.png')
            (self.evidence / 'custom-move.rmdoc').write_bytes(path.read_bytes())
            report['cases'].append(dict(name='custom Move creation, native replacement, inherited native paper, save/reopen', backend=backend,
                templates=[p.template for p in saved.pages], ink_counts=[len(saved.page(i).strokes) for i in range(3)]))
            report['cases'].append(await self.pdf_highlighter(path.parent))
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
            try:
                await capture_window(self, self.evidence / 'failure.png')
            except Exception:
                pass
        # The generic runners copy this result before deleting their QA app.
        # Inline bounded synthetic artifacts also preserve Android evidence.
        report['artifacts'] = {p.name: base64.b64encode(p.read_bytes()).decode('ascii')
            for p in self.evidence.iterdir() if p.suffix in ('.png', '.rmdoc')}
        (Path(self.paths.cache) / 'notebook-template-result.json').write_text(json.dumps(report))


def main():
    return Probe('Notebook template QA', BUNDLE)
