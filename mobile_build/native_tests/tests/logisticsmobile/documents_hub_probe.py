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
        book, comic = make_books(root, embed_cover=True)
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
        if self.routes.apple:
            from .toolbar_conventions_probe import native_geometry
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
            await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-libraries.png')
            assert self.document_search.parent is None
            search = self.routes.body('documents').children[0]._document_search_button
            search.on_press()
            assert self.document_search.parent is not None
            self.document_search.value = 'QA unique'
            await asyncio.sleep(.4)
            await self.hub_controller()._documents_file_search.task
            assert self.document_views.parent is None
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

    async def check_thumbnails(self, section, count):
        from .sync_status_probe import control_frame
        for _ in range(30):
            artwork = [widget for widget in walk(section) if hasattr(widget, '_document_cover')]
            if len(artwork) == count:
                for tile in artwork:
                    row = control_frame(self, tile.parent)
                    frame = control_frame(self, tile)
                    assert frame['height'] >= 72 and abs(row['height'] - frame['height']) <= 2, (row, frame)
                    cover = tile._document_cover
                    assert abs(cover.style.width / cover.style.height
                               - cover.image.width / cover.image.height) < .03
                return
            await asyncio.sleep(.1)
        raise AssertionError(f'Expected {count} loaded local thumbnails')

    def check_duo_header(self, view, destination, frame, geometry):
        from mobile.destination_actions import DUO_HEADINGS
        from mobile.ios_toolbar import vertical_edge

        state = view._duo_heading_state
        header = state['header']
        title = header.children[0]
        assert title.text == DUO_HEADINGS[destination]
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
        assert abs(title_box['x'] - box['x']) <= 1, (destination, box, title_box)
        pane = getattr(view, '_duo_heading_pane', None)
        from toga.style.pack import NONE, ROW
        if destination == 'documents' and geometry['pose']['width'] > 900:
            assert pane.parent.style.direction == ROW, destination
        if pane is not None and pane.parent.style.direction == ROW and pane.style.width != NONE:
            leading = frame(self, pane)
            expected = leading['x'] + leading['width'] / 2
            assert abs(title_box['x'] + title_box['width'] / 2 - expected) <= 2, (destination, leading, title_box)
        else:
            assert abs(title_box['x'] + title_box['width'] - title_end) <= 1, (destination, title_end, title_box)
        for x, y, width, height in geometry['occlusions']:
            assert (box['x'] + box['width'] <= x + 1 or box['x'] >= x + width - 1
                    or box['y'] + box['height'] <= y + 1 or box['y'] >= y + height - 1), (destination, box)
        if destination == 'files':
            tabs = frame(self, view._workspaces_source_row)
            assert tabs['y'] >= box['y'] + box['height'] - 1, (box, tabs)

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
        if sidebar:
            assert detail['x'] >= nav['x'] + nav['width'] + (fold.width if fold is not None else 16) - 2, sample
        else:
            assert detail['y'] >= nav['y'] + nav['height'] + (fold.height if fold else 0) - 2, sample
        for control in controls.values():
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
