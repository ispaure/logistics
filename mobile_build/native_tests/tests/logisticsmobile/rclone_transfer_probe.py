"""Native transfer review/progress acceptance using read-only synthetic data."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import json
from pathlib import Path
from threading import Event
from time import monotonic, sleep
import traceback
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from zipfile import ZipFile
import sys

from commonUtils.testing.stages import TestStage
from features.rclone.transfers.review import ReviewRequest, ReviewSession
from features.rclone.transfers.mobile.review_ui import MobileReviewPresentation, TransferReviewDialog
from mobile.app import LogisticsMobile
from . import start_native_check
from .fixtures import capture_window
from .rotation_checks import rotate

TEST_STAGE = TestStage.REGRESSION


class RcloneTransferProbe(LogisticsMobile):
    def startup(self):
        self.fixture_root = Path(self.paths.cache) / ('transfer-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def wait_surface(self, surface):
        for _ in range(150):
            if surface.ready and surface.delivered_revision == surface.revision and surface.revision:
                return
            await asyncio.sleep(.1)
        raise AssertionError('Transfer surface did not render: ' + str((surface.ready, surface.revision, surface.delivered_revision)))

    async def sample(self, surface, name, report, evidence):
        from .web_checks import verify_native_transfer_fallback

        await self.wait_surface(surface)
        await asyncio.sleep(.2)
        assert surface.web is None
        report['samples'].append(dict(name=name, **verify_native_transfer_fallback(surface)))
        await capture_window(self, evidence / (name + '.png'))

    async def probe(self):
        report = dict(success=False, synthetic=True, samples=[])
        evidence = Path(self.paths.cache) / 'viewer-layout'
        evidence.mkdir(exist_ok=True)
        session = task = None
        try:
            self.show_cloud(present=False)
            restore = getattr(self, 'cloud_restore_task', None)
            if restore is not None:
                await restore
            await asyncio.sleep(.5)
            self.routes.return_to('files')
            with patch.object(self, 'loaded_remote_names', return_value=['Personal', 'Backup']):
                self.show_local_push('Personal')
                await self.wait_surface(self.transfer_controller()._transfer_setup_surface)
                await capture_window(self, evidence / 'push-options.png')
            self.routes.return_to('files')
            owner = self.transfer_controller()
            state = owner.state
            state.operation, state.result = 'push', 'running'
            state.started_at = monotonic() - 84
            self.transfer_busy = self.transfer_notification = True
            self.transfer_epoch = 1
            self.transfer_endpoints = ('Local/Personal', 'Personal:')
            self.show_transfers(detail=True)
            for name, values in (
                ('progress', dict(phase='Transferring', files=28, total_files=64, done=125000000,
                    total=250000000, active=2, listed=82, checks=18,
                    active_files=[dict(name='Photos/Autumn/Maples.jpg', bytes=1200000, size=3200000),
                                  dict(name='Projects/Research/Planning notes.md', bytes=8600, size=12000)])),
                ('progress-unknown', dict(phase='Discovering / checking files', files=0, done=0, total=0, listed=82, checks=18)),
                ('progress-verify', dict(phase='Sync complete; verifying local copy', files=64, done=250000000, total=250000000))):
                self.publish_mirror_progress(1, values)
                await self.sample(self.transfer_view, name, report, evidence)
            if type(self._impl).__module__.startswith('toga_android.'):
                await self.sample_android_contrast(report, evidence)
            # Leave the screen through its real action; updates must remain offscreen.
            self.publish_mirror_progress(1, dict(phase='Transferring', files=28, done=125000000, total=250000000))
            await self.wait_surface(self.transfer_view)
            hidden_surface = self.transfer_view
            await hidden_surface.native_fallback.buttons.children[-1].on_press()
            await asyncio.sleep(.2)
            delivered = hidden_surface.delivered_revision
            self.publish_mirror_progress(1, dict(phase='Transferring', files=29, done=126000000, total=250000000))
            await asyncio.sleep(.2)
            assert hidden_surface.delivered_revision == delivered
            assert hidden_surface.send_task is None
            self.show_transfers(detail=True)
            await self.wait_surface(hidden_surface)
            progress_bar = hidden_surface.native_fallback.progress
            self.publish_mirror_progress(1, dict(phase='Transferring', files=30, done=127000000, total=250000000))
            await self.wait_surface(hidden_surface)
            assert hidden_surface.native_fallback.progress is progress_bar
            report['offscreen_updates_suppressed'] = True
            report['progress_widget_retained'] = True
            state.busy, state.complete, state.result = False, True, 'complete'
            state.finished_at = monotonic()
            owner.render_transfer_summary()
            await self.sample(self.transfer_view, 'progress-complete', report, evidence)
            state.complete, state.result = False, 'failed'
            state.message = 'Connection lost. Completed changes remain.'
            owner.render_transfer_summary()
            await self.sample(self.transfer_view, 'progress-failed', report, evidence)
            state.result = 'idle'
            state.message = 'No transfer is running.'
            owner.render_transfer_summary()
            with patch.object(owner, 'refresh_transfer_history', new=AsyncMock()):
                self.show_transfers()
            surface = self.transfer_view
            surface.update(dict(surface.model, downloads=[dict(id='sample', name='World tour.mp4',
                path='Videos/World tour.mp4', offset=45_000_000_000, size=100_000_000_000)],
                history=[dict(time=1_796_000_000_000_000_000, operation='download',
                              source='Personal:Photos/Autumn', destination='On this Phone / Autumn',
                              bytes=3_500_000_000)]))
            await self.sample(surface, 'transfer-history', report, evidence)
            history = surface.native_fallback.history
            contents = next(control.children[0] for control in history.children
                            if hasattr(control, 'children') and control.children
                            and hasattr(control.children[0], 'children')
                            and any(getattr(child, 'text', '') == 'World tour.mp4'
                                    for child in control.children[0].children))
            assert '45.00 GB of 100.00 GB' in contents.children[1]._settings_source_text
            assert [control.text for control in contents.children[-1].children] == ['Resume', 'Discard…']
            assert any(getattr(control, 'text', None) == 'Clear history…' for control in history.children)
            self.routes.return_to('files')
            self.transfer_busy = self.transfer_notification = False
            if type(self._impl).__module__.startswith('toga_android.'):
                await self.skip_live_review(owner, report)

            def scan(emit, cancelled):
                for kind, path in [('add', 'Documents/Travel checklist.md'), ('add', 'Photos/Autumn/Maples.jpg'),
                    ('add', 'Documents/Receipts/'), ('replace', 'Documents/Trip budget.xlsx'),
                    ('delete', 'Archives/old-backup.zip'), ('replace', 'Projects/Research/Planning notes.md'),
                    ('add', 'Unsafe/<img src=x onerror=alert(1)>.txt')]:
                    emit(kind, path)
                if many:
                    for index in range(35):
                        emit('add', f'More/File {index + 1:02}.txt')
                return 'synthetic-revision'

            for operation, many in (('Push', False), ('Pull', False), ('Push', True)):
                suffix = 'many' if many else operation.lower()
                source, target = ('Local/Personal', 'Personal:') if operation == 'Push' else ('Personal:', 'Local/Personal')
                active = [True]
                session = ReviewSession(ReviewRequest(operation, source, target, 'synthetic'), scan, lambda: active[0])
                dialog = TransferReviewDialog(MobileReviewPresentation(owner))
                task = asyncio.create_task(dialog.run(session))
                for _ in range(100):
                    surface = getattr(self, '_transfer_review_view', None)
                    if surface is not None and surface.review_ready:
                        break
                    await asyncio.sleep(.1)
                else:
                    raise AssertionError('Review did not become ready')
                await self.sample(surface, 'review-' + suffix, report, evidence)
                if not many and operation == 'Push':
                    self.preferences.values['font_size'] = '20'
                    surface.update(surface.model)
                    await self.sample(surface, 'review-large-text', report, evidence)
                    self.preferences.values['font_size'] = '16'
                    surface.update(surface.model)
                    await self.wait_surface(surface)

                fallback = surface.native_fallback
                if many:
                    await fallback.review_next.on_press()
                    await self.sample(surface, 'review-next-page', report, evidence)
                    assert surface.model['page'] == 1
                kind = fallback.review_filters.children[0]
                kind.value = 'Delete'
                await kind.on_change()
                await self.sample(surface, 'delete-' + suffix, report, evidence)
                assert surface.model['rows'] == (('delete', 'Archives/old-backup.zip'),)
                if operation == 'Pull' and sys.platform == 'ios':
                    await rotate(self, 'landscape-left', settle=.3)
                    await self.sample(surface, 'review-landscape', report, evidence)
                    await rotate(self, 'portrait', settle=.3)
                if operation == 'Push' and not many:
                    # Exercise the native action through ReviewSession confirmation.
                    declined = AsyncMock(return_value=False)
                    with patch.object(self.main_window, 'dialog', new=declined):
                        start = next(button for button in fallback.buttons.children
                                     if getattr(button, '_settings_source_text', button.text) == 'Start push')
                        await start.on_press()
                        for _ in range(40):
                            if declined.await_count:
                                break
                            await asyncio.sleep(.05)
                        assert declined.await_count == 1
                        assert not session.approved and not surface.closed
                    await self.wait_surface(surface)
                    accepted = AsyncMock(return_value=True)
                    with patch.object(self.main_window, 'dialog', new=accepted):
                        start = next(button for button in fallback.buttons.children
                                     if getattr(button, '_settings_source_text', button.text) == 'Start push')
                        await start.on_press()
                        assert await asyncio.wait_for(task, 5)
                        assert accepted.await_count == 1 and session.approved
                    report['native_approval_and_decline'] = True
                else:
                    active[0] = False
                    await task
                assert surface.closed and not surface.model
                session = task = None
            await self.selected_downloads(report, evidence)
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if session is not None:
                session.cancel()
            if task is not None:
                await task
            (Path(self.paths.cache) / 'rclone-transfer-result.json').write_text(json.dumps(report, indent=2))

    async def skip_live_review(self, owner, report):
        advance = Event()

        def scan(emit, cancelled):
            changes = [('replace', f'Comics/Series/Chapter {index:05}.cbz') for index in range(12_000)]
            emit.replace(changes)
            while not advance.wait(.05) and not cancelled():
                pass
            if not cancelled():
                emit.replace([*changes, ('add', 'Comics/New volume.cbz')])
            while not cancelled():
                sleep(.05)
            return ''

        session = ReviewSession(ReviewRequest('Pull', 'Fixture:', 'Local/Fixture', 'fixture'), scan)
        dialog = TransferReviewDialog(MobileReviewPresentation(owner))
        task = asyncio.create_task(dialog.run(session))
        try:
            for _ in range(150):
                surface = dialog.surface
                if surface is not None and surface.model.get('total') == 12_000:
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError('Live review did not show the first large snapshot')
            footer = surface.native_fallback.buttons
            skip = next(button for button in footer.children if button.text == 'Skip preview and start')
            advance.set()
            for _ in range(150):
                if surface.model.get('total') == 12_001:
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError('Live review did not show the growing snapshot')
            assert skip in footer.children and skip._impl.native.performClick()
            assert await asyncio.wait_for(asyncio.shield(task), 5)
            report['android_skip_one_tap_during_large_review'] = True
        finally:
            if not task.done():
                session.cancel()
                await task

    async def sample_android_contrast(self, report, evidence):
        from mobile.appearance import configure_android_eink
        from mobile.palette import argb
        from toga.style.pack import ROW

        def set_contrast(enabled):
            self.preferences.values['android_eink'] = 'true' if enabled else 'false'
            configure_android_eink(self)
            self.refresh_native_theme()

        def fill(progress):
            tint = progress._impl.native.getProgressTintList()
            return None if tint is None else tint.getDefaultColor()

        surface = self.transfer_view
        fallback = surface.native_fallback
        original_fill = fill(fallback.progress)
        active_files = [dict(name=f'Library/Collected editions/Volume {index + 1:02}.cbz',
                             bytes=16_000_000 + index * 4_000_000, size=64_000_000)
                        for index in range(10)]
        values = dict(phase='Transferring', files=28, total_files=64, done=125_000_000,
                      total=250_000_000, active=len(active_files), active_files=active_files)
        self.publish_mirror_progress(1, values)
        await self.sample(surface, 'progress-regular-ten-files', report, evidence)
        set_contrast(True)
        try:
            update_times = []
            for tick in range(1, 7):
                snapshot = [dict(row, bytes=row['bytes'] + tick * 500_000) for row in active_files]
                start = monotonic()
                self.publish_mirror_progress(1, dict(values, active_files=snapshot,
                    done=values['done'] + tick * 5_000_000))
                update_times.append(monotonic() - start)
                await asyncio.sleep(.1)
            report['android_eink_max_progress_update_ms'] = round(max(update_times) * 1000)
            assert max(update_times) < 4
            await self.sample(surface, 'progress-eink', report, evidence)
            assert len(fallback.file_cells) == 10
            assert len(fallback.rows.children) == 10
            assert list(fallback.file_group.children) == [fallback.file_heading, fallback.rows]
            assert fallback.file_group._impl._surface_eink_outlined
            assert not fallback.file_group._impl._surface_roles[2]
            assert all(not row._impl._surface_eink_outlined for row in fallback.rows.children)
            assert fill(fallback.progress) == argb('#000000')
            inline_rows = 0
            for detail, bar in fallback.file_cells:
                label_view, bar_view = detail._impl.native, bar._impl.native
                assert label_view.isAttachedToWindow() and bar_view.isAttachedToWindow()
                assert detail.parent is bar.parent
                if detail.parent.style.direction == ROW:
                    assert label_view.getRight() <= bar_view.getLeft() or bar_view.getRight() <= label_view.getLeft()
                    assert label_view.getTop() < bar_view.getBottom() and bar_view.getTop() < label_view.getBottom()
                    inline_rows += 1
                else:
                    assert label_view.getBottom() <= bar_view.getTop()
                assert bar_view.getWidth() > 0
                assert fill(bar) == argb('#000000')
            scroll = fallback.children[0]
            scroll.vertical_position = scroll.max_vertical_position
            await asyncio.sleep(.2)
            await capture_window(self, evidence / 'progress-eink-last-files.png')
            report['android_eink_active_rows'] = len(fallback.file_cells)
            report['android_eink_inline_rows'] = inline_rows
        finally:
            set_contrast(False)
        assert surface.native_fallback is fallback
        assert fill(fallback.progress) == original_fill
        report['android_eink_progress_restored'] = True

    async def selected_downloads(self, report, evidence):
        from commonUtils.runtime.operations import check_cancelled
        from commonUtils.runtime.resources.documents import LocalDocuments
        from features.rclone.mobile import remote_downloads
        from services.documents.locations import collection_path
        from services.documents.mobile_locations import enabled, phone_path
        from mobile.local_sources import device_files_label
        from .web_checks import wait_for_transfer_surface

        async def until(condition, message):
            for _ in range(240):
                if condition():
                    return
                await asyncio.sleep(.1)
            raise AssertionError(message)

        async def appearance(dark):
            if sys.platform == 'ios':
                self.main_window._impl.native.overrideUserInterfaceStyle = 2 if dark else 1
            else:
                from android.app import UiModeManager
                from android.content import Context
                activity = self._impl.native
                manager = activity.getSystemService(Context.UI_MODE_SERVICE)
                manager.setApplicationNightMode(UiModeManager.MODE_NIGHT_YES if dark else UiModeManager.MODE_NIGHT_NO)
                await until(lambda: bool(activity.getResources().getConfiguration().uiMode
                           & 0x30 == 0x20) == dark, 'Android did not adopt the requested appearance')
                self.refresh_native_theme()
            await asyncio.sleep(.3)

        fixture = self.fixture_root / 'download-fixture'
        seed = fixture / 'seed'
        (seed / 'folder').mkdir(parents=True)
        (seed / 'note.txt').write_text('Selected crypt file')
        (seed / 'folder' / 'child.txt').write_text('Selected crypt folder')
        package = fixture / 'Synthetic.zip'
        with ZipFile(package, 'w') as archive:
            archive.writestr('Cloud.txt', '[Cloud]\ntype=memory\n')
            archive.writestr('Secret.txt', '[Secret]\ntype=crypt\nremote=Cloud:encrypted\n'
                'password=kbLdY_D-MRsrDH6_akD3SfOzlJ0VseUk2jfUrywMSTOLmTrSvFOxCkP94a-Ul-w\n')
        client = self.cloud_client
        names = await asyncio.to_thread(client.import_package, LocalDocuments(), package,
                                        'synthetic-session-password', remember=True)
        assert any(record['saved'] for record in client.package_records)
        self.set_loaded_remote_names(names)
        self.cloud_crypt_remotes = set(await asyncio.to_thread(client.crypt_remotes))
        identity = await asyncio.to_thread(client.connection_identity, 'Secret')
        await asyncio.to_thread(client.request, 'mirror_sync', remote='Secret', path='fixtures',
            identity=identity, local_path=str(seed.resolve()), run=uuid4().hex, push=True, decrypted=True)

        if enabled(self.private_root):
            base = phone_path(self.private_root)
            browser_storage, picker_storage = 'Shared files', device_files_label(self)
        else:
            base = collection_path(self.private_root)
            browser_storage, picker_storage = 'Local files', 'Local'
        parent = base / 'Download QA'
        parent.mkdir(parents=True)
        for index in range(60):
            (parent / f'keep-{index:02}.txt').write_text('retained')
        assert await self.show_files(location=(browser_storage, parent.name))
        browser = self.file_browser

        from features.rclone.mobile import folder_recovery
        copy_file = remote_downloads.sync_copy
        copy_folder = folder_recovery.run_folder_download
        for dark in (False, True):
            theme = 'dark' if dark else 'light'
            await appearance(dark)
            self.show_transfers()
            await wait_for_transfer_surface(self.transfer_view)
            await self.sample(self.transfer_view, theme + '-before-download', report, evidence)
            self.routes.back()
            for source, suffix, outcome in (
                    ('note.txt', 'note.txt', 'complete'), ('folder', 'folder', 'complete'),
                    ('note.txt', 'cancelled.txt', 'cancelled'), ('note.txt', 'failed.txt', 'failed')):
                assert await self.open_picker_folder(dict(kind='remote', value=('Secret', 'fixtures'),
                    source='Remote', remote='Secret', name='Secret'))
                row = next(row for row in self.cloud_rows.values() if row['name'] == source)
                await self.download_remote_item(row)
                picker = self.editor_picker()
                await picker.browser_editor_location((picker_storage, parent.name))
                target = f'{theme}-{suffix}'
                picker.save_as_name.value = target
                started, release = Event(), Event()

                def hold(progress, cancelled):
                    progress(phase='Transferring', done=1, total=2, files=0, total_files=1)
                    started.set()
                    if not release.wait(75):
                        raise TimeoutError('Download sample did not release the fixture')
                    check_cancelled(cancelled)
                    if outcome == 'failed':
                        raise OSError('Synthetic read failure')

                def gated_file(job, active, **kwargs):
                    hold(kwargs['progress'], kwargs['cancelled'])
                    return copy_file(job, active, **kwargs)

                def gated_folder(root, remote, path, destination, name, cancelled, progress, *arguments):
                    hold(progress, cancelled)
                    return copy_folder(root, remote, path, destination, name, cancelled, progress, *arguments)

                with patch.object(remote_downloads, 'sync_copy', side_effect=gated_file), \
                        patch.object(folder_recovery, 'run_folder_download', side_effect=gated_folder), \
                        patch.object(self.main_window, 'dialog', new=AsyncMock(return_value=True)):
                    task = asyncio.create_task(picker.complete_destination())
                    try:
                        await until(started.is_set, 'Selected download never entered the worker')
                        progress = self.transfer_view
                        await until(lambda: progress.model.get('percentage') == 50, 'No live progress displayed')
                        await self.sample(progress, theme + '-running-' + suffix, report, evidence)
                        if source == 'folder':
                            # Drive an actual scene/activity transition on the owned emulator.
                            ready = Path(self.paths.cache) / 'transfer-resumed'
                            ready.unlink(missing_ok=True)
                            (Path(self.paths.cache) / 'transfer-background').touch()
                            await until(ready.exists, 'Native background/resume was not acknowledged')
                            await wait_for_transfer_surface(progress, timeout=12)
                            await self.sample(progress, theme + '-resumed', report, evidence)
                        if outcome == 'cancelled':
                            await progress.native_fallback.buttons.children[0].on_press()
                        if outcome == 'complete':
                            await progress.native_fallback.buttons.children[-1].on_press()
                            assert await self.show_files(location=(browser_storage, parent.name))
                            await asyncio.sleep(.3)
                            await browser.select(next(entry for entry in browser.entries if entry.label == 'keep-10.txt'))
                            browser.vertical_position = 240
                            await asyncio.sleep(.2)
                            body, selected, location = self.body, browser.selected, browser.location
                            history = list(browser.history.locations)
                            position = browser.vertical_position
                    finally:
                        release.set()
                        completed = await task
                assert completed == (outcome == 'complete'), self.transfer_message
                if completed:
                    assert self.body is body
                    assert browser.location == location and browser.selected == selected, (browser.location, location)
                    assert browser.history.locations == history
                    assert browser.vertical_position >= position - 12, (browser.vertical_position, position)
                    assert target in {entry.label for entry in browser.entries}
                    self.show_transfers(detail=True)
                assert progress.model['phase'] == outcome, progress.model
                await self.sample(progress, theme + '-' + outcome + '-' + suffix, report, evidence)
                self.routes.back()
                assert (parent / target).exists() == completed
                assert not any(path.name.startswith('.download-') for path in parent.iterdir())
            assert (parent / f'{theme}-note.txt').read_text() == 'Selected crypt file'
            assert (parent / f'{theme}-folder/child.txt').read_text() == 'Selected crypt folder'
        report['selected_crypt_file_and_folder'] = True
        report['cancel_and_failure_cleanup'] = True
        report['background_resume_both_appearances'] = True

        if sys.platform == 'ios':
            from rubicon.objc import ObjCClass
            from mobile.fold_layout import is_iphone_duo
            expect_wide = int(ObjCClass('UIDevice').currentDevice.userInterfaceIdiom) == 1 or is_iphone_duo()
        else:
            expect_wide = self._impl.native.getResources().getConfiguration().smallestScreenWidthDp >= 600
            if expect_wide:
                (Path(self.paths.cache) / 'creation-orientation').write_text('landscape-left')
        if expect_wide:
            await rotate(self, 'landscape-left', timeout=30)
        self.change_folder_source('rclone')
        self.show_locations()
        assert await self.refresh_folder_hub()
        if expect_wide:
            await until(lambda: self.adaptive.wide, 'Workspaces did not enter its wide layout')
        workspace = next((name for name, entry in self.folder_picker_choices.items()
                          if any(copy.get('remote') == 'Secret' and copy['source'] == 'Remote'
                                 for copy in (entry, *entry.get('copies', ())))), None)
        assert workspace in self.folder_buttons, tuple(self.folder_buttons)
        overview = self.body
        self.transfer_busy = True
        self.set_cloud_busy(True)
        try:
            assert not await self.folder_buttons[workspace].on_press()
            assert self.routes.screens['files'][-1][0] == 'workspace-status'
            frame = self.body.children[0]._workspace_frame
            assert frame.folder_detail
            assert any(getattr(child, 'text', '') == 'View transfers' for child in frame.main.children)
            columns = getattr(self.adaptive, 'file_columns', None)
            if expect_wide and columns is None:
                assert frame.folder_master in frame.row.children
            elif expect_wide:
                assert columns.sidebar.native.bounds.size.width > 0
                assert columns.navigation.view.bounds.size.width > 0
            report['workspace_while_busy'] = dict(wide=self.adaptive.wide,
                native_columns=columns is not None)
            await capture_window(self, evidence / 'workspace-transfer-status.png')
        finally:
            self.transfer_busy = False
            self.set_cloud_busy(False)
        await until(lambda: self.body is overview, 'Workspaces did not return after the transfer')
        assert await self.folder_buttons[workspace].on_press(), self.cloud_status.value
        assert self.routes.screens['files'][-1][0].startswith(('remote-browser', 'folder:remote-browser:'))
        report['workspace_remote_reopens_after_transfer'] = True


def main():
    return RcloneTransferProbe('Transfer QA', 'io.github.ispaure.logisticsnotebookqa')
