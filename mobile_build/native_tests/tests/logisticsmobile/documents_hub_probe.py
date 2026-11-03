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
        (root / 'Projects/One/Two/Notes/.obsidian').mkdir(parents=True, exist_ok=True)
        (root / 'Projects/One/Two/Notes/QA unique note.md').write_text('# Filename search fixture')
        (root / 'No match.txt').write_text('QA unique')
        inbox_path(self.private_root).mkdir(parents=True, exist_ok=True)
        (inbox_path(self.private_root) / 'QA unique received.txt').write_text('Received')
        (root / 'Graphic novels').mkdir(exist_ok=True)
        (root / 'remoteConfig.ini').write_text('[LogisticsComics]\nlibraries = Graphic novels\n')
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
                    from .toolbar_conventions_probe import native_geometry
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
            for position in positions[1:]:
                assert abs(position[0] - positions[0][0]) <= 2, positions
                assert abs(position[1] - positions[0][1]) <= 2, positions
            assert not hasattr(self.body.children[0], '_workspace_frame')
            self.document_view_buttons['Libraries'].on_press()
            await self._notes_discovery_task
            await self.hub_controller()._document_comics_discovery
            assert self.document_notes_list.children[0].text == 'Notes'
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


def main():
    return DocumentsHubProbe('Documents hub QA', 'io.github.ispaure.logisticsnotebookqa')
