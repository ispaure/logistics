"""Native bar geometry and retained action audit with synthetic documents."""
import json
import asyncio
from pathlib import Path
import traceback

from .ios_toolbar_probe import ToolbarProbe
from .rotation_checks import pose_snapshot

BUNDLE = 'io.github.ispaure.logisticsconventionsqa'


def native_geometry(app):
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

    def controller(value):
        return dict(kind=str(value.objc_class.name), frame=rect(value.view),
                    edge=vertical_edge(value),
                    children=[controller(child) for child in children(value, 'childViewControllers')])

    buttons = []
    def views(view, hidden=False):
        hidden = hidden or bool(view.isHidden()) or float(view.alpha) == 0
        if not hidden and view.isKindOfClass(ObjCClass('UIControl')):
            buttons.append(dict(kind=str(view.objc_class.name),
                                label=str(view.accessibilityLabel or ''), frame=rect(view)))
        for child in children(view, 'subviews'):
            views(child, hidden)
    views(window)
    return dict(controllers=controller(window.rootViewController), buttons=buttons,
                pose=pose_snapshot(app))


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
        self.report['checks'].append('extended-panel-inventory')
        self.report['not_applicable'] = ['Collection drive relocation is Android-only; iOS uses system document storage.']


def main():
    return ConventionsProbe('Toolbar conventions QA', BUNDLE)
