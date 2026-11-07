"""Focused Documents layout, filename search and shared unlock native acceptance."""
import asyncio
from pathlib import Path
import toga
from commonUtils.testing.stages import TestStage
from .document_workspace_probe import DocumentWorkspaceProbe
from .fixtures import capture_window
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
        (root / 'No match.txt').write_text('QA unique')
        inbox_path(self.private_root).mkdir(parents=True, exist_ok=True)
        (inbox_path(self.private_root) / 'QA unique received.txt').write_text('Received')
        (root / 'Graphic novels').mkdir(exist_ok=True)
        (root / 'remoteConfig.ini').write_text('[LogisticsComics]\nlibraries = Graphic novels\n')
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
                    unlock = [item for item in geometry['items'] if item['label'] == 'Unlock LocalCrypt']
                    assert len(unlock) == 1, geometry
                    position = unlock[0]['frame']
                    report['samples'].append(dict(destination=destination, orientation=orientation,
                                                  geometry=geometry))
                else:
                    frame = control_frame(self, actions[0])
                    position = [frame[key] for key in ('x', 'y', 'width', 'height')]
                    report['samples'].append(dict(destination=destination, orientation=orientation, unlock=position))
                positions.append(position)
                await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-{destination}.png')
            # Documents keeps its native bar even when another destination
            # projects its unlock shortcut into a free part of the top band.
            for position in (positions[1:2] if self.routes.apple else positions[1:]):
                assert abs(position[0] - positions[0][0]) <= 2, positions
                assert abs(position[1] - positions[0][1]) <= 2, positions
            assert not hasattr(self.body.children[0], '_workspace_frame')
            report.setdefault('collections', []).append(self.check_collection_frames(control_frame, orientation))
            self.document_view_buttons['Libraries'].on_press()
            await self._notes_discovery_task
            await self.hub_controller()._document_comics_discovery
            # A synthetic locked copy inserts guidance before the Notes heading.
            assert any(isinstance(widget, toga.Label) and widget.text == 'Notes'
                       for widget in self.document_notes_list.children)
            assert self.document_comics_list.children[0].text == 'Comics'
            assert any(getattr(w, 'text', '') == 'Notes' and isinstance(w, toga.Button)
                       for w in walk(self.document_notes_list))
            assert any(getattr(w, 'text', '') == 'Graphic novels' and isinstance(w, toga.Button)
                       for w in walk(self.document_comics_list))
            await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-libraries.png')
            assert self.document_search.parent is None
            self.open_document_search()
            assert self.document_search.parent is not None
            self.document_search.value = 'QA unique'
            await asyncio.sleep(.4)
            await self.hub_controller()._documents_file_search.task
            assert self.document_views.parent is None
            names = [w.text for w in walk(self.document_search_results) if isinstance(w, toga.Button) and not hasattr(w, '_document_search_menu')]
            assert names == ['QA unique note.md', 'QA unique received.txt'], names
            await capture_window(self, Path(self.paths.cache) / f'documents-hub-{orientation}-search.png')
            if self.routes.apple:
                self.close_document_search()
            else:
                self._impl.native.getOnBackPressedDispatcher().onBackPressed()
            assert not self.documents_search_open and self.document_search.parent is None
            assert self.document_views.parent is not None
            self.document_view_buttons['Open'].on_press()
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
                                'shared_unlock_placement', 'no_documents_hamburger', 'unlock_disappears'])

    def check_collection_frames(self, frame, orientation):
        from mobile.documents_hub import SIDEBAR_BREAKPOINT
        from mobile.fold_layout import division

        hub = self.hub_controller()
        nav = frame(self, hub._document_collection_navigation)
        detail = frame(self, hub._document_collection_detail)
        fold = division(self, hub._document_collection_body)
        width = self.adaptive.content_width('documents', margin=32)
        sidebar = fold.vertical if fold is not None else width >= SIDEBAR_BREAKPOINT
        controls = {name: frame(self, button) for name, button in self.document_view_buttons.items()}
        sample = dict(orientation=orientation, nav=nav, detail=detail, controls=controls,
                      sidebar=sidebar, fold=vars(fold) if fold else None)
        if sidebar:
            assert detail['x'] >= nav['x'] + nav['width'] + (fold.width if fold else 16) - 2, sample
        else:
            assert detail['y'] >= nav['y'] + nav['height'] + (fold.height if fold else 0) - 2, sample
        for control in controls.values():
            assert control['height'] >= 46 and control['width'] >= 43, sample
            assert control['x'] >= nav['x'] - 1, sample
            assert control['x'] + control['width'] <= nav['x'] + nav['width'] + 1, sample
        return sample

    async def check_retained_toolbar_rotation(self, report, native_geometry):
        from .sync_status_probe import control_frame
        commands = {'Open document', 'New document', 'Search documents',
                    'Document actions', 'Unlock LocalCrypt'}
        samples = report['retained_toolbar_rotation'] = []
        for unlock in (True, False):
            self.home_unlock_candidates = lambda unlock=unlock: [('synthetic', dict(zip='Synthetic.zip'))] if unlock else []
            self.show_documents_hub()
            for name in ('Libraries', 'Open', 'Recent', 'Saved'):
                self.document_view_buttons[name].on_press()
                selected = self.document_results.children[0]
                portrait = None
                for orientation in ('portrait', 'landscape-left', 'portrait', 'landscape-right', 'portrait'):
                    await rotate(self, orientation, settle=.5)
                    assert self.documents_view == name and self.document_results.children[0] is selected
                    geometry = native_geometry(self)
                    layout = self.check_collection_frames(control_frame, orientation)
                    items = [item for item in geometry['items'] if item['label'] in commands]
                    sample = dict(tab=name, unlock=unlock, orientation=orientation,
                                  geometry=geometry, collections=layout)
                    samples.append(sample)
                    frames = {item['label']: item['frame'] for item in items}
                    assert frames and len(frames) == len(items), sample
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
