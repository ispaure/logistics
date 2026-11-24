"""Focused Documents layout, filename search and shared unlock native acceptance."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from pathlib import Path
import toga
from commonUtils.testing.stages import TestStage
from .document_workspace_probe import DocumentWorkspaceProbe
from .fixtures import capture_window, make_books
from .rotation_checks import rotate, pose_snapshot

TEST_STAGE = TestStage.REGRESSION


def walk(root):
    yield root
    if isinstance(root, toga.ScrollContainer):
        if root.content is not None:
            yield from walk(root.content)
    else:
        for child in root.children:
            yield from walk(child)


class DocumentsHubProbe(DocumentWorkspaceProbe):
    result_name = 'documents-hub-result.json'

    async def run_checks(self, app, report):
        from services.documents.locations import collection_path
        from mobile.incoming_files import inbox_path
        from .sync_status_probe import control_frame
        root = collection_path(self.private_root)
        (root / 'Projects/Notes/.obsidian').mkdir(parents=True, exist_ok=True)
        note = root / 'Projects/Notes/One/Two/QA unique note.md'
        note.parent.mkdir(parents=True)
        note.write_text('# Filename search fixture')
        from mobile.favourites import catalog
        from mobile.workspace import Session
        book, comic = make_books(root, embed_cover=True,
                                 chapter_text='a' * 83, second_chapter_text='b' * 765)
        markdown = root / 'Reading list.md'
        markdown.write_text('Reading list')
        for recent, kind in ((comic, 'comic'), (book, 'epub'), (markdown, 'markdown')):
            name = recent.name
            source = dict(type='local', path=str(recent))
            self.recent_documents.remember_file(Session('', 'file-reference', name, kind, title=name), source)
        catalog(self).remember(dict(type='local', path=str(book)), book.name, dict(kind='epub'), favourite=True)
        (root / 'No match.txt').write_text('QA unique')
        inbox_path(self.private_root).mkdir(parents=True, exist_ok=True)
        (inbox_path(self.private_root) / 'QA unique received.txt').write_text('Received')
        (root / 'Graphic novels').mkdir(exist_ok=True)
        (root / 'remoteConfig.ini').write_text('[LogisticsComics]\nlibraries = Graphic novels\n')
        (root / 'Calibre collection').mkdir(exist_ok=True)
        (root / 'Calibre collection/metadata.db').touch()
        (root / 'Calibre collection/Library.epub').write_bytes(book.read_bytes())
        nested = root / 'Calibre collection/Author/Series'
        nested.mkdir(parents=True)
        for index in range(32):
            (nested / f'Sample {index + 1:02}.txt').write_text('Folder viewport fixture')
        from commonUtils.runtime.resources.local import LocalFiles
        from mobile.document_completion import item_progress
        from services.documents.storage import FileItem
        library_book = FileItem(LocalFiles(root), 'Calibre collection/Library.epub')
        with item_progress(self, library_book, '.epub') as progress:
            assert progress.state.save(dict(page=0, resource=progress.names[0], offset=62, percent=31)) == 'saved'
        if self.routes.apple:
            from .toolbar_conventions_probe import native_geometry
            await self.check_library_root_touches(report, control_frame)
            await self.check_library_folder_rotation(report, control_frame)
            await self.check_workspace_folder_heading(report, control_frame)
            await self.check_notes_library_launch(report)
            await self.check_retained_toolbar_rotation(report, native_geometry)
        self.home_unlock_candidates = lambda: [('synthetic', dict(zip='Synthetic.zip'))]
        report['samples'] = []
        for orientation in ('portrait', 'landscape-left'):
            if not self.routes.apple:
                # The managed tablet viewport needs the owning external driver
                # to acknowledge its real emulator rotation as well.
                (Path(self.paths.cache) / 'creation-orientation').write_text(orientation)
            await rotate(self, orientation, settle=.5)
            positions = []
            for destination, show in (('home', self.show_home), ('files', self.show_locations),
                                       ('documents', self.show_documents_hub)):
                show()
                await asyncio.sleep(.35)
                view = self.routes.roots[destination].children[0]
                _, actions = view._destination_actions
                assert actions[0].accessible_name == 'Unlock LocalCrypt'
                assert not self.routes.screens[destination]
                await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-{destination}.png')
                if self.routes.apple:
                    geometry = native_geometry(self)
                    controls = [*geometry['items'], *geometry['header_items']]
                    unlock = [item for item in controls if item['label'] == 'Unlock LocalCrypt']
                    assert len(unlock) == 1, geometry
                    position = unlock[0]['frame']
                    if geometry['pose']['duo_capable']:
                        self.check_duo_header(view, destination, control_frame, geometry)
                    report['samples'].append(dict(destination=destination, orientation=orientation,
                                                  geometry=geometry))
                else:
                    frame = control_frame(self, actions[0])
                    position = [frame[key] for key in ('x', 'y', 'width', 'height')]
                    report['samples'].append(dict(destination=destination, orientation=orientation, unlock=position))
                positions.append(position)
                if destination == 'home':
                    hub = self.hub_controller()
                    assert [button.text for button in hub._home_recent_buttons] == [
                        'Reading list.md', 'Fixture.epub', 'Fixture.cbz']
                    assert hub._home_recents.parent is hub.home_sections.content
                    assert any(getattr(widget, 'text', '') == 'Your libraries'
                               for widget in walk(hub.home_sections.trailing))
                    shortcuts = hub._home_library_shortcuts
                    bounds = control_frame(self, shortcuts)
                    scroll = hub.home_sections.trailing_scroll if hub.home_sections.paired else hub.home_sections.leading_scroll
                    viewport = control_frame(self, scroll)
                    assert bounds['x'] + bounds['width'] <= viewport['x'] + viewport['width'] + 1, (bounds, viewport)
                    for button in shortcuts.children:
                        button_box = control_frame(self, button)
                        assert button_box['x'] >= bounds['x'] - 1, (bounds, button_box)
                        assert button_box['x'] + button_box['width'] <= bounds['x'] + bounds['width'] + 1, (bounds, button_box)
                    await self.check_thumbnails(hub._home_recents, 2)
                await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-{destination}.png')
            if not self.routes.apple:
                for position in positions[1:]:
                    assert abs(position[0] - positions[0][0]) <= 2, positions
                    assert abs(position[1] - positions[0][1]) <= 2, positions
            assert not hasattr(self.body.children[0], '_workspace_frame')
            report.setdefault('collections', []).append(self.check_collection_frames(control_frame, orientation))
            self.document_view_buttons['Libraries'].on_press()
            await self._notes_discovery_task
            await self.hub_controller()._document_comics_discovery
            await self.hub_controller()._document_books_discovery
            # A synthetic locked copy inserts guidance before the Notes heading.
            assert any(isinstance(widget, toga.Label) and widget.text == 'Notes'
                       for widget in self.document_notes_list.children)
            assert self.document_comics_list.children[0].text == 'Comics'
            assert any(getattr(w, 'text', '') == 'Notes' and isinstance(w, toga.Button)
                       for w in walk(self.document_notes_list))
            assert any(getattr(w, 'text', '') == 'Graphic novels' and isinstance(w, toga.Button)
                       for w in walk(self.document_comics_list))
            assert any(isinstance(w, toga.Button) and w.text == 'Calibre collection'
                       for w in walk(self.document_books_list))
            if self.hub_controller()._document_collection_body.style.direction == 'row':
                library = next(w for w in walk(self.document_books_list)
                               if isinstance(w, toga.Button) and w.text == 'Calibre collection')
                await library.on_press()
                drawer = self.adaptive.browsers['documents']
                hub = self.hub_controller()
                assert hub._document_collection_navigation.parent is drawer.library_sidebar
                assert library._document_library_selected
                if self.routes.apple:
                    assert drawer.page._ios_toolbar_buttons == [drawer.folder_search_button, drawer.folder_actions_button]
                    assert drawer.browser.search_button.parent is None
                assert any(entry.label == 'Library.epub' for entry in drawer.browser.entries)
                await self.check_explorer_completion(drawer.browser, control_frame)
                await capture_window(self, Path(self.paths.cache) / 'documents-hub-library-browser.png')
                drawer.cancel_browser()
            await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-libraries.png')
            assert self.document_search.parent is None
            search = next(button for button in self.routes.body('documents').children[0]._destination_actions[1]
                          if button.accessible_name == 'Search documents')
            search.on_press()
            assert self.document_search.parent is not None
            self.document_search.value = 'QA unique'
            await asyncio.sleep(.4)
            await self.hub_controller()._documents_file_search.task
            assert self.document_views.parent is not None
            names = [w.text for w in walk(self.document_search_results)
                     if isinstance(w, toga.Button) and not hasattr(w, 'document_actions')]
            assert names == ['QA unique note.md', 'QA unique received.txt'], names
            await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-search.png')
            if self.routes.apple:
                self.close_document_search()
            else:
                self._impl.native.getOnBackPressedDispatcher().onBackPressed()
            assert not self.documents_search_open and self.document_search.parent is None
            assert self.document_views.parent is not None
            self.document_view_buttons['Recent'].on_press()
            await self.check_thumbnails(self.document_recent_list, 2)
            self.document_view_buttons['Favourites'].on_press()
            await self.check_thumbnails(self.document_favourites_list, 1)
            self.document_view_buttons['Recent'].on_press()
            if self.routes.apple and geometry['pose']['duo_capable']:
                self.show_settings()
                await asyncio.sleep(.35)
                settings = self.routes.roots['settings'].children[0]
                self.check_duo_header(settings, 'settings', control_frame, native_geometry(self))
                await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-settings.png')
        self.home_unlock_candidates = lambda: []
        self.show_documents_hub()
        await asyncio.sleep(.25)
        if self.routes.apple:
            geometry = native_geometry(self)
            assert not any(item['label'] == 'Unlock LocalCrypt' for item in geometry['items'])
        else:
            _, actions = self.body.children[0]._destination_actions
            assert actions[0].parent is None
        report['pose'] = pose_snapshot(self)
        report['cases'].extend(['filename_only_local_and_received', 'direct_notes_and_comics_lists',
                                'shared_unlock_placement', 'no_documents_hamburger', 'unlock_disappears',
                                'local_epub_and_comic_thumbnails_on_home_recent_and_favourites'])
        if self.routes.apple:
            await self.check_document_browser_search(report, root, control_frame)
            for group, scope in [('Others', 'device'), ('Rclone', 'copies')]:
                self.show_locations()
                owner = self.folder_controller()
                owner.change_folder_source('Local')
                owner.folder_local_group = group
                root_view = self.routes.roots['files'].children[0]
                assert root_view._workspace_search in root_view._ios_toolbar_buttons()
                result = root_view._workspace_search.on_press._raw(root_view._workspace_search)
                await asyncio.sleep(.1)
                panel = self.hub_controller()._document_search_route
                assert panel is not None, dict(group=group, source=owner.folder_source,
                    result=str(result), status=self.status.text,
                    destination=self.native_host.state.destination,
                    routes=list(self.routes.screens['files']), checkpoint=self.checkpoint())
                assert panel.destination == 'files'
                assert self.hub_controller()._documents_file_search.scope == scope
                panel.close()
            report['cases'].append('workspaces_local_subtab_search_without_folder')
            await self.check_workspace_document_chrome(report, root)

    async def check_library_folder_rotation(self, report, frame):
        await rotate(self, 'portrait', settle=.5)
        self.show_documents_hub()
        self.document_view_buttons['Libraries'].on_press()
        hub = self.hub_controller()
        await hub._document_books_discovery
        library = next(w for w in walk(self.document_books_list)
                       if isinstance(w, toga.Button) and w.text == 'Calibre collection')
        await library.on_press()
        drawer = self.adaptive.browsers['documents']
        browser = drawer.browser
        assert await drawer.open_folder({'path': 'Calibre collection/Author'})
        assert await drawer.open_folder({'path': 'Calibre collection/Author/Series'})
        page, tree = drawer.page, browser.tree
        samples = report['library_folder_rotation'] = []
        for orientation in ('portrait', 'landscape-left', 'portrait'):
            await rotate(self, orientation, settle=.6)
            nav = hub._document_collection_navigation
            split = hub._document_collection_body.style.direction == 'row'
            assert self.routes.body('documents').children[0] is page
            assert browser.tree is tree and drawer.breadcrumb.value == 'Series'
            assert (nav.parent is drawer.library_sidebar) == split
            listing = frame(self, browser.native_list)
            header = self.folder_header_geometry(browser, listing)
            sample = dict(orientation=orientation, split=split, listing=listing, header=header)
            samples.append(sample)
            if split:
                assert library._document_library_selected
                sidebar = sample['sidebar'] = frame(self, nav)
                assert sidebar['x'] + sidebar['width'] < listing['x'], (sidebar, listing)
                bottom = sample['bottom'] = float(self.main_window._impl.native.bounds.size.height)
                if pose_snapshot(self)['duo_capable'] and orientation == 'landscape-left':
                    for pane in (sidebar, listing):
                        assert abs(pane['y'] + pane['height'] - bottom) <= 2, (pane, bottom)
            else:
                item = self.native_host.adapter.content_controller('documents').navigationItem
                assert str(item.title) == 'Series', str(item.title)
                assert item.titleView == browser.location_bar._folder_title_view
            await capture_window(self, Path(self.paths.cache) / f'documents-folder-{orientation}.png')
        assert await drawer.up() and drawer.breadcrumb.value == 'Author'
        assert await drawer.up() and drawer.breadcrumb.value == 'Calibre collection'
        assert await drawer.up() and hub.visible_library_drawer() is None
        report['cases'].append('retained_documents_library_folder_rotation')

    async def check_library_root_touches(self, report, frame):
        from commonUtils.testing.waiting import wait_until
        from rubicon.objc import CGPoint
        from .sync_status_probe import tap

        async def touches_reach_list(hub):
            nav = hub._document_collection_navigation
            window = self.main_window._impl.native
            observed = {}

            def reaches_sidebar():
                box = frame(self, nav)
                point = CGPoint(box['x'] + box['width'] / 2, box['y'] + box['height'] * .75)
                target = window.hitTest(point, withEvent=None)
                observed.update(frame=box, target=repr(target))
                return target is not None and target.isDescendantOfView(nav._impl.native)

            # UIKit can hold touches during the spring animation after rotation.
            await wait_until(reaches_sidebar, timeout=2, message=lambda: str(observed))

        await rotate(self, 'landscape-left', settle=.4)
        self.show_documents_hub()
        hub = self.hub_controller()
        for cycle in range(3):
            await hub._document_books_discovery
            for orientation in ('portrait', 'landscape-left'):
                await rotate(self, orientation, settle=.4)
                await touches_reach_list(hub)
            self.routes.return_to('files')
            await asyncio.sleep(.25)
            self.routes.return_to('documents')
            await asyncio.sleep(.35)
            await touches_reach_list(hub)
            button = next(w for w in walk(self.document_books_list)
                          if isinstance(w, toga.Button) and w.text == 'Calibre collection')
            assert button._impl.native.contentEdgeInsets.left == 8
            tap(self, button)
            await wait_until(lambda: hub.visible_library_drawer() is not None, timeout=3)
            drawer = hub.visible_library_drawer()
            await wait_until(lambda: drawer.provider is not None, timeout=5)
            await rotate(self, 'portrait', settle=.4)
            await rotate(self, 'landscape-left', settle=.4)
            assert button._document_library_selected
            assert button._impl.native.contentEdgeInsets.left == 8
            if cycle == 1:
                self.show_documents_hub()
            else:
                assert drawer.cancel_browser()
            await asyncio.sleep(.35)
            if cycle != 1:
                assert not button._document_library_selected
                assert button._impl.native.contentEdgeInsets.left == 8
        report['cases'].append('library_root_touches_after_rotation_and_tab_switching')

    async def check_notes_library_launch(self, report):
        self.show_documents_hub()
        await self._notes_discovery_task
        library = next(w for w in walk(self.document_notes_list)
                       if isinstance(w, toga.Button) and w.text == 'Notes')
        await library.on_press()
        assert self.vault_browser.session.provider == 'notes-library'
        key = self.vault_browser.session.id
        assert self.hub_controller().visible_library_drawer() is None
        await asyncio.sleep(.35)
        await capture_window(self, Path(self.paths.cache) / 'documents-notes-library.png')
        self.close_session(key)
        self.show_documents_hub()
        report['cases'].append('wide_notes_launches_notes_library')

    async def check_document_browser_search(self, report, root, frame):
        """Retain folder search across compact and wide layouts."""
        from commonUtils.runtime.resources.local import LocalFiles

        samples = report['document_browser_search'] = []
        for opened_wide in (True, False):
            await rotate(self, 'landscape-left' if opened_wide else 'portrait', settle=.5)
            self.show_documents_hub()
            self.document_view_buttons['Libraries'].on_press()
            hub = self.hub_controller()
            await hub.browse_document_library('Local files', provider=LocalFiles(root),
                folder='Calibre collection', title='Calibre collection')
            drawer = self.adaptive.browsers['documents']
            browser = drawer.browser
            page = self.routes.body('documents').children[0]
            assert page is drawer.page and not hasattr(page, '_workspace_frame')
            assert page._ios_toolbar_buttons == [drawer.folder_search_button, drawer.folder_actions_button]
            assert drawer.browser.search_button.parent is None
            browser.open_search()
            browser.search.value = 'Library'
            for _ in range(50):
                if browser.entries and not browser.searching:
                    break
                await asyncio.sleep(.1)
            for orientation in ('portrait', 'landscape-left', 'portrait'):
                await rotate(self, orientation, settle=.6)
                assert browser.search_open
                assert [entry.label for entry in browser.entries] == ['Library.epub']
                field, listing = frame(self, browser.search), frame(self, browser.native_list)
                viewport = frame(self, browser.widget)
                sample = dict(opened_wide=opened_wide, orientation=orientation,
                              field=field, listing=listing, viewport=viewport)
                samples.append(sample)
                search_route = browser._search_navigation
                assert self.routes.body('documents').children[0] is search_route.view
                assert browser.native_list.menu_provider is None
                assert not browser.native_list._impl.primary_action_enabled
                from rubicon.objc import ObjCClass
                index = ObjCClass('NSIndexPath').indexPathForRow(0, inSection=0)
                cell = browser.native_list._impl.native.cellForRowAtIndexPath(index)
                assert cell is not None and cell.accessoryView is None
                assert not search_route.view._ios_toolbar_buttons
                from .toolbar_conventions_probe import native_geometry
                geometry = native_geometry(self, verify=False)
                labels = [item['label'] for item in geometry['items'] + geometry['header_items']]
                assert 'Exit search' in labels, labels
                assert not {'Search this folder', 'Parent folder', 'Browse files', 'New document', 'Search documents'}.intersection(labels), labels
                assert field['width'] >= 100 and field['height'] >= 40, sample
                assert listing['height'] >= 80, sample
                assert listing['y'] >= field['y'] + field['height'] - 1, sample
                assert listing['x'] >= viewport['x'] - 1, sample
                assert listing['x'] + listing['width'] <= viewport['x'] + viewport['width'] + 1, sample
                assert not browser.search._impl.native.isHidden(), sample
                assert not browser.native_list._impl.native.isHidden(), sample
                await capture_window(self, Path(self.paths.cache) /
                    f'documents-browser-search-{opened_wide}-{orientation}.png')
            search_route = browser._search_navigation
            await browser.activate_entry(browser.entries[0])
            await asyncio.sleep(.4)
            key = self.visible_reader()
            assert key is not None
            assert self.request_reader_close(key)
            await asyncio.sleep(.5)
            assert self.routes.body('documents').children[0] is search_route.view
            assert browser.search.value == 'Library'
            assert [entry.label for entry in browser.entries] == ['Library.epub']
            browser.close_search()
            assert not browser.search_open
            drawer.cancel_browser()
            self.show_documents_hub()
            # Returning from the browser and entering global search must not
            # leave its retained native listing over the global results.
            search = next(button for button in self.routes.body('documents').children[0]._destination_actions[1]
                          if button.accessible_name == 'Search documents')
            search.on_press()
            self.document_search.value = 'QA unique'
            await asyncio.sleep(.4)
            await hub._documents_file_search.task
            assert self.routes.screens['documents'][-1][0].startswith('search:')
            assert list(hub.document_search_results.children)
            self.close_document_search()
        report['cases'].append('retained_documents_library_search_rotation')

    async def check_workspace_folder_heading(self, report, frame):
        await rotate(self, 'landscape-left', settle=.6)
        self.show_locations()
        await self.show_files(location=('Local files', 'Calibre collection/Author/Series'))
        await asyncio.sleep(.4)
        columns = getattr(self.adaptive, 'file_columns', None)
        if columns is None or not columns.side_by_side:
            return
        root = self.routes.roots['files'].children[0]
        heading = root._destination_actions[0]
        assert heading.parent is columns.sidebar_box
        title = frame(self, root._destination_title)
        listing = frame(self, self.file_browser.native_list)
        assert title['width'] >= 100 and title['height'] >= 24, title
        assert title['x'] + title['width'] < listing['x'], (title, listing)
        assert not heading._impl.native.isHidden()
        header = report['workspaces_folder_header'] = self.folder_header_geometry(self.file_browser, listing)
        documents = next(sample['header'] for sample in report['library_folder_rotation']
                         if sample['orientation'] == 'landscape-left')
        assert abs(documents['title_height'] - header['title_height']) < .1, (documents, header)
        assert abs(documents['caption_offset'] - header['caption_offset']) < .1, (documents, header)
        if pose_snapshot(self)['duo_capable']:
            assert abs(documents['gap'] - header['gap']) <= 1, (documents, header)
        await capture_window(self, Path(self.paths.cache) / 'workspaces-folder-heading.png')
        report['cases'].append('workspaces_sidebar_heading_during_folder_navigation')

    def folder_header_geometry(self, browser, listing):
        from commonUtils.ui.native.keyboard import native_value

        view = browser.location_bar._folder_title_view
        (content,) = native_value(view.subviews)
        title, caption = native_value(content.subviews)
        assert str(native_value(title.text)) == 'Series'
        assert str(native_value(caption.accessibilityLabel)) == 'On-device'
        window = self.main_window._impl.native
        title_box = title.convertRect(title.bounds, toView=window)
        caption_box = caption.convertRect(caption.bounds, toView=window)
        assert caption_box.size.width >= 24
        return dict(title_height=float(title_box.size.height),
                    caption_offset=float(caption_box.origin.y - title_box.origin.y),
                    gap=float(listing['y'] - caption_box.origin.y - caption_box.size.height))

    async def check_workspace_document_chrome(self, report, root):
        from features.notebooks.notebook import Notebook

        self.set_feature_enabled('notebooks', True, refresh=False)
        path = 'Calibre collection/Author/Series'
        (root / path / 'Notebook.rmdoc').write_bytes(Notebook.new('Workspace notebook').to_bytes())
        await rotate(self, 'landscape-left', settle=.5)
        self.show_locations()
        await self.show_files(location=('Local files', path))
        await asyncio.sleep(.35)
        columns = getattr(self.adaptive, 'file_columns', None)
        if columns is None:
            return
        heading = self.routes.roots['files'].children[0]._destination_actions[0]
        assert heading.parent is columns.sidebar_box
        for filename in ('Notebook.rmdoc', 'Sample 01.txt'):
            entry = next(row for row in self.file_browser.entries if row.label == filename)
            await self.file_browser.activate_entry(entry)
            await asyncio.sleep(.6)
            key = self.visible_reader()
            assert key is not None
            assert heading.parent is None
            assert self.adaptive.file_columns.sidebar.controller.view.hidden
            if filename.endswith('.rmdoc'):
                await capture_window(self, Path(self.paths.cache) / 'workspaces-notebook-open.png')
            assert self.request_reader_close(key)
            await asyncio.sleep(.45)
            assert heading.parent is self.adaptive.file_columns.sidebar_box
        report['cases'].append('workspace_heading_retires_for_notebook_and_text_readers')

    async def check_explorer_completion(self, browser, frame):
        row = next(item for item in browser.native_list.data if item.title == 'Library.epub')
        for _ in range(30):
            if getattr(row, 'accessory_caption', None) == ('7%', 'reading_active'):
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('The visible EPUB row did not replace its old 31% estimate with 7%.')
        if self.routes.apple:
            from rubicon.objc import ObjCClass
            from commonUtils.ui.native.recycled_list_ios import _ACCESSORY_CAPTION_TAG
            index = ObjCClass('NSIndexPath').indexPathForRow(row.index, inSection=0)
            cell = browser.native_list._impl.native.cellForRowAtIndexPath(index)
            accessory = cell.accessoryView
            accessory.layoutIfNeeded()
            label = accessory.viewWithTag(_ACCESSORY_CAPTION_TAG)
            assert str(label.text) == '7%'
            caption_frame, dots_frame = label.frame, accessory.titleLabel.frame
            caption_y = caption_frame.origin.y + caption_frame.size.height / 2
            dots_y = dots_frame.origin.y + dots_frame.size.height / 2
            assert caption_frame.origin.y >= 7
            assert 12 <= dots_y - caption_y <= 20
            assert abs(caption_y + dots_y - accessory.bounds.size.height) <= 2
        await capture_window(self, Path(self.paths.cache) / 'documents-hub-explorer-completion-list.png')
        browser.show_tiles()
        for _ in range(30):
            card = browser.entry_rows.get(row.entry.identity)
            badge = getattr(card, '_completion_badge', None)
            if badge is not None and badge.text == '7%':
                break
            await asyncio.sleep(.1)
        else:
            raise AssertionError('The EPUB tile did not show 7%.')
        await asyncio.sleep(.1)
        badge._impl.set_color(badge.style.color)
        native = badge._impl.native
        if self.routes.apple:
            from mobile.appearance import apple_color
            actual = native.textColor.resolvedColorWithTraitCollection(native.traitCollection)
            expected = apple_color('reading_active').resolvedColorWithTraitCollection(native.traitCollection)
            assert actual.isEqual(expected)
        else:
            from mobile.palette import android_palette, argb
            colors = android_palette(native.getResources().getConfiguration().uiMode & 0x30 == 0x20)
            assert native.getCurrentTextColor() == argb(colors.get('reading_active', colors['text']))
        badge, tile = frame(self, badge), frame(self, card)
        assert badge['x'] > tile['x'] + tile['width'] / 2 and abs(badge['y'] - tile['y']) < 2, (badge, tile)
        await capture_window(self, Path(self.paths.cache) / 'documents-hub-explorer-completion-tiles.png')
        browser.show_list()

    async def check_thumbnails(self, section, count):
        from .sync_status_probe import control_frame
        for _ in range(30):
            artwork = [widget for widget in walk(section) if hasattr(widget, '_document_cover')]
            if len(artwork) == count:
                for tile in artwork:
                    row = control_frame(self, tile.parent)
                    frame = control_frame(self, tile)
                    padded_height = frame['height'] + tile.style.margin_top + tile.style.margin_bottom
                    assert frame['height'] >= 72 and abs(row['height'] - padded_height) <= 2, (row, frame)
                    if self.routes.apple:
                        title = next(item for item in walk(tile.parent) if hasattr(item, '_source_caption'))
                        caption = next(item for item in title._source_caption.children if isinstance(item, toga.Label))
                        label = title._impl.native.titleLabel
                        title_frame = label.convertRect(label.bounds, toView=self.main_window._impl.native)
                        detail = control_frame(self, caption)
                        title_bottom = title_frame.origin.y + title_frame.size.height
                        assert -4 <= detail['y'] - title_bottom <= 6, (title_frame, detail)
                        text_center = (title_frame.origin.y + detail['y'] + detail['height']) / 2
                        assert abs(text_center - (row['y'] + row['height'] / 2)) <= 8, (title_frame, detail, row)
                    cover = tile._document_cover
                    assert abs(cover.style.width / cover.style.height
                               - cover.image.width / cover.image.height) < .03
                return
            await asyncio.sleep(.1)
        raise AssertionError(f'Expected {count} loaded local thumbnails')

    def check_duo_header(self, view, destination, frame, geometry):
        from mobile.destination_actions import HEADINGS
        from mobile.ios_toolbar import vertical_edge

        state = view._destination_heading_state
        header = state['header']
        title = header.children[0]
        assert title.text == HEADINGS[destination]
        box = frame(self, header)
        assert box['y'] < 32 and box['height'] >= 48, (destination, box)
        edge = vertical_edge(self.native_host.adapter.content_controller(destination))
        if edge:
            assert not state['buttons'], destination
        elif destination != 'settings':
            assert state['buttons'], destination
            action_groups = state['group'].children
            frames = [frame(self, group) for group in action_groups]
            for first, second in zip(frames, frames[1:]):
                assert second['x'] - first['x'] - first['width'] >= 7, frames
            if destination == 'documents':
                assert len(action_groups[0].children) == 2
                native_children = action_groups[0]._impl.native.subviews
                native_children = native_children() if callable(native_children) else native_children
                assert any(str(child.objc_class.name) == 'UIVisualEffectView'
                           for child in native_children)
        title_box = frame(self, title)
        group = state['group']
        title_end = frame(self, group)['x'] if group is not None else box['x'] + box['width']
        assert int(title._impl.native.textAlignment) == 1, destination
        pane = getattr(view, '_duo_heading_pane', None)
        from toga.style.pack import ROW
        if destination == 'documents' and geometry['pose']['width'] > 900:
            assert pane.parent.style.direction == ROW, destination
        if state['center'] is not None:
            start, end = state['title_space']
            half = title_box['width'] / 2
            expected = box['x'] + min(end - start - half, max(half, state['center'] - start))
            assert abs(title_box['x'] + half - expected) <= 2, (destination, box, title_box)
        else:
            assert abs(title_box['x'] - box['x']) <= 1, (destination, box, title_box)
            assert abs(title_box['x'] + title_box['width'] - title_end) <= 1, (destination, title_end, title_box)
        for x, y, width, height in geometry['occlusions']:
            assert (box['x'] + box['width'] <= x + 1 or box['x'] >= x + width - 1
                    or box['y'] + box['height'] <= y + 1 or box['y'] >= y + height - 1), (destination, box)
        if destination == 'files':
            tabs = frame(self, view._workspaces_source_row)
            assert tabs['y'] >= box['y'] + box['height'] - 1, (box, tabs)
            columns = getattr(self.adaptive, 'file_columns', None)
            if columns is not None:
                if edge and columns.side_by_side:
                    assert state['spans_columns'], (box, tabs)
                    if not geometry['pose']['division_regions']:
                        assert abs(title_box['x'] + title_box['width'] / 2 - geometry['pose']['width'] / 2) <= 2, title_box
                prompt = frame(self, columns.master.folder_placeholder.children[0])
                if prompt['x'] >= tabs['x'] + tabs['width'] - 1:
                    assert abs(prompt['y'] + prompt['height'] / 2 - tabs['y'] - tabs['height'] / 2) <= 2, (tabs, prompt)

    def check_collection_frames(self, frame, orientation):
        from mobile.fold_layout import division
        from toga.style.pack import ROW

        hub = self.hub_controller()
        nav = frame(self, hub._document_collection_navigation)
        detail = frame(self, hub._document_collection_detail)
        fold = division(self, hub._document_collection_body)
        sidebar = hub._document_collection_body.style.direction == ROW
        controls = {name: frame(self, button) for name, button in self.document_view_buttons.items()}
        sample = dict(orientation=orientation, nav=nav, detail=detail, controls=controls,
                      sidebar=sidebar, fold=vars(fold) if fold else None)
        if self.routes.apple:
            companion_visible = sidebar and self.document_search.parent is None
            assert bool(hub._document_companion._impl.native.isHidden()) == (not companion_visible), sample
            assert bool(hub._document_results_scroll._impl.native.isHidden()) == companion_visible, sample
            if not companion_visible:
                assert not hub._document_companion.children, sample
        if sidebar:
            assert detail['x'] >= nav['x'] + nav['width'] + (fold.width if fold is not None else 16) - 2, sample
        else:
            assert detail['y'] >= nav['y'] + nav['height'] + (fold.height if fold else 0) - 2, sample
        for control in controls.values():
            if self.document_views.parent is None:
                continue
            assert control['height'] >= 46 and control['width'] >= 43, sample
            assert control['x'] >= nav['x'] - 1, sample
            assert control['x'] + control['width'] <= nav['x'] + nav['width'] + 1, sample
        return sample

    async def check_retained_toolbar_rotation(self, report, native_geometry):
        from .sync_status_probe import control_frame
        commands = {'New document', 'Search documents', 'Document actions', 'Unlock LocalCrypt'}
        samples = report['retained_toolbar_rotation'] = []
        for unlock in (True, False):
            self.home_unlock_candidates = lambda unlock=unlock: [('synthetic', dict(zip='Synthetic.zip'))] if unlock else []
            self.show_documents_hub()
            for name in ('Libraries', 'Favourites', 'Recent'):
                self.document_view_buttons[name].on_press()
                selected = self.document_results.children[0]
                portrait = None
                for orientation in ('portrait', 'landscape-left', 'portrait', 'landscape-right', 'portrait'):
                    await rotate(self, orientation, settle=.85)
                    assert self.documents_view == name and self.document_results.children[0] is selected
                    geometry = native_geometry(self, verify=False)
                    layout = self.check_collection_frames(control_frame, orientation)
                    items = [item for item in [*geometry['items'], *geometry['header_items']]
                             if item['label'] in commands]
                    sample = dict(tab=name, unlock=unlock, orientation=orientation,
                                  geometry=geometry, collections=layout)
                    samples.append(sample)
                    if geometry['collisions']:
                        await capture_window(self, Path(self.paths.cache) / 'documents-hub-header-collision.png')
                        raise AssertionError(geometry['collisions'])
                    frames = {item['label']: item['frame'] for item in items}
                    assert frames and len(frames) == len(items), sample
                    assert {'New document', 'Search documents'} <= frames.keys(), sample
                    assert ('Unlock LocalCrypt' in frames) == unlock, sample
                    if orientation == 'portrait':
                        if portrait is None:
                            portrait = frames
                        else:
                            assert frames.keys() == portrait.keys(), sample
                            for label, frame in frames.items():
                                assert abs(frame[1] - portrait[label][1]) <= 2, (portrait, sample)
        report['cases'].append('retained_documents_toolbar_portrait_return')


def main():
    return DocumentsHubProbe('Documents hub QA', 'io.github.ispaure.logisticsnotebookqa')
