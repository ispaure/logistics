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

    def assert_duo_header_clearance(self, owner, controller, window):
        from mobile.ios_toolbar import vertical_edge
        edge = vertical_edge(controller)
        if edge not in (1, 2):
            return
        header = owner.view._document_title_header._impl.native
        row = header.convertRect(header.bounds, toView=window)
        assert row.origin.y <= 44, ('Unexpected gap above the Duo header', row.origin.y)
        for button in (owner.menu, owner.links_button, owner.edit, owner.reader_actions_button):
            native = button._impl.native
            rect = native.convertRect(native.bounds, toView=window)
            clearance = (rect.origin.x if edge == 1 else
                         window.bounds.size.width - rect.origin.x - rect.size.width)
            assert clearance >= 80, ('Document control enters the rail', getattr(button, 'accessible_name', button.text), clearance)

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
            long_name = 'Weekly environment art and lighting production references.md'
            (root / long_name).write_text('# Weekly review')
            large = root / 'Large folder'
            large.mkdir()
            for index in range(55):
                (large / f'Note {index:02}.md').write_text('# Note')
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
                for button in (owner.menu, owner.links_button, *owner.breadcrumbs.children):
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
                assert int(title.font.fontDescriptor.symbolicTraits) & 2, 'Notes title is not bold'
                assert owner.reader_actions_button._impl._surface_roles[0] == 'transparent'
                assert owner.menu._impl._surface_roles[0] == ('notes_selection' if owner.sidebar.expanded else 'transparent')
                title_frame = title.convertRect(title.bounds, toView=window)
                article_frame = owner.web._impl.native.convertRect(owner.web._impl.native.bounds, toView=window)
                for button in owner.view._document_title_controls:
                    control = button._impl.native
                    rect = control.convertRect(control.bounds, toView=window)
                    assert abs(float(rect.size.width) - button.style.width) <= 1
                    midpoint = rect.origin.y + rect.size.height / 2
                    assert title_frame.origin.y <= midpoint <= title_frame.origin.y + title_frame.size.height
                assert title_frame.origin.y + title_frame.size.height <= article_frame.origin.y
                assert header.parent is owner.article
                controller = self.native_host.adapter.content_controller(owner.destination)
                from .fixtures import ios_toolbar_items
                from mobile.ios_toolbar import vertical_edge
                close_item = owner.close_button._native_reader_close_item
                if vertical_edge(controller):
                    assert close_item is not None
                    assert ios_toolbar_items(controller, leading=True) == [close_item]
                else:
                    assert close_item is None
                    assert header.children[0] is owner.close_button
                    assert not ios_toolbar_items(controller, leading=True)
                if drive_touches and orientation == 'landscape-left':
                    self.assert_duo_header_clearance(owner, controller, window)
                evidence = output / 'viewer-layout'
                evidence.mkdir(exist_ok=True)
                if owner.sidebar.expanded:
                    tab = owner.panel_tabs['Files']._impl.native
                    tabs_frame = tab.convertRect(tab.bounds, toView=window)
                    if drive_touches and vertical_edge(controller):
                        panel = owner.tree._impl.native
                        frame = panel.convertRect(panel.bounds, toView=window)
                        bottom_gap = window.bounds.size.height - frame.origin.y - frame.size.height
                        assert abs(bottom_gap) <= 2, ('Files panel stops above window bottom', bottom_gap)
                        listing = owner.rows.native_list._impl.native
                        assert listing.contentInset.bottom >= owner.sidebar.files_bottom_extension + 11
                    title_y = float(title_frame.origin.y + title_frame.size.height / 2)
                    assert abs(title_y - float(tabs_frame.origin.y + tabs_frame.size.height / 2)) <= 2
                    await capture_window(self, evidence / ('notes-pane-open-' + orientation + '.png'))
                    owner.sidebar.toggle()
                    await asyncio.sleep(.3)
                    assert not owner.sidebar.expanded
                    assert owner.menu._impl._surface_roles[0] == 'transparent'
                    title = owner.view._document_title_view
                    closed = title.convertRect(title.bounds, toView=window)
                    assert abs(title_y - float(closed.origin.y + closed.size.height / 2)) <= 2
                    if drive_touches:
                        self.assert_duo_header_clearance(owner, controller, window)
                    await capture_window(self, evidence / ('notes-pane-closed-' + orientation + '.png'))
                    owner.sidebar.show_sidebar()
                    await asyncio.sleep(.3)
                await capture_window(self, output / ('notes-reading-' + orientation + '.png'))
                if drive_touches:
                    assert await owner.open_note(deep_note.relative_to(root).as_posix())
                    await asyncio.sleep(.6)
                    shortened = owner._breadcrumbs_shortened
                    if shortened:
                        await capture_window(self, evidence / ('breadcrumbs-fitted-' + orientation + '.png'))
                        await self.real_swipe(owner, 1, strip=scroll)
                        for _ in range(60):
                            if (not owner._breadcrumbs_shortened and scroll.max_horizontal_position > 20
                                    and scroll.horizontal_position <= 1):
                                break
                            await asyncio.sleep(.05)
                        assert not owner._breadcrumbs_shortened, 'Horizontal drag did not expand breadcrumb labels'
                        assert owner.sidebar.side is None
                        assert scroll.horizontal_position <= 1
                        if orientation == 'landscape-left':
                            self.assert_duo_header_clearance(owner, controller, window)
                        await capture_window(self, evidence / ('breadcrumbs-expanded-' + orientation + '.png'))
                    else:
                        self.assert_breadcrumb_end(owner)
                    assert scroll.max_horizontal_position > 20
                    for direction in ((-1, 1) if shortened else (1, -1)):
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
                assert owner.panel_actions.parent is None
                await capture_window(self, evidence / ('sidebar-search-' + orientation + '.png'))
                owner.select_panel_tab('Calendar')
                await owner.calendar_task
                await asyncio.sleep(.3)
                assert owner.panel_body.children == [owner.calendar_scroll]
                assert owner.panel_actions.parent is None
                await capture_window(self, evidence / ('sidebar-calendar-' + orientation + '.png'))
                owner.select_panel_tab('Files')
                assert owner.panel_actions.parent is owner.tree
                owner.sidebar.show_detail()
                await asyncio.sleep(.3)
                report['samples'].append(dict(orientation=orientation, expanded=owner.sidebar.expanded,
                    title_width=float(title_frame.size.width), document_width=float(article_frame.size.width)))
            owner.sidebar.show_sidebar()
            await owner.toggle_folder('Large folder')
            assert owner.rows.recycled
            assert any(row.path == 'Large folder/Note 54.md' for row in owner.rows.native_list.data)
            await owner.toggle_folder('Large folder')
            drawer = owner.sidebar.overlay
            if drawer is not None:
                from toga_iOS.libs import NSIndexPath
                listing = owner.rows.native_list
                entry = next(row for row in listing.data if row.path == long_name)
                native_list = listing._impl.native
                native_list.scrollToRowAtIndexPath(
                    NSIndexPath.indexPathForRow(entry.index, inSection=0), atScrollPosition=2, animated=False)
                await asyncio.sleep(.3)
                cell = native_list.cellForRowAtIndexPath(NSIndexPath.indexPathForRow(entry.index, inSection=0))
                label = cell.wrapping_title
                assert label.numberOfLines == 2
                assert abs(float(label.font.pointSize) - 15) < .1
                assert label.frame.size.height > label.font.lineHeight * 1.5, 'Long note title did not wrap'
                await capture_window(self, evidence / 'notes-files-wrapped-portrait.png')
                pending = asyncio.create_task(owner.file_actions('Home.md'))
                await asyncio.sleep(.3)
                choice = owner.sidebar.action_overlay
                assert choice is not None and owner.sidebar.overlay is drawer
                await capture_window(self, evidence / 'notes-file-actions-portrait.png')
                cancel = choice.panel.content.children[-1]._impl.native
                cancel.sendActionsForControlEvents_(1 << 6)
                await asyncio.wait_for(pending, timeout=5)
                assert owner.sidebar.overlay is drawer and owner.sidebar.side == 'files'
                owner.sidebar.show_detail()
                owner.sidebar.finish_dismissals()
            close = owner.close_button._native_reader_close_item
            if close is None:
                owner.close_button._impl.native.sendActionsForControlEvents_(1 << 6)
            else:
                from rubicon.objc import ObjCClass
                assert ObjCClass('UIApplication').sharedApplication.sendAction_to_from_forEvent_(
                    close.action, close.target, close, None)
            for _ in range(100):
                if not owner.valid():
                    break
                await asyncio.sleep(.05)
            else:
                raise AssertionError('Native Close did not dismiss the library')
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
