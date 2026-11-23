"""Native Workspaces transfer shortcut/navigation acceptance with synthetic progress."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage
TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
from pathlib import Path
import traceback
from uuid import uuid4
from mobile.app import LogisticsMobile
from . import start_native_check
from .rotation_checks import rotate, pose_snapshot
from .fixtures import capture_window


def control_frame(app, widget):
    native = widget._impl.native
    if type(app._impl).__module__.startswith('toga_iOS.'):
        rect = native.convertRect(native.bounds, toView=app.main_window._impl.native)
        return dict(x=float(rect.origin.x), y=float(rect.origin.y),
                    width=float(rect.size.width), height=float(rect.size.height))
    from java import jarray, jint
    position = jarray(jint)(2)
    native.getLocationOnScreen(position)
    density = native.getResources().getDisplayMetrics().density
    return dict(x=position[0] / density, y=position[1] / density,
                width=native.getWidth() / density, height=native.getHeight() / density)


class SyncStatusProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('sync-status-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def probe(self):
        report = dict(success=False, samples=[], synthetic_progress=True)
        try:
            self.show_cloud(present=False)
            self.show_locations()
            self.transfer_busy = self.transfer_notification = True
            self.transfer_percentage = 42
            for orientation in ('portrait', 'landscape-left'):
                await rotate(self, orientation, settle=.5)
                self.routes.return_to('files')
                self.refresh_transfer_status()
                await asyncio.sleep(.3)
                button = self.folder_transfers_button
                assert list(self._files_status_row.children) == [self.folder_source_tabs, button]
                assert '42%' in button.accessible_name
                frame = control_frame(self, button)
                row_frame = control_frame(self, button.parent)
                server = control_frame(self, self.folder_source_buttons['Network shares'])
                assert 47 <= frame['width'] <= 49 and 47 <= frame['height'] <= 49, frame
                assert 0 <= frame['x'] - (server['x'] + server['width']) <= 12, (frame, server)
                assert frame['x'] + frame['width'] <= row_frame['x'] + row_frame['width'] + 1, (frame, row_frame)
                for source in ('rclone', 'Network shares', 'Local'):
                    self.change_folder_source(source)
                    await asyncio.sleep(.2)
                    assert list(self._files_status_row.children) == [self.folder_source_tabs, button]
                    await capture_window(self, Path(self.paths.cache) /
                        f'sync-{orientation}-files-{source.replace(" ", "-")}.png')
                native = button._impl.native
                if type(self._impl).__module__.startswith('toga_iOS.'):
                    native.sendActionsForControlEvents(1 << 6)
                else:
                    native.performClick()
                await asyncio.sleep(.2)
                assert self.routes.screens['files'][-1][0] == 'transfers'
                self.routes.back()
                assert not self.routes.screens['files']
                assert self.transfer_busy
                report['samples'].append(dict(orientation=orientation, destination='files',
                    pose=pose_snapshot(self), button=frame, row=row_frame))
            self.transfer_percentage = None
            self.refresh_transfer_status()
            await asyncio.sleep(.5)
            assert self._sync_status_tick is not None
            self.show_documents(destination='documents')
            assert self._sync_status_tick is None
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            self.transfer_busy = self.transfer_notification = False
            self.refresh_transfer_status()
        (Path(self.paths.cache) / 'sync-status-result.json').write_text(json.dumps(report, indent=2))


def main():
    return SyncStatusProbe('Sync status QA', 'io.github.ispaure.logisticsnotebookqa')
