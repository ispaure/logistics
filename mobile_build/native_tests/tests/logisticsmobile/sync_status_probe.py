"""Native main-tab sync shortcut/navigation acceptance with synthetic progress."""
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
            # Exercise the crowded Home row without importing any credentials.
            self.home_unlock_candidates = lambda: [('synthetic', 'Synthetic credentials')]
            self.show_home()
            self.transfer_busy = self.transfer_notification = True
            self.transfer_percentage = 42
            for orientation in ('portrait', 'landscape-left'):
                await rotate(self, orientation, settle=.5)
                for destination in ('home', 'files', 'documents', 'chat', 'settings'):
                    self.routes.return_to(destination)
                    self.refresh_transfer_status()
                    await asyncio.sleep(.3)
                    _, _, button, _ = self._sync_status_controls[destination]
                    assert button.parent is not None
                    assert '42%' in button.accessible_name
                    assert sum((control if inline else row).parent is not None
                        for _, row, control, inline in self._sync_status_controls.values()) == 1
                    await capture_window(self, Path(self.paths.cache) /
                        f'sync-{orientation}-{destination}.png')
                    frame = control_frame(self, button)
                    row_frame = control_frame(self, button.parent)
                    if type(self._impl).__module__.startswith('toga_iOS.'):
                        viewport_width = float(self.main_window._impl.native.bounds.size.width)
                    else:
                        decor = self._impl.native.getWindow().getDecorView()
                        viewport_width = decor.getWidth() / decor.getResources().getDisplayMetrics().density
                    assert frame['x'] >= 0 and frame['x'] + frame['width'] <= viewport_width + 1, frame
                    assert 47 <= frame['width'] <= 49 and 47 <= frame['height'] <= 49, frame
                    assert frame['x'] >= row_frame['x'] - 1, (frame, row_frame)
                    assert frame['x'] + frame['width'] <= row_frame['x'] + row_frame['width'] + 1, (frame, row_frame)
                    assert button._impl._surface_roles == ('hover', 'text', False)
                    if destination == 'files':
                        for source in ('rclone', 'Network shares', 'Local'):
                            self.change_folder_source(source)
                            await asyncio.sleep(.2)
                            await capture_window(self, Path(self.paths.cache) /
                                f'sync-{orientation}-files-{source.replace(" ", "-")}.png')
                            if type(self._impl).__module__.startswith('toga_android.'):
                                for tab in self.folder_source_buttons.values():
                                    view = tab._impl.native
                                    layout = view.getLayout()
                                    last = layout.getLineCount() - 1
                                    assert layout.getEllipsisCount(last) == 0, tab.text
                                    assert layout.getLineBottom(last) <= (view.getHeight()
                                        - view.getCompoundPaddingTop() - view.getCompoundPaddingBottom() + 1), tab.text
                    if destination == 'settings' and self.settings_navigation.wide:
                        self.settings_navigation.choose('Appearance')
                        await asyncio.sleep(.2)
                        await capture_window(self, Path(self.paths.cache) / f'sync-{orientation}-settings-panel.png')
                    native = button._impl.native
                    if type(self._impl).__module__.startswith('toga_iOS.'):
                        native.sendActionsForControlEvents(1 << 6)
                    else:
                        native.performClick()
                    await asyncio.sleep(.2)
                    assert self.routes.screens[destination][-1][0] == 'transfers'
                    other = 'files' if destination == 'home' else 'home'
                    self.routes.return_to(other)
                    self.routes.return_to(destination)
                    assert not self.routes.screens[destination]
                    assert self.transfer_busy
                    report['samples'].append(dict(orientation=orientation, destination=destination,
                        pose=pose_snapshot(self), button=frame, row=row_frame))
                self.routes.return_to('home')
                await asyncio.sleep(.3)
                await capture_window(self, Path(self.paths.cache) / ('sync-' + orientation + '.png'))
            self.transfer_percentage = None
            self.refresh_transfer_status()
            await asyncio.sleep(.5)
            assert self._sync_status_tick is not None
            self.show_documents(destination='documents')
            assert self._sync_status_tick is None
            assert all((button if inline else row).parent is None
                for _, row, button, inline in self._sync_status_controls.values())
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            self.transfer_busy = self.transfer_notification = False
            self.refresh_transfer_status()
        (Path(self.paths.cache) / 'sync-status-result.json').write_text(json.dumps(report, indent=2))


def main():
    return SyncStatusProbe('Sync status QA', 'io.github.ispaure.logisticsnotebookqa')
