"""Native browser viewports reach their host edge and retain final-row clearance."""

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
        report['cloud_headers'] = []
        for orientation in ('portrait', 'landscape-left', 'landscape-right', 'portrait'):
            if not self.routes.apple:
                (Path(self.paths.cache) / 'creation-orientation').write_text(orientation)
            await rotate(self, orientation, settle=.5)
            if self.routes.apple:
                await self.check_tab_edges(report, evidence, orientation)
            self.show_locations()
            self.change_folder_source('rclone')
            await asyncio.sleep(.3)
            tabs = control_frame(self, self.folder_cloud_tabs)
            picker = control_frame(self, self.folder_credential)
            header = control_frame(self, self.folder_picker_header)
            report['cloud_headers'].append(dict(orientation=orientation, tabs=tabs, picker=picker, header=header))
            assert tabs['y'] + tabs['height'] <= picker['y'] + 1
            assert picker['x'] + picker['width'] <= header['x'] + header['width'] + 1
            await capture_window(self, evidence / f'cloud-{orientation}.png')
            self.change_folder_source('Local')
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

    async def check_tab_edges(self, report, evidence, orientation):
        from rubicon.objc import CGPoint

        self.show_home()
        home = self.hub_controller().home_sections
        scroll = home.trailing_scroll if home.paired else home.leading_scroll
        rows = [toga.Label(f'Home fixture {index:02}', style=Pack(height=48)) for index in range(30)]
        scroll.content.add(*rows)
        await asyncio.sleep(.3)
        self.sample(report, 'home', scroll)
        native = scroll._impl.native
        native.setContentOffset(CGPoint(0, max(0, native.contentSize.height
            + native.contentInset.bottom - native.bounds.size.height)), animated=False)
        await asyncio.sleep(.15)
        last = control_frame(self, rows[-1])
        window = self.main_window._impl.native
        safe_bottom = window.bounds.size.height - window.safeAreaInsets.bottom
        bar = self.native_host.adapter.controller.tabBar
        bounds = bar.convertRect(bar.bounds, toView=window)
        if not self.native_host.adapter.tabs_hidden() and bounds.size.width >= bounds.size.height:
            safe_bottom = min(safe_bottom, bounds.origin.y)
        assert last['y'] + last['height'] <= safe_bottom + 1, (last, safe_bottom)
        await capture_window(self, evidence / f'home-last-{orientation}.png')

        self.show_settings()
        await asyncio.sleep(.3)
        self.sample(report, 'settings', self.settings_navigation.sidebar)
        await capture_window(self, evidence / f'settings-{orientation}.png')

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
