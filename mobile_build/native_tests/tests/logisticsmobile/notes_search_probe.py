"""Native independent document/name search controls and retained results."""
import asyncio
import json
from pathlib import Path
import sys
import traceback

from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.testing.stages import TestStage
from mobile.obsidian import open_vault
from .chat_settings_probe import ChatSettingsProbe
from .fixtures import capture_window

TEST_STAGE = TestStage.REGRESSION


def assert_panel_tabs_reachable(owner):
    from rubicon.objc import CGPoint
    window = owner.view.window._impl.native
    for name, button in owner.panel_tabs.items():
        native = button._impl.native
        width, height = native.bounds.size.width, native.bounds.size.height
        assert native.window is not None and not native.isHidden() and width > 0 and height > 0, (
            'Notes tab is missing', owner.panel_tab, name)
        point = native.convertPoint(CGPoint(width / 2, height / 2), toView=window)
        hit = window.hitTest(point, withEvent=None)
        while hit is not None and hit != native:
            hit = hit.superview
        assert hit == native, ('Notes tab is covered', owner.panel_tab, name, point)


async def check_panel_tab_switching(owner):
    pane_children = tuple(owner.tree.children)
    query = owner.search.value
    owner.search.focus()
    await asyncio.sleep(.4)
    assert owner.search._impl.has_focus
    assert_panel_tabs_reachable(owner)
    for name in ('Files', 'Search', 'Files', 'Calendar', 'Search'):
        owner.panel_tabs[name]._impl.native.sendActionsForControlEvents(1 << 6)
        await asyncio.sleep(.4)
        assert owner.panel_tab == name
        assert tuple(owner.tree.children) == pane_children
        assert_panel_tabs_reachable(owner)
    assert owner.search.value == query


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
                if sys.platform == 'ios' and pose.startswith('landscape'):
                    await check_panel_tab_switching(owner)
                    report['native_panel_tabs'] = pose
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
