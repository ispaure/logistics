"""Native transfer review/progress acceptance using read-only synthetic data."""
import asyncio
import json
from pathlib import Path
from time import monotonic
import traceback
from uuid import uuid4
from unittest.mock import AsyncMock, patch

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
        self.storage_root = Path(self.paths.cache) / ('transfer-' + uuid4().hex)
        super().startup()

    def on_running(self):
        start_native_check(self, type(self).probe)

    async def wait_surface(self, surface):
        for _ in range(150):
            if surface.ready and surface.delivered_revision == surface.revision and surface.revision:
                return
            await asyncio.sleep(.1)
        raise AssertionError('Transfer web surface did not render: ' + str((surface.ready, surface.revision, surface.delivered_revision)))

    async def js(self, surface, script):
        return await surface.web.evaluate_javascript(script)

    async def sample(self, surface, name, report, evidence):
        await self.wait_surface(surface)
        await asyncio.sleep(.2)
        data = json.loads(await self.js(surface, "JSON.stringify((()=>{const r=el=>{const b=el.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height,right:b.right,bottom:b.bottom}};const button=document.getElementById('approve')||document.getElementById('background');return {viewport:{width:innerWidth,height:innerHeight},body:document.body.scrollWidth,action:r(button),list:document.querySelector('.file-list')?r(document.querySelector('.file-list')):null,inspect:window.Transfer.inspect(),smallTargets:[...document.querySelectorAll('button')].filter(el=>{const b=el.getBoundingClientRect();return b.width>0&&b.height>0&&!el.hidden&&(b.width<43||b.height<43)}).map(el=>el.textContent)}})())"))
        data['name'] = name
        report['samples'].append(data)
        await capture_window(self, evidence / (name + '.png'))
        assert not data['smallTargets'], data
        assert data['body'] <= data['viewport']['width'] + 1, data
        assert data['action']['bottom'] <= data['viewport']['height'] + 1, data
        assert data['action']['right'] <= data['viewport']['width'] + 1, data
        if data['list']:
            assert data['list']['height'] >= 90, data
            assert data['inspect']['rows'] <= 30, data

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
            self.loaded_remote_names = lambda: ['Personal', 'Backup']
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
            self.show_transfers()
            for name, values in (
                ('progress', dict(phase='Transferring', files=28, total_files=64, done=125000000,
                    total=250000000, active=2, listed=82, checks=18,
                    active_files=[dict(name='Photos/Autumn/Maples.jpg', bytes=1200000, size=3200000),
                                  dict(name='Projects/Research/Planning notes.md', bytes=8600, size=12000)])),
                ('progress-unknown', dict(phase='Discovering / checking files', files=0, done=0, total=0, listed=82, checks=18)),
                ('progress-verify', dict(phase='Sync complete; verifying local copy', files=64, done=250000000, total=250000000))):
                self.publish_mirror_progress(1, values)
                await self.sample(self.transfer_view, name, report, evidence)
            # Leave the screen through its real action; updates must remain offscreen.
            self.publish_mirror_progress(1, dict(phase='Transferring', files=28, done=125000000, total=250000000))
            await self.wait_surface(self.transfer_view)
            hidden_surface = self.transfer_view
            await self.js(hidden_surface, "document.getElementById('background').click()")
            await asyncio.sleep(.2)
            delivered = hidden_surface.delivered_revision
            self.publish_mirror_progress(1, dict(phase='Transferring', files=29, done=126000000, total=250000000))
            await asyncio.sleep(.2)
            assert hidden_surface.delivered_revision == delivered
            assert hidden_surface.send_task is None
            self.show_transfers()
            await self.wait_surface(hidden_surface)
            await self.js(hidden_surface, "window.savedPercentNode=document.querySelector('.number');true")
            self.publish_mirror_progress(1, dict(phase='Transferring', files=30, done=127000000, total=250000000))
            await self.wait_surface(hidden_surface)
            assert await self.js(hidden_surface, "window.savedPercentNode===document.querySelector('.number')")
            report['offscreen_updates_suppressed'] = True
            report['progress_dom_preserved'] = True
            state.busy, state.complete, state.result = False, True, 'complete'
            state.finished_at = monotonic()
            owner.render_transfer_summary()
            await self.sample(self.transfer_view, 'progress-complete', report, evidence)
            state.complete, state.result = False, 'failed'
            state.message = 'Connection lost. Completed changes remain.'
            owner.render_transfer_summary()
            await self.sample(self.transfer_view, 'progress-failed', report, evidence)
            self.routes.return_to('files')
            self.transfer_busy = self.transfer_notification = False

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

                assert not await self.js(surface, "!!document.querySelector('#file-list img')")
                if many:
                    await self.js(surface, "document.querySelector('[data-action=next]').click()")
                    await asyncio.sleep(.3)
                    await self.sample(surface, 'review-next-page', report, evidence)
                    assert surface.model['page'] == 1
                await self.js(surface, "document.querySelector('[data-filter=delete]').click()")
                await asyncio.sleep(.3)
                await self.sample(surface, 'delete-' + suffix, report, evidence)
                assert surface.model['rows'] == (('delete', 'Archives/old-backup.zip'),)
                await self.js(surface, "document.querySelector('[data-file]').click()")
                await asyncio.sleep(.2)
                await capture_window(self, evidence / ('selected-' + suffix + '.png'))
                if operation == 'Pull':
                    await rotate(self, 'landscape-left', settle=.3)
                    await self.sample(surface, 'review-landscape', report, evidence)
                    await rotate(self, 'portrait', settle=.3)
                await self.js(surface, "document.querySelector('[data-local=close]')?.click()")
                if operation == 'Push' and not many:
                    # Exercise the actual WebView command -> native confirmation ->
                    # ReviewSession path. No executor is attached to this fixture.
                    declined = AsyncMock(return_value=False)
                    with patch.object(self.main_window, 'dialog', new=declined):
                        await self.js(surface, "document.getElementById('approve').click()")
                        for _ in range(40):
                            if declined.await_count:
                                break
                            await asyncio.sleep(.05)
                        assert declined.await_count == 1
                        assert not session.approved and not surface.closed
                    await self.wait_surface(surface)
                    accepted = AsyncMock(return_value=True)
                    with patch.object(self.main_window, 'dialog', new=accepted):
                        await self.js(surface, "document.getElementById('approve').click()")
                        assert await asyncio.wait_for(task, 5)
                        assert accepted.await_count == 1 and session.approved
                    report['web_approval_and_decline'] = True
                else:
                    active[0] = False
                    await task
                assert surface.closed and not surface.model
                session = task = None
            report['success'] = True
        except Exception:
            report['error'] = traceback.format_exc()
        finally:
            if session is not None:
                session.cancel()
            if task is not None:
                await task
            (Path(self.paths.cache) / 'rclone-transfer-result.json').write_text(json.dumps(report, indent=2))


def main():
    return RcloneTransferProbe('Transfer QA', 'io.github.ispaure.logisticsnotebookqa')
