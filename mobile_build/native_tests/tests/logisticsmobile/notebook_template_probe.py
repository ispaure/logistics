"""Native Android/iOS creation controls, per-page templates and saved inheritance."""
import asyncio
import base64
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window, choose_creation_type

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

    async def template(self, panel, name, paper_format, visible=True):
        await panel.web.evaluate_javascript("$('pageTemplateButton').click();"
            "$('pageTemplate').value=" + json.dumps(name) + ";$('templateFormat').value="
            + json.dumps(paper_format) + ";$('templateVisible').checked=" + json.dumps(visible) + ";"
            "$('pageTemplate').dispatchEvent(new Event('change'))")
        await self.idle(panel)
        page = panel.editor.notebook.pages[panel.editor.index]
        expected = name + (' Move' if paper_format == 'move' else ' Pro') if name.startswith('Logistics ') else name
        assert page.template == expected, dict(expected=expected, actual=page.template)

    async def create(self, title, template, paper_format):
        from features.notebooks.templates import CATALOG, FORMATS
        await choose_creation_type(self, 'rmdoc')
        picker = self.editor_picker()
        picker.save_as_name.value = title
        controls = picker.notebook_templates
        backend = type(controls.template._impl).__module__
        assert backend.startswith(('toga_iOS.', 'toga_android.')), backend
        assert controls.parent is picker.name_view
        controls.template.value = CATALOG[template]
        controls.paper_format.value = FORMATS[paper_format]
        await asyncio.sleep(.3)
        assert controls.selection() == (template, paper_format)
        assert controls.paper_format.enabled == template.startswith('Logistics ')
        native = controls.template._impl.native
        if backend.startswith('toga_iOS.'):
            assert native.window is not None and native.bounds.size.height > 0
        else:
            assert native.isShown() and native.getWidth() > 0 and native.getHeight() > 0
        await capture_window(self, self.evidence / (title + '-creation.png'))
        await picker.choose_creation_location()
        await picker.browser_editor_location(('Local', ''))
        assert picker.picker_primary.enabled, picker.save_as_status.value
        path = picker.editor_provider('Local').root / (title + '.rmdoc')
        await picker.save_text_destination()
        panel = self.notebook_panel
        assert panel.editor.notebook.name == title, picker.save_as_status.value
        await self.idle(panel)
        return panel, path, backend

    async def save_reopen(self, panel, path):
        from features.notebooks.notebook import Notebook
        from features.notebooks.mobile.documents import close_notebook, open_notebook
        await self.command(panel, dict(op='save'))
        assert not panel.document.dirty
        original = Notebook.read(path.read_bytes())
        assert close_notebook(self, panel.session.id, 'discard')
        assert await open_notebook(self, path=path)
        replacement = self.notebook_panel
        assert replacement is not panel
        await self.idle(replacement)
        assert [p.template for p in replacement.editor.notebook.pages] == [p.template for p in original.pages]
        return replacement, original

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

            panel, path, backend = await self.create('Native lined', 'P Lines medium', 'pro')
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
            panel, path, backend = await self.create('Custom Move', 'Logistics Cornell notes', 'move')
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
