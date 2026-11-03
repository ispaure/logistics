"""Native JSON/view execution, refresh and source preservation on both WebViews."""
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from .notes_library_probe import NotesLibraryProbe
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION


class DataViewProbe(NotesLibraryProbe):
    async def probe(self):
        report = dict(success=False)
        evidence = Path(self.paths.cache) / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        owner = None
        try:
            root = Path(self.paths.cache) / ('dataview-' + uuid4().hex)
            (root / '.obsidian').mkdir(parents=True)
            (root / 'views/inventory').mkdir(parents=True)
            data_path = root / '_Resources/dataview/data.json'
            data_path.parent.mkdir(parents=True)
            data_path.write_text('[{"name":"Native JSON","quantity":7}]')
            (root / 'views/inventory/view.js').write_text('await dv.view("views/rows", input);')
            (root / 'views/rows.js').write_text('const rows=JSON.parse(await dv.io.load(input.path));'
                'dv.header(2,"Inventory");dv.table(["Name","Quantity"],rows.map(r=>[r.name,r.quantity]));'
                'dv.list(["Worker complete"]);')
            source = '# Dashboard\n\n```dataviewjs\nawait dv.view("views/inventory", {path:"_Resources/dataview/data"});\n```\n'
            (root / 'Home.md').write_text(source)
            (root / 'Error.md').write_text('```dataviewjs\nJSON.parse(await dv.io.load("missing.json"));\n```\n')
            (root / 'Anchor.md').write_text('# Anchor test\n\n' + 'Paragraph\n\n' * 60
                + '```dataviewjs\ndv.header(2, "Generated target");\n```\n' + '\nTail paragraph\n' * 60)
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            assert await owner.open_note('Home.md')
            assert not await owner.open_note('Missing.md')
            await self.wait_js(owner.web, 'document.body.innerText.includes("Worker complete")')
            report['failed_navigation_kept_view'] = True
            text = await owner.web.evaluate_javascript('document.body.innerText')
            assert 'Native JSON' in text and '7' in text, text
            assert 'Loading data view' not in text, text
            await capture_window(self, evidence / 'notes-dataview.png')
            report['nested_views_json_table_list'] = True
            assert await owner.open_editor()
            await self.wait_js(owner.embedded.formatted.view, '!!window.markdownSnapshot')
            assert owner.embedded.text == source
            assert not owner.embedded.dirty
            assert (root / 'Home.md').read_text() == source
            data_path.write_text('[{"name":"Refreshed JSON","quantity":9}]')
            assert await owner.open_note('Home.md', remember=False), owner.notice.text
            await self.wait_js(owner.web, 'document.body.innerText.includes("Refreshed JSON")')
            report['source_preserved_and_refreshed'] = True
            sessions = set(self.workspace.sessions)
            await owner.load_folder('_Resources/dataview')
            assert any(row['name'] == 'data.json' for row in owner.folders['_Resources/dataview'])
            assert await owner.open_note('_Resources/dataview/data.json')
            assert owner.embedded.kind == 'text'
            assert owner.embedded.view in owner.article.children
            owner.embedded.source.value = '[{"name":"Edited JSON","quantity":11}]'
            owner.embedded.changed(owner.embedded.source.value)
            await asyncio.sleep(.4)
            if not self._is_apple():
                native = owner.embedded.source._impl.native
                assert native.isShown() and native.getHeight() > 0, 'Embedded source input is not visible'
            await capture_window(self, evidence / 'notes-json-editor.png')
            assert await owner.embedded.save(), owner.notice.text
            assert 'Edited JSON' in data_path.read_text()
            assert await owner.open_note('Home.md')
            await self.wait_js(owner.web, 'document.body.innerText.includes("Edited JSON")')
            assert await owner.open_note('views/rows.js', resolve_link=True)
            assert owner.embedded.kind == 'text' and 'dv.table' in owner.embedded.text
            assert set(self.workspace.sessions) == sessions
            report['embedded_json_script_editing'] = True
            assert await owner.open_note('Error.md')
            await self.wait_js(owner.web, 'document.body.innerText.includes("Data view error:")')
            report['errors_visible'] = True
            assert await owner.open_note('Anchor.md', fragment='generated-target')
            await self.wait_js(owner.web, '!!document.getElementById("generated-target")')
            await self.wait_js(owner.web, 'window.scrollY > 100 && Math.abs(document.getElementById("generated-target").getBoundingClientRect().top) < 5')
            report['generated_heading_jump'] = True
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
            if owner is not None:
                report['notice'] = owner.notice.text
                try:
                    report['document'] = await owner.web.evaluate_javascript('document.body.innerText')
                    report['worker'] = await owner.web.evaluate_javascript('window.logisticsDataView?.poll() || "absent"')
                    task = getattr(owner, 'data_view_task', None)
                    report['task'] = repr(task)
                    await capture_window(self, evidence / 'notes-dataview-error.png')
                except Exception:
                    report['diagnostic_error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
            (Path(self.paths.cache) / 'dataview-result.json').write_text(json.dumps(report, indent=2))


def main():
    return DataViewProbe('Logistics Data View QA', 'io.github.ispaure.logisticsnotebookqa')
