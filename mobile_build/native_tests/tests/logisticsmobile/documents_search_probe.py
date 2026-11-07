"""Search result names retain usable native width in both phone orientations."""
import asyncio
from pathlib import Path

import toga
from commonUtils.testing.stages import TestStage
from .document_workspace_probe import DocumentWorkspaceProbe
from .documents_hub_probe import walk
from .fixtures import capture_window
from .rotation_checks import rotate
from .sync_status_probe import control_frame

TEST_STAGE = TestStage.REGRESSION


class DocumentsSearchProbe(DocumentWorkspaceProbe):
    result_name = 'documents-search-result.json'

    async def run_checks(self, app, report):
        from services.documents.locations import collection_path
        root = collection_path(self.private_root)
        (root / 'Railgun 8 folder').mkdir(parents=True, exist_ok=True)
        (root / 'Railgun 8.cbz').write_text('Filename-only search fixture')
        report['samples'] = []
        self.show_documents_hub()
        self.open_document_search()
        self.document_search.value = 'railgun 8'
        await asyncio.sleep(.4)
        await self.hub_controller()._documents_file_search.task
        for orientation in ('portrait', 'landscape-left'):
            await rotate(self, orientation, settle=.5)
            buttons = [w for w in walk(self.document_search_results)
                       if isinstance(w, toga.Button) and not hasattr(w, '_document_search_menu')]
            assert sorted(w.text for w in buttons) == ['Railgun 8 folder', 'Railgun 8.cbz']
            for button in buttons:
                frame = control_frame(self, button)
                assert frame['width'] > 150, (button.text, frame)
                if self.routes.apple:
                    assert button._impl.native.titleLabel.frame.size.width > 100, button.text
                more = button.parent.children[-1]
                action = control_frame(self, more)
                assert action['x'] >= frame['x'] + frame['width'] - 1, (frame, action)
                report['samples'].append(dict(orientation=orientation, name=button.text, frame=frame))
            await capture_window(self, Path(self.paths.cache) / f'documents-search-{orientation}.png')
        report['cases'].append('search_filenames_have_space_beside_icons_and_actions')


def main():
    return DocumentsSearchProbe('Documents search QA', 'io.github.ispaure.logisticsnotebookqa')
