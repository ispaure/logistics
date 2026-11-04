"""Native independent document/name search controls and retained results."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from .chat_settings_probe import ChatSettingsProbe
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION


class NotesSearchProbe(ChatSettingsProbe):
    async def probe(self, app):
        output = Path(self.paths.cache)
        report = dict(success=False, samples=[])
        owner = None
        try:
            root = self.storage_root / 'Library'
            (root / '.obsidian').mkdir(parents=True)
            (root / 'Plan.md').write_text('# Plan')
            (root / 'Body.md').write_text('Unique phrase in document content')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            owner.search.value = 'Plan'
            await owner.search_task
            names_input, names_rows, names_scroll = owner.search, owner.rows, owner.rows_scroll
            owner.search_mode.value = 'Search within Documents'
            assert owner.search is not names_input and owner.search.value == ''
            owner.search.value = 'Unique phrase'
            await owner.search_task
            assert [row['path'] for row in owner.search_rows] == ['Body.md']
            documents_input, documents_rows = owner.search, owner.rows
            assert documents_rows is not names_rows and owner.rows_scroll is not names_scroll
            for pose in ('portrait', 'landscape-left'):
                await self.rotate_probe(pose)
                owner.sidebar.show_sidebar()
                owner.select_panel_tab('Search')
                for scope, suffix, control, rows, query, path in (
                    ('Search in File Names', 'names', names_input, names_rows, 'Plan', 'Plan.md'),
                    ('Search within Documents', 'documents', documents_input, documents_rows, 'Unique phrase', 'Body.md')):
                    owner.search_mode.value = scope
                    await asyncio.sleep(.3)
                    assert owner.search is control and owner.rows is rows
                    assert owner.search.value == query
                    assert [row['path'] for row in owner.search_rows] == [path]
                    assert owner.search.parent is owner.search_content
                    assert owner.rows_scroll.parent is owner.search_content
                    await capture_window(self, output / f'notes-search-{pose}-{suffix}.png')
                    report['samples'].append(dict(pose=pose, scope=scope, result=path))
            owner.dispose()
            owner = None
            assert names_input.value == documents_input.value == ''
            assert not names_rows.children and not documents_rows.children
            report['success'] = True
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
        (output / 'notes-search-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesSearchProbe('Notes Search QA', 'io.github.ispaure.logisticsstorageqa')
