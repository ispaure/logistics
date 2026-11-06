"""Native bar geometry and retained action audit with synthetic documents."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import asyncio
from pathlib import Path
import traceback

from .ios_toolbar_probe import ToolbarProbe
from .rotation_checks import pose_snapshot

BUNDLE = 'io.github.ispaure.logisticsconventionsqa'


def native_geometry(app, *, verify=True):
    from mobile.ios_toolbar import vertical_edge
    from rubicon.objc import ObjCClass
    window = app.main_window._impl.native

    def children(value, name):
        result = getattr(value, name)
        return result() if callable(result) else result

    def rect(view):
        value = view.convertRect(view.bounds, toView=window)
        return [round(float(v), 2) for v in
                (value.origin.x, value.origin.y, value.size.width, value.size.height)]

    def visible_rect(view):
        """Intersect real clipping ancestors; collapsed tabs retain old frames."""
        x, y, width, height = rect(view)
        left, top, right, bottom = x, y, x + width, y + height
        ancestor = view
        while ancestor is not None:
            if ancestor.isHidden() or float(ancestor.alpha) < .01:
                return None
            if ancestor == window or ancestor.clipsToBounds or ancestor.layer.masksToBounds:
                x, y, width, height = rect(ancestor)
                left, top = max(left, x), max(top, y)
                right, bottom = min(right, x + width), min(bottom, y + height)
            ancestor = children(ancestor, 'superview')
        return [left, top, right - left, bottom - top] if right > left and bottom > top else None

    def controller(value):
        from rubicon.objc import SEL
        item = value.navigationItem
        compression = (int(item.verticalBarCompressionBehavior)
                       if item.respondsToSelector(SEL('verticalBarCompressionBehavior')) else None)
        return dict(kind=str(value.objc_class.name), frame=rect(value.view), compression=compression,
                    edge=vertical_edge(value),
                    children=[controller(child) for child in children(value, 'childViewControllers')])

    buttons = []
    def views(view, hidden=False):
        hidden = hidden or bool(view.isHidden()) or float(view.alpha) == 0
        if not hidden and view.isKindOfClass(ObjCClass('UIControl')):
            button = dict(kind=str(view.objc_class.name),
                          label=str(view.accessibilityLabel or ''), frame=rect(view))
            button['visible_frame'] = visible_rect(view)
            if button['kind'] in ('_UIButtonBarButton', '_UITabButton'):
                from rubicon.objc import CGPoint
                x, y, width, height = button['frame']
                hit = window.hitTest(CGPoint(x + width / 2, y + height / 2), withEvent=None)
                button['hit_target'] = bool(hit is not None and hit.isDescendantOfView(view))
            buttons.append(button)
        for child in children(view, 'subviews'):
            views(child, hidden)
    views(window)
    from rubicon.objc import SEL
    occlusions = []
    if window.respondsToSelector(SEL('reservedRegionsOfKind:options:')):
        kind = ObjCClass('UIViewReservedRegionKind').occlusionRegionKind()
        regions = ObjCClass('NSMutableArray').arrayWithArray(window.reservedRegionsOfKind(kind, options=0))
        for region in regions:
            r = region.frame
            occlusions.append([float(r.origin.x), float(r.origin.y), float(r.size.width), float(r.size.height)])
    navigation = app.native_host.adapter.navigation_for(app.native_host.state.destination)
    outer = app.native_host.adapter.outer_navigation
    if not outer.isNavigationBarHidden():
        navigation = outer
    nav = navigation.topViewController.navigationItem
    groups = [*nav.leadingItemGroups, *nav.trailingItemGroups]
    if nav.pinnedTrailingGroup is not None:
        groups.append(nav.pinnedTrailingGroup)
    if navigation.isNavigationBarHidden():
        groups = []
    items = []
    for group in groups:
        for item in group.barButtonItems:
            # QA-only inspection of UIKit's view for the public bar item.
            view = item.valueForKey('view')
            if view is None or view.window is None or view.isHidden():
                continue
            bounds = rect(view)
            if bounds[2] <= 0 or bounds[3] <= 0:
                continue
            items.append(dict(label=str(item.accessibilityLabel or item.title or ''), frame=bounds,
                              visible_frame=visible_rect(view)))
    header_items, collisions = [], []
    body = app.routes.body()
    view = body.children[0] if body.children else None
    reader_header = getattr(view, '_reader_top_band_state', None)
    home_header = getattr(view, '_home_top_band', None)
    destination_header = getattr(view, '_destination_top_band', None)
    controls = (reader_header['buttons'] if reader_header else home_header['row'].children if home_header
                else destination_header['buttons'] if destination_header else ())
    for button in controls:
        native = button._impl.native
        if native.window is not None and not native.isHidden():
            bounds = rect(native)
            from rubicon.objc import CGPoint
            hit = window.hitTest(CGPoint(bounds[0] + bounds[2] / 2, bounds[1] + bounds[3] / 2), withEvent=None)
            item = dict(label=str(native.accessibilityLabel or getattr(button, 'text', '')),
                        frame=bounds, hit_target=bool(hit is not None and hit.isDescendantOfView(native)))
            header_items.append(item)
            if min(bounds[2:]) < 44 or not item['hit_target']:
                collisions.append(('Header action is not a reachable 44pt target', item))
    bars = [button for button in buttons if button['kind'] == '_UIButtonBarButton' and button['visible_frame']]
    for item in [*items, *bars, *header_items]:
        frame = item.get('visible_frame', item['frame'])
        if frame is None:
            continue
        x, y, width, height = frame
        for left, top, w, h in occlusions:
            overlap = (min(x + width, left + w) - max(x, left),
                       min(y + height, top + h) - max(y, top))
            if min(overlap) > 1:
                collisions.append(('Native action overlaps system UI', item, occlusions))
    # System overflow and Back are not necessarily in our explicit item groups.
    # Include their control frames when checking the shared vertical bar against
    # destination tabs; checking only the Island misses action/tab collisions.
    tabs = [button for button in buttons if button['kind'] == '_UITabButton' and button['visible_frame']]
    for button in bars:
        x, y, width, height = button['visible_frame']
        for tab in tabs:
            left, top, w, h = tab['visible_frame']
            overlap = (min(x + width, left + w) - max(x, left),
                       min(y + height, top + h) - max(y, top))
            if min(overlap) > 1:
                collisions.append(('Native action overlaps destination tab', button, tab))
    containers = []
    for container, _ in app.native_host.adapter.containers:
        containers.append(dict(frame=rect(container.native),
            safe=[float(getattr(container.native.safeAreaInsets, side)) for side in ('top', 'left', 'bottom', 'right')],
            applied=[float(getattr(container, side + '_inset')) for side in ('top', 'left', 'bottom', 'right')]))
    result = dict(controllers=controller(window.rootViewController), buttons=buttons,
                items=items, occlusions=occlusions, pose=pose_snapshot(app),
                containers=containers, header_items=header_items, collisions=collisions)
    if verify:
        assert not collisions, collisions
    return result


class ConventionsProbe(ToolbarProbe):
    def on_running(self):
        from rubicon.objc import ObjCClass
        arguments = [str(arg) for arg in ObjCClass('NSProcessInfo').processInfo.arguments]
        self.sweep = '--sweep' in arguments
        self.extended = '--extended' in arguments
        self.extended_only = '--extended-only' in arguments
        super().on_running()

    async def check(self):
        if not self.extended_only:
            await super().check()
            return
        self.output = Path(self.paths.cache) / 'toolbar-qa'
        self.output.mkdir(exist_ok=True)
        self.report = dict(success=False, screens=[], checks=[])
        try:
            await asyncio.sleep(1)
            self.show_home()
            assert self.create_chosen_document('md', name='Companion.md', content='# Companion')
            await self.additional_checks()
            self.report['success'] = True
        except BaseException:
            self.report['error'] = traceback.format_exc()
        (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))

    def check_close(self, sample):
        body = self.routes.body()
        view = body.children[0] if body.children else None
        close = getattr(view, '_reader_close_button', None)
        if close is not None and not getattr(view, '_reader_fullscreen', False):
            label = str(getattr(close, 'accessible_name', None) or close._impl.native.accessibilityLabel)
            if getattr(view, '_reader_top_band_state', None) is not None:
                assert any(row['label'] == label and row['frame'][2] >= 44 and row['frame'][3] >= 44
                           for row in sample['native']['buttons']), sample
                return
            assert sample['leading'] and sample['leading'][0] == label, sample

    async def record(self, name):
        sample = await super().record(name)
        sample['native'] = native_geometry(self)
        self.check_close(sample)
        if self.sweep:
            from .rotation_checks import rotate, panel_state
            expected = panel_state(self)
            for orientation in ('landscape-left', 'landscape-right', 'portrait'):
                await rotate(self, orientation)
                self.resize_workspace()
                await asyncio.sleep(.2)
                assert panel_state(self) == expected, (name, orientation, 'state changed')
                row = await super().record(name + '-' + orientation)
                row['native'] = native_geometry(self)
                self.check_close(row)
        (self.output / 'progress.json').write_text(json.dumps(self.report, indent=2))
        if name == 'editor-dirty':
            for destination in ('documents', 'files'):
                self.show_documents(edit=True, destination=destination)
                from .rotation_checks import rotate
                for orientation in (('landscape-left', 'landscape-right', 'portrait') if self.sweep else (None,)):
                    if orientation is not None:
                        await rotate(self, orientation)
                    for step in ('opened', 'refreshed'):
                        self.adaptive.render()
                        row = await super().record('-'.join(filter(None, ('editor', destination, orientation, step))))
                        row['native'] = native_geometry(self)
                        self.check_close(row)
                        columns = getattr(self.adaptive, 'file_columns', None)
                        if destination == 'files' and columns is not None:
                            frame = columns.navigation.view.frame
                            width = columns.controller.view.bounds.size.width
                            assert abs(frame.origin.x) < 1 and abs(frame.size.width - width) < 1, row
            (self.output / 'progress.json').write_text(json.dumps(self.report, indent=2))
        return sample

    async def additional_checks(self):
        if not self.extended:
            return
        self.set_feature_enabled('notebooks', True, refresh=False)
        from services.documents.mobile_notebooks import open_notebook
        from .rotation_checks import assert_visible_controls
        self.show_home()
        assert self.create_chosen_document('txt', name='Conventions.txt', content='Synthetic search fixture')
        self.show_documents(edit=True, destination='documents')
        await self.record('text-editor')
        self.editor_view.toggle_search()
        await self.record('editor-find')
        self.editor_view.toggle_search()
        self.adaptive.toggle('documents')
        await self.record('document-drawer')
        self.adaptive.toggle('documents')
        if self.adaptive.wide:
            other = next(key for key in self.text_views if key != self.workspace.active)
            self.adaptive.pinned = other
            self.adaptive.render()
            await self.record('paired-documents')
            self.adaptive.pinned = None
            self.adaptive.render()
        self.show_home()
        assert await open_notebook(self, destination='documents')
        await self.record('notebook-canvas')
        from commonUtils.runtime.resources.documents import LocalDocuments
        from .fixtures import make_books
        root = Path(self.paths.cache) / 'child-panel-books'
        root.mkdir(exist_ok=True)
        epub, comic = make_books(root)
        for path, kind in ((epub, 'epub'), (comic, 'comic')):
            self.show_home()
            book = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), path)
            assert await self.open_book(book['id'])
            owner = self.readers.active
            owner.set_reading_mode(False)
            owner.show_reader_tools()
            await self.record(kind + '-contents')
            owner.show_library()
            owner.show_book_metadata()
            await self.record(kind + '-metadata')
            owner.show_library()
            if kind == 'epub':
                owner.show_epub_search()
                await self.record('epub-search')
                owner.show_library()
                owner.show_read_aloud()
                await self.record('speech-controls')
                owner.close_read_aloud()
        self.show_settings()
        for title in self.settings_navigation.sections:
            self.show_settings()
            self.settings_navigation.choose(title)
            await self.record('settings-category-' + title.lower().replace(' ', '-'))
        for name, show in (('connections', self.show_cloud_connections),
                           ('import-credentials', self.show_cloud_import),
                           ('smb-connection', self.show_smb_connection),
                           ('saved-files', self.show_saved_files),
                           ('reset-review', self.show_app_reset)):
            self.show_settings()
            show()
            await self.record(name)
            assert_visible_controls(self)
        # Exercise the failed-unlock form from the reported screenshot without
        # touching a real credential package or submitting a password.
        from types import SimpleNamespace
        from unittest.mock import patch
        self.prepare_cloud()
        self.show_locations()
        cache = SimpleNamespace(items={'toolbar-qa': {'zip': 'Synthetic.zip'}})
        with patch.object(self, 'retained_packages', return_value=cache):
            self.show_retained_unlock('toolbar-qa')
        self.credential_unlock_status.text = 'Unlock failed: invalid password or credential ZIP'
        self.main_window._impl.native.endEditing(True)
        await self.record('credential-unlock-error')
        assert_visible_controls(self)
        self.report['checks'].append('extended-panel-inventory')
        self.report['not_applicable'] = ['Collection drive relocation is Android-only; iOS uses system document storage.']


def main():
    return ConventionsProbe('Toolbar conventions QA', BUNDLE)
