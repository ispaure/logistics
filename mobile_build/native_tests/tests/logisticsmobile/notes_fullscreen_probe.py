"""Notes owns the screen, closes to Workspaces, and prompts on each visit."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from unittest.mock import AsyncMock, patch
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
            (root / 'Projects').mkdir(exist_ok=True)
            (root / 'Projects/Projects.md').write_text('# Projects\n\nFolder landing note.\n')
            self.show_locations()
            await asyncio.sleep(.5)
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            folder = next(row for row in owner.rows.children if row.children[-1].vault_path == 'Projects')
            assert folder.children[1].browser_entry_kind == 'folder_document'
            await folder.children[-1].on_press()
            assert owner.path == 'Projects/Projects.md'
            folder = next(row for row in owner.rows.children if row.children[-1].vault_path == 'Projects')
            await folder.children[2].on_press()
            assert any(row.children[-1].vault_path == 'Projects/Projects.md' for row in owner.rows.children)
            report['folder_page_visible_and_opened'] = True
            await owner.open_note('Welcome.md')
            owner.follow_link(owner.web, owner.base + '?target=Projects%2FProjects.md')
            for _ in range(100):
                if owner.path == 'Projects/Projects.md':
                    break
                await asyncio.sleep(.05)
            assert owner.path == 'Projects/Projects.md'
            for button, expected in ((owner.back_button, 'Welcome.md'),
                                     (owner.forward_button, 'Projects/Projects.md')):
                native = button._impl.native
                if type(self._impl).__module__.startswith('toga_iOS.'):
                    native.sendActionsForControlEvents(1 << 6)
                else:
                    native.performClick()
                for _ in range(100):
                    if owner.path == expected:
                        break
                    await asyncio.sleep(.05)
                assert owner.path == expected, (owner.path, expected)
            report['native_history_buttons'] = True
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
            assert self.native_host.state.destination == 'files'
            assert not self.routes.screens['files']
            columns = getattr(self.adaptive, 'file_columns', None)
            if columns is not None:
                columns.layout()
                assert not columns.sidebar.controller.view.hidden
            report['returned_to_workspaces'] = True
            from services.documents.locations import collection_path
            vault = collection_path(self.private_root) / 'Repeat Notes'
            (vault / '.obsidian').mkdir(parents=True, exist_ok=True)
            (vault / 'Welcome.md').write_text('# Repeat visit\n')
            for choice in ('cancel', 'notes', 'cancel', 'notes'):
                with patch.object(self.main_window, 'dialog', new=AsyncMock(return_value=choice)) as dialog:
                    await self.show_files(location=('Local files', 'Repeat Notes'))
                    assert dialog.await_count == 1, (choice, dialog.await_count)
                await asyncio.sleep(.2)
                if choice == 'notes':
                    self.vault_browser.close()
                else:
                    self.routes.back()
                await asyncio.sleep(.2)
                assert not self.routes.screens['files']
            report['repeat_folder_choices'] = 4
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notes-fullscreen-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesFullscreenProbe('Notes fullscreen QA', 'io.github.ispaure.logisticsnotebookqa')
