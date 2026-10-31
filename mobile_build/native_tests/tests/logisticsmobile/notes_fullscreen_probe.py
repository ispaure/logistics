"""Notes Library owns the mobile screen and returns to its folder browser."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import start_native_check
from .rotation_checks import rotate, pose_snapshot
from .fixtures import capture_window


class NotesFullscreenProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-screen-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, samples=[])
        try:
            root = Path(self.paths.cache) / 'notes-fixture'
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Welcome.md').write_text('# Welcome\n\nThe library owns this screen.\n')
            self.show_locations()
            await asyncio.sleep(.5)
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            for orientation in ('landscape-left', 'portrait', 'landscape-left'):
                await rotate(self, orientation, settle=.5)
                await owner.open_note('Welcome.md')
                await asyncio.sleep(.5)
                assert self._document_tabs_hidden
                assert not hasattr(owner.view, '_workspace_frame')
                columns = getattr(self.adaptive, 'file_columns', None)
                if columns is not None:
                    columns.layout()
                    assert columns.sidebar.controller.view.hidden
                    bounds = columns.controller.view.bounds.size
                    frame = columns.navigation.view.frame
                    assert abs(frame.origin.x) < 1 and abs(frame.size.width - bounds.width) < 1
                report['samples'].append(dict(orientation=orientation, pose=pose_snapshot(self),
                    native_columns=columns is not None, full_screen=True))
            await capture_window(self, Path(self.paths.cache) / 'notes-fullscreen.png')
            owner.close()
            await asyncio.sleep(.5)
            assert not self._document_tabs_hidden
            columns = getattr(self.adaptive, 'file_columns', None)
            if columns is not None:
                columns.layout()
                assert not columns.sidebar.controller.view.hidden
            report['returned_to_browser'] = True
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notes-fullscreen-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesFullscreenProbe('Notes fullscreen QA', 'io.github.ispaure.logisticsnotebookqa')
