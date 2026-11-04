"""Notes owns the screen, closes to Workspaces, and prompts on each visit."""
from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from threading import Event
from commonUtils.runtime.resources.local import LocalFiles
from mobile.app import LogisticsMobile
from mobile.obsidian import open_vault
from . import start_native_check
from .rotation_checks import rotate, pose_snapshot
from .fixtures import capture_window
from .notes_tree_helpers import activate_entry, landing_row, row_paths


class NotesFullscreenProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('notes-screen-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, samples=[])
        try:
            root = (Path(self.paths.cache) / 'notes-fixture').resolve()
            (root / '.obsidian').mkdir(parents=True, exist_ok=True)
            (root / 'Welcome.md').write_text('# Welcome\n\nThe library owns this screen. [[Projects/Projects]]\n')
            (root / 'Projects').mkdir(exist_ok=True)
            (root / 'Projects/Projects.md').write_text('# Projects\n\nFolder landing note.\n')
            self.show_locations()
            await asyncio.sleep(.5)
            owner = await open_vault(self, LocalFiles(root), '', 'files')
            assert owner.sidebar.side == 'files'
            assert owner.sidebar.overlay is not None
            assert landing_row(owner, 'Projects')
            await activate_entry(owner, 'Projects')
            assert owner.path == 'Projects/Projects.md'
            await activate_entry(owner, 'Projects', expand=True)
            assert 'Projects/Projects.md' in row_paths(owner)
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
            entered, released = Event(), Event()
            original_read = owner.library.read
            def slow_note(path, **kwargs):
                entered.set()
                if not released.wait(10):
                    raise RuntimeError('Slow note fixture timed out')
                return original_read(path, **kwargs)
            with patch.object(owner.library, 'read', side_effect=slow_note):
                task = asyncio.create_task(owner.navigate_history(-1))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.05)
                    assert entered.is_set() and owner.page_loading.active
                    assert owner.page_loading.row.parent is owner.article
                    await asyncio.sleep(.3)
                finally:
                    released.set()
                    await task
            assert not owner.page_loading.active
            report['notes_loading_feedback'] = True
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
                # Exercise the installed DOM gesture handler through WebView
                # navigation, not just the Python drawer callbacks.
                await owner.web.evaluate_javascript('''(function(){
                    function event(type,x){const e=new Event(type,{bubbles:true});
                      Object.defineProperty(e,'touches',{value:[{clientX:x,clientY:160}]});
                      Object.defineProperty(e,'changedTouches',{value:[{clientX:x,clientY:160}]});
                      document.body.dispatchEvent(e);}
                    event('touchstart',innerWidth-5);event('touchend',innerWidth-100);
                })();''')
                for _ in range(100):
                    if owner.sidebar.side == 'links' and any(
                            getattr(row, 'text', '') == 'Outgoing links (1)' for row in owner.link_rows.children):
                        break
                    await asyncio.sleep(.05)
                assert owner.sidebar.side == 'links'
                assert any(getattr(row, 'text', '') == 'Outgoing links (1)' for row in owner.link_rows.children)
                assert list(owner.sidebar.view.children) == [owner.article]
                await asyncio.sleep(.3)
                overlay = owner.sidebar.overlay
                if type(self._impl).__module__.startswith('toga_iOS.'):
                    frame = overlay.container.native.frame
                    bounds = overlay.window.bounds
                    assert frame.origin.x >= 0 and frame.origin.y >= 0
                    assert frame.origin.x + frame.size.width <= bounds.size.width + 1
                    assert frame.origin.y + frame.size.height <= bounds.size.height + 1
                    from mobile.ios_reader_chrome import occlusion_geometry
                    for x, y, width, height in occlusion_geometry(overlay.window):
                        assert not (frame.origin.x < x + width and frame.origin.x + frame.size.width > x
                                    and frame.origin.y < y + height and frame.origin.y + frame.size.height > y)
                await capture_window(self, Path(self.paths.cache) / ('notes-links-' + orientation + '.png'))
                owner.sidebar.swipe(1)
                assert owner.sidebar.overlay is None
                owner.menu.on_press()
                assert owner.sidebar.side == 'files'
                await asyncio.sleep(.3)
                await capture_window(self, Path(self.paths.cache) / ('notes-files-' + orientation + '.png'))
                owner.sidebar.swipe(-1)
                assert owner.sidebar.overlay is None
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
            for choice in ('files', 'notes', 'files', 'notes'):
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
            from mobile.documentation_ui import show_documentation
            docs = show_documentation(self, root, root / 'Welcome.md')
            await docs.load_task
            assert docs.speech.button.enabled
            entered, released = Event(), Event()
            original_read = docs._read_page
            def slow_page(path):
                entered.set()
                if not released.wait(10):
                    raise RuntimeError('Slow documentation fixture timed out')
                return original_read(path)
            with patch.object(docs, '_read_page', side_effect=slow_page):
                docs.open_page(root / 'Projects/Projects.md')
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(.05)
                    assert entered.is_set() and docs.page_loading.active
                    assert docs.path == root / 'Welcome.md'
                    await asyncio.sleep(.3)
                finally:
                    released.set()
                    await docs.load_task
            assert not docs.page_loading.active
            docs.back()
            await docs.load_task
            assert docs.path == root / 'Welcome.md'
            report['documentation_loading_feedback'] = True
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        (Path(self.paths.cache) / 'notes-fullscreen-result.json').write_text(json.dumps(report, indent=2))


def main():
    return NotesFullscreenProbe('Notes fullscreen QA', 'io.github.ispaure.logisticsnotebookqa')
