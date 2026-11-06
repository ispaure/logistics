"""Native Notes Library action wiring and header allocation across device sizes."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from commonUtils.runtime.resources.local import LocalFiles
from mobile.obsidian import open_vault
from .notes_drawers_probe import NotesDrawersProbe
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class NotesHeaderProbe(NotesDrawersProbe):
    def assert_breadcrumb_end(self, owner):
        scroll = owner.breadcrumb_scroll
        assert abs(scroll.horizontal_position - scroll.max_horizontal_position) <= 1, (
            'Breadcrumb did not reveal the end after layout',
            scroll.horizontal_position, scroll.max_horizontal_position)

    async def probe(self):
        from rubicon.objc import CGPoint
        output = Path(self.paths.cache)
        report = dict(success=False, samples=[], native_breadcrumb_swipes=False)
        drive_touches = (output / 'drive-notes-touches').exists()
        owner = None
        try:
            root = output / 'Art'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Home.md').write_text('# Home\n\n[[Other]]\n')
            (root / 'Other.md').write_text('# Other\n\n[[Home]]\n')
            folder = root / '3D Character Art'
            folder.mkdir(exist_ok=True)
            (folder / '3D Character Art.md').write_text(
                '# Character Art Team\n\nProducer: Diane Guillemont\n\n'
                'Lead Character Artist: Chad Emond\n\n## Pages\n\n[[../Home]]\n\n'
                '## Naming conventions\n\nKeep shared files organized by project.\n')
            deep = folder
            for name in ('Illustrations and environments', 'Reference images for production',
                         'Character outlines and colour palettes', 'Works in progress for this release'):
                deep /= name
            deep.mkdir(parents=True)
            deep_note = deep / 'Deeply nested.md'
            deep_note.write_text('# Deeply nested')
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.5)
                assert await owner.open_note('Home.md')
                await self.check_note_actions(owner, report)
                assert await owner.open_note('3D Character Art/3D Character Art.md')
                await asyncio.sleep(.5)
                assert owner.secondary.parent is not None
                assert owner.breadcrumb_scroll.parent is owner.secondary
                window = self.main_window._impl.native
                scroll = owner.breadcrumb_scroll
                self.assert_breadcrumb_end(owner)
                scroll.horizontal_position = 0
                await asyncio.sleep(.35)
                root_button = owner.breadcrumbs.children[0]._impl.native
                root_point = root_button.convertPoint(
                    CGPoint(root_button.bounds.size.width / 2, root_button.bounds.size.height / 2), toView=window)
                hit = window.hitTest(root_point, withEvent=None)
                while hit is not None and hit != root_button:
                    hit = hit.superview
                assert hit == root_button, 'Beginning of breadcrumb path is unreachable'
                scroll.horizontal_position = scroll.max_horizontal_position
                await asyncio.sleep(.35)
                for button in (owner.close_button, owner.menu, owner.links_button, *owner.breadcrumbs.children):
                    if not hasattr(button, 'on_press') or not button.enabled:
                        continue
                    native = button._impl.native
                    if hasattr(button, 'breadcrumb_folder'):
                        viewport = owner.breadcrumb_scroll._impl.native
                        rect = native.convertRect(native.bounds, toView=viewport)
                        center = float(rect.origin.x + rect.size.width / 2)
                        if not float(viewport.bounds.origin.x) <= center <= float(viewport.bounds.origin.x + viewport.bounds.size.width):
                            continue
                    point = native.convertPoint(CGPoint(native.bounds.size.width / 2,
                                                        native.bounds.size.height / 2), toView=window)
                    hit = window.hitTest(point, withEvent=None)
                    while hit is not None and hit != native:
                        hit = hit.superview
                    assert hit == native, ('Header control is covered', getattr(button, 'accessible_name', button.text))
                header = owner.view._document_title_header
                title = owner.view._document_title_view
                title_frame = title.convertRect(title.bounds, toView=window)
                article_frame = owner.web._impl.native.convertRect(owner.web._impl.native.bounds, toView=window)
                for button in (owner.close_button, owner.menu, owner.links_button):
                    control = button._impl.native
                    rect = control.convertRect(control.bounds, toView=window)
                    assert abs(float(rect.size.width) - owner.back_button.style.width) <= 1
                    midpoint = rect.origin.y + rect.size.height / 2
                    assert title_frame.origin.y <= midpoint <= title_frame.origin.y + title_frame.size.height
                assert title_frame.origin.y + title_frame.size.height <= article_frame.origin.y
                assert header.parent is (owner.article if owner.sidebar.expanded else owner.view)
                await capture_window(self, output / ('notes-reading-' + orientation + '.png'))
                if drive_touches:
                    assert await owner.open_note(deep_note.relative_to(root).as_posix())
                    await asyncio.sleep(.6)
                    assert scroll.max_horizontal_position > 20
                    self.assert_breadcrumb_end(owner)
                    for direction in (1, -1):
                        before = scroll.horizontal_position
                        await self.real_swipe(owner, direction, strip=scroll)
                        assert (before - scroll.horizontal_position) * direction > 5, (
                            direction, before, scroll.horizontal_position)
                        assert owner.sidebar.side is None, ('Breadcrumb swipe opened a drawer', direction, owner.sidebar.side)
                    for _ in range(100):
                        if await owner.web.evaluate_javascript(
                                'window.notesDrawersBase===' + json.dumps(owner.base)
                                + ' && document.readyState==="complete"'):
                            break
                        await asyncio.sleep(.05)
                    else:
                        raise AssertionError('Document swipe handlers did not load')
                    await self.real_swipe(owner, -1)
                    assert owner.sidebar.side == 'links', 'Intentional article swipe did not open Links'
                    owner.sidebar.show_detail()
                    owner.sidebar.finish_dismissals()
                    assert await owner.open_note('3D Character Art/3D Character Art.md')
                evidence = output / 'viewer-layout'
                evidence.mkdir(exist_ok=True)
                owner.sidebar.show_sidebar()
                await asyncio.sleep(.3)
                assert list(owner.panel_tabs) == ['Files', 'Search', 'Calendar']
                assert owner.search.parent is owner.search_content
                assert owner.rows_scroll.parent is owner.files_content
                assert owner.tree.children[1:3] == [owner.panel_actions, owner.panel_body]
                assert sum(hasattr(child, 'on_press') for child in owner.panel_actions.children) == 3
                if not owner.sidebar.expanded:
                    overlay = owner.sidebar.overlay
                    assert overlay.edge_panel
                    bounds = overlay.container.native.frame
                    safe = window.safeAreaInsets
                    assert abs(float(bounds.origin.y) - float(safe.top)) < 2
                    assert abs(float(bounds.origin.y + bounds.size.height)
                               - float(window.bounds.size.height - safe.bottom)) < 2
                await capture_window(self, evidence / ('sidebar-files-' + orientation + '.png'))
                owner.select_panel_tab('Search')
                owner.search.value = 'Home'
                await owner.search_task
                await asyncio.sleep(.3)
                assert owner.search_rows
                assert owner.rows_scroll.parent is owner.search_content
                assert owner.panel_actions.parent is owner.tree
                await capture_window(self, evidence / ('sidebar-search-' + orientation + '.png'))
                owner.select_panel_tab('Calendar')
                await owner.calendar_task
                await asyncio.sleep(.3)
                assert owner.panel_body.children == [owner.calendar_scroll]
                await capture_window(self, evidence / ('sidebar-calendar-' + orientation + '.png'))
                owner.select_panel_tab('Files')
                owner.sidebar.show_detail()
                await asyncio.sleep(.3)
                report['samples'].append(dict(orientation=orientation, expanded=owner.sidebar.expanded,
                    title_width=float(title_frame.size.width), document_width=float(article_frame.size.width)))
            owner.close_button._impl.native.sendActionsForControlEvents(1 << 6)
            for _ in range(100):
                if not owner.valid():
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('Inline Close did not dismiss the library')
            report['native_breadcrumb_swipes'] = drive_touches
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if owner is not None:
                owner.dispose()
        (output / 'notes-header-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesHeaderProbe('Notes header QA', 'io.github.ispaure.logisticsnotebookqa')
