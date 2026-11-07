"""Native browser viewports reach their host edge and retain final-row clearance."""
import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from commonUtils.testing.stages import TestStage
from .document_workspace_probe import DocumentWorkspaceProbe
from .fixtures import capture_window
from .rotation_checks import rotate
from .sync_status_probe import control_frame

TEST_STAGE = TestStage.REGRESSION


class WorkspaceEdgesProbe(DocumentWorkspaceProbe):
    result_name = 'workspace-edges-result.json'

    async def run_checks(self, app, report):
        from services.documents.locations import collection_path
        root = collection_path(self.private_root)
        for index in range(40):
            (root / f'Folder {index:02}').mkdir(parents=True, exist_ok=True)
        evidence = Path(self.paths.cache) / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        report['samples'] = []
        for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
            if not self.routes.apple:
                (Path(self.paths.cache) / 'creation-orientation').write_text(orientation)
            await rotate(self, orientation, settle=.5)
            self.show_locations()
            await asyncio.sleep(.3)
            # A long synthetic source tree exercises the actual retained scroll.
            for child in list(self.folder_list.children):
                self.folder_list.remove(child)
            self.folder_list.add(*(toga.Button(f'Workspace {index:02}', style=Pack(height=48))
                                   for index in range(40)))
            await asyncio.sleep(.3)
            await capture_window(self, evidence / f'sources-{orientation}.png')
            self.sample(report, 'sources', self.folder_picker_view._bottom_scrolls[0])
            await self.show_files(location=('Local files', ''))
            await asyncio.sleep(.5)
            await capture_window(self, evidence / f'workspace-{orientation}.png')
            listing = self.file_browser.native_list
            self.sample(report, 'files', listing)
            columns = getattr(self.adaptive, 'file_columns', None)
            if columns is not None:
                self.sample(report, 'sidebar', columns.sidebar_box._bottom_scrolls[0])
            await capture_window(self, evidence / f'workspace-{orientation}.png')
            if self.routes.apple:
                from rubicon.objc import CGPoint
                native = listing._impl.native
                native.setContentOffset(CGPoint(0, max(0, native.contentSize.height
                    + native.contentInset.bottom - native.bounds.size.height)), animated=False)
                await asyncio.sleep(.15)
                last = list(native.visibleCells)[-1]
                frame = last.convertRect(last.bounds, toView=self.main_window._impl.native)
                window = self.main_window._impl.native
                assert frame.origin.y + frame.size.height <= window.bounds.size.height - window.safeAreaInsets.bottom + 1
            else:
                native = listing._impl.native
                native.setSelection(native.getCount() - 1)
                await asyncio.sleep(.15)
                assert native.getLastVisiblePosition() == native.getCount() - 1
                last = native.getChildAt(native.getChildCount() - 1)
                assert last.getBottom() <= native.getHeight() - native.getPaddingBottom() + 1
            await capture_window(self, evidence / f'workspace-last-{orientation}.png')
        report['cases'].append('browser_viewport_bottom_and_last_row')

    def sample(self, report, name, scroll):
        frame = control_frame(self, scroll)
        if self.routes.apple:
            container = scroll._impl.container
            native = container.native
            bounds = native.convertRect(native.bounds, toView=self.main_window._impl.native)
            bottom = float(bounds.origin.y + bounds.size.height)
            padding = float(scroll._impl.native.contentInset.bottom)
            assert padding >= 12
        else:
            # Android's navigation host allocates content above its system bars.
            frame_root = control_frame(self, self.routes.body())
            bottom = frame_root['y'] + frame_root['height']
            padding = scroll._impl.native.getPaddingBottom() / scroll._impl.native.getResources().getDisplayMetrics().density
            assert padding >= 12
        gap = bottom - frame['y'] - frame['height']
        report['samples'].append(dict(name=name, frame=frame, bottom=bottom, gap=gap, padding=padding))
        assert abs(gap) <= 1, report['samples'][-1]


def main():
    return WorkspaceEdgesProbe('Workspace edges QA', 'io.github.ispaure.logisticsnotebookqa')
