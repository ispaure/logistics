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
        return apple_frame(app, apple_control_view(widget))
    from java import jarray, jint
    position = jarray(jint)(2)
    native.getLocationOnScreen(position)
    density = native.getResources().getDisplayMetrics().density
    return dict(x=position[0] / density, y=position[1] / density,
                width=native.getWidth() / density, height=native.getHeight() / density)


def apple_frame(app, native):
    rect = native.convertRect(native.bounds, toView=app.main_window._impl.native)
    return dict(x=float(rect.origin.x), y=float(rect.origin.y),
                width=float(rect.size.width), height=float(rect.size.height))


def apple_control_view(widget):
    item = getattr(widget, '_ios_action_item', None)
    if widget.parent is None and item is not None:
        view = item.valueForKey('view')
        if view is not None and view.window is not None:
            return view
    return widget._impl.native


def progress_geometry(app, fallback):
    container = fallback._impl.container
    viewport = apple_frame(app, container.native)
    left = viewport['x'] + container.left_inset
    right = viewport['x'] + viewport['width'] - container.right_inset
    controls = [fallback.card, fallback.progress, *fallback.fact_cells, *fallback.buttons.children]
    controls.extend(bar for _, bar in fallback.file_cells if bar is not None)
    for control in controls:
        rect = control_frame(app, control)
        assert left - 1 <= rect['x'] and rect['x'] + rect['width'] <= right + 1, (left, right, rect)
    assert abs(fallback._fitted_width - (right - left)) <= 1

    from mobile.fold_layout import division
    columns = getattr(app.adaptive, 'file_columns', None)
    fold = division(app, app.main_window)
    if columns is not None:
        root = app.routes.roots['files'].children[0]
        heading = root._destination_actions[0]
        assert heading.parent is columns.sidebar_box
        sidebar = apple_frame(app, columns.sidebar.native)
        title = control_frame(app, root._destination_title)
        assert sidebar['x'] - 1 <= title['x'] and title['x'] + title['width'] <= sidebar['x'] + sidebar['width'] + 1
        if fold is not None:
            if fold.vertical:
                assert abs(sidebar['x'] + sidebar['width'] - fold.x) <= 1
                assert abs(viewport['x'] - fold.x - fold.width) <= 1
            else:
                assert abs(sidebar['y'] + sidebar['height'] - fold.y) <= 1
                assert abs(viewport['y'] - fold.y - fold.height) <= 1
    elif fold is not None:
        raise AssertionError('A dividing fold must retain both Workspaces panes')
    return dict(viewport=viewport, usable_width=right - left, split=columns is not None)


def tap(app, widget):
    native = widget._impl.native
    assert widget.enabled
    if type(app._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import CGPoint

        frame = control_frame(app, widget)
        root = app.main_window._impl.native
        point = CGPoint(frame['x'] + frame['width'] / 2, frame['y'] + frame['height'] / 2)
        target = root.hitTest(point, withEvent=None)
        view = apple_control_view(widget)
        assert target is not None and target.isDescendantOfView(view), frame
        if view != native:
            item = widget._ios_action_item
            item.target.performSelector(item.action, withObject=item)
        else:
            native.sendActionsForControlEvents(1 << 6)
    else:
        assert native.isShown() and native.performClick()


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
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            self.show_locations()
            self.transfer_busy = self.transfer_notification = True
            self.transfer_percentage = 42
            state = self.transfer_controller().state
            state.endpoints = ('Server:Projects/Media Archive/' + 'long-folder-name-' * 7,
                               'Local / Received Files / Test downloads')
            state.metrics = dict(phase='Transferring', done=42, total=100, active=1,
                                 active_files=[dict(name='A long sample file.mkv', bytes=42, size=100)])
            self.set_cloud_busy(True)
            for orientation in ('portrait', 'landscape-left'):
                await rotate(self, orientation, settle=.5)
                self.routes.return_to('files')
                self.refresh_transfer_status()
                await asyncio.sleep(.3)
                button = self.folder_transfers_button
                view = self.routes.roots['files'].children[0]
                state = getattr(view, '_destination_heading_state', None)
                native = self.routes.apple and button.parent is None
                placement = [self.folder_source_tabs]
                assert list(self._files_status_row.children) == placement
                assert '42%' in button.accessible_name
                frame = control_frame(self, button)
                server = control_frame(self, self.folder_source_buttons['Network shares'])
                row_frame = None
                if native:
                    assert button._ios_action_item.valueForKey('view').window is not None, frame
                elif state is not None:
                    assert button in state['buttons'] and frame['y'] < server['y'], (frame, server)
                else:
                    assert 47 <= frame['width'] <= 49 and 47 <= frame['height'] <= 49, frame
                    assert frame['y'] < server['y'], (frame, server)
                if not native:
                    row_frame = control_frame(self, state['header'] if state is not None else button.parent)
                    assert frame['x'] + frame['width'] <= row_frame['x'] + row_frame['width'] + 1, (frame, row_frame)
                for source in ('rclone', 'Network shares', 'Local'):
                    tap(self, self.folder_source_buttons[source])
                    await asyncio.sleep(.2)
                    assert self.folder_source == source
                    assert list(self._files_status_row.children) == placement
                    await capture_window(self, Path(self.paths.cache) /
                        f'sync-{orientation}-files-{source.replace(" ", "-")}.png')
                for group in ('Rclone', 'Others'):
                    tap(self, self.folder_local_buttons[group])
                    await asyncio.sleep(.2)
                    assert self.folder_local_group == group
                pose = pose_snapshot(self)
                if pose.get('division_regions'):
                    # Test the transfer panes independently of hit testing the
                    # overview's inline glass control across a simulated fold.
                    self.show_transfers()
                else:
                    tap(self, button)
                await asyncio.sleep(.2)
                assert self.routes.screens['files'][-1][0] == 'transfers'
                overview = self.body
                surface = self.transfer_view
                fallback = surface.native_fallback
                card = fallback.active_card
                assert card is not None and list(fallback.body.children).index(card) == 0
                assert fallback.history in fallback.body.children
                tap(self, card.children[0].children[0])
                await asyncio.sleep(.2)
                assert self.routes.screens['files'][-1][0] == 'transfer-detail'
                fallback = self.transfer_view.native_fallback
                assert fallback.history.parent is None
                sample = dict(orientation=orientation, destination='files',
                              pose=pose, button=frame, row=row_frame)
                if self.routes.apple:
                    await asyncio.sleep(.4)
                    sample['progress'] = progress_geometry(self, fallback)
                    await capture_window(self, Path(self.paths.cache) / f'sync-{orientation}-progress.png')
                    if orientation == 'landscape-left':
                        await rotate(self, 'landscape-right', settle=.5)
                        assert self.transfer_view.native_fallback is fallback
                        sample['rotated_progress'] = progress_geometry(self, fallback)
                        sample['rotated_pose'] = pose_snapshot(self)
                        await capture_window(self, Path(self.paths.cache) / 'sync-landscape-right-progress.png')
                assert self.routes.back()
                assert self.body is overview
                self.routes.back()
                assert not self.routes.screens['files']
                assert self.transfer_busy
                report['samples'].append(sample)
            self.transfer_percentage = None
            self.refresh_transfer_status()
            await asyncio.sleep(.5)
            snapshot = self.folder_transfers_button.snapshot
            self.refresh_transfer_status()
            assert self.folder_transfers_button.snapshot is snapshot
            self.show_documents(destination='documents')
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            self.transfer_busy = self.transfer_notification = False
            self.set_cloud_busy(False)
            self.refresh_transfer_status()
        (Path(self.paths.cache) / 'sync-status-result.json').write_text(json.dumps(report, indent=2))


def main():
    return SyncStatusProbe('Sync status QA', 'io.github.ispaure.logisticsnotebookqa')
