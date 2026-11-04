"""Focused native clearance acceptance for workspace, editor and picker controls."""
import asyncio
import json
from pathlib import Path
import traceback

from commonUtils.testing.stages import TestStage
from .toolbar_conventions_probe import ConventionsProbe

TEST_STAGE = TestStage.REGRESSION


class SystemOcclusionProbe(ConventionsProbe):
    async def check(self):
        self.output = Path(self.paths.cache) / 'toolbar-qa'
        self.output.mkdir(exist_ok=True)
        self.report = dict(success=False, screens=[], checks=[])
        try:
            await asyncio.sleep(1)
            self.show_locations()
            self.change_folder_source('Local')
            self.folder_local_buttons['Others'].on_press()
            await self.folder_controller().discovery.request()
            await self.record('workspace-overview')
            self.assert_other_locations()
            self.show_chat()
            await self.record('compact-chat-drawer')
            self.show_home()
            assert self.create_chosen_document('md', name='Clearance.md', content='# Clearance')
            sample = await self.record('markdown-editor')
            assert sample['leading'][0] == 'Close document', sample
            self.editor_view.editor.value = '# Changed clearance fixture'
            self.adaptive.render()
            sample = await self.record('markdown-dirty')
            assert sample['pinned'] == ['Save'], sample
            await self.press(self.editor_view.save_button)
            assert not self.editor_view.document.modified
            for destination in ('documents', 'files'):
                self.show_documents(edit=True, destination=destination)
                sample = await self.record('markdown-in-' + destination)
                assert sample['leading'][0] == 'Close document', sample
            self.show_home()
            from .fixtures import choose_creation_type
            await choose_creation_type(self, 'txt')
            await self.record('new-document-name')
            picker = self.editor_picker()
            picker.save_as_name.value = 'Clearance.txt'
            await picker.choose_creation_location()
            await self.record('new-document-confirmation')
            self.report['checks'].extend(['received-and-shared-locations', 'native-markdown-close',
                'native-save-dispatch', 'native-picker-confirmation', 'system-region-and-tab-intersections'])
            self.report['success'] = True
        except BaseException:
            self.report['error'] = traceback.format_exc()
        (self.output / 'result.json').write_text(json.dumps(self.report, indent=2))

    def assert_other_locations(self):
        assert set(self.folder_buttons) == {'All files', 'Received Files'}, set(self.folder_buttons)
        assert self.folder_buttons['All files'].text == 'Shared Files'


def main():
    return SystemOcclusionProbe('System clearance QA', 'io.github.ispaure.logisticsconventionsqa')
