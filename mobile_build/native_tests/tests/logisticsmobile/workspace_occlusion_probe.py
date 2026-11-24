"""Retained folder bars across real Island changes and library dismissal."""

import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .adaptive_shell_probe import ShellProbe
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class WorkspaceOcclusionProbe(ShellProbe):
    async def check(self):
        self.output = Path(self.paths.cache) / 'shell-qa'
        self.output.mkdir(exist_ok=True)
        self.report = dict(success=False, screens=[], checks=[])
        try:
            for _ in range(400):
                if not getattr(self, '_startup_in_progress', False):
                    break
                await asyncio.sleep(.1)
            from services.documents.locations import collection_path
            root = collection_path(self.private_root)
            (root / 'Island fixture/Movies').mkdir(parents=True, exist_ok=True)
            for index in range(6):
                (root / f'Island fixture/Movies/Fixture {index}.txt').write_text('Fixture')
            await rotate(self, 'landscape-right', settle=.6)
            self.show_locations()
            await self.show_files(location=('Local files', 'Island fixture/Movies'))
            await self.record('folder-idle')
            browser = self.file_browser
            names = [entry.label for entry in browser.entries]
            for phase in ('audio', 'stopped'):
                await self.wait_phase(phase)
                await self.record('folder-' + phase)
                assert self.file_browser is browser
                assert [entry.label for entry in browser.entries] == names
            samples = self.report['screens'][:3]
            assert len({(row['width'], row['height']) for row in samples}) == 1
            regions = [row['native']['occlusions'] for row in samples]
            assert regions[0] != regions[1] and regions[0] == regions[2], regions
            assert not [row for row in samples if row['native']['collisions']], samples
            self.show_documents_hub()
            from commonUtils.runtime.resources.local import LocalFiles
            hub = self.hub_controller()
            await hub.browse_document_library('Local files', provider=LocalFiles(root),
                folder='Island fixture', title='Island fixture')
            drawer = self.adaptive.browsers['documents']
            assert hub._document_collection_navigation.parent is drawer.library_sidebar
            await self.record('library-open')
            drawer.folder_back_button._impl.native.sendActionsForControlEvents(1 << 6)
            await asyncio.sleep(.4)
            assert hub.visible_library_drawer() is None
            actions = self.routes.roots['documents'].children[0]._ios_toolbar_buttons()
            assert drawer.folder_search_button not in actions
            assert drawer.folder_back_button not in actions
            assert drawer.folder_actions_button not in actions
            assert {button.accessible_name for button in actions} >= {'New document', 'Search documents'}
            await self.record('library-closed')
            assert not self.report['screens'][-1]['native']['collisions']
            self.report['checks'] = ['same-size-real-island-expansion-contraction',
                'retained-workspace-folder-actions', 'native-library-back-restores-documents-actions']
            self.report['success'] = True
        except BaseException:
            self.report['error'] = traceback.format_exc()
        finally:
            (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))


def main():
    return WorkspaceOcclusionProbe('Workspace Island QA', 'io.github.ispaure.logisticsconventionsqa')
