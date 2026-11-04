"""Exercise native transfer recovery without depending on an intermittent OS fault."""
from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
import traceback
from pathlib import Path

from mobile.app import LogisticsMobile
from features.rclone.transfers.mobile import surface as renderer
from . import start_native_check


class StalledSurface(renderer.TransferSurface):
    def create_web(self):
        super().create_web()
        async def unanswered(script):
            await asyncio.Event().wait()
        self.web.evaluate_javascript = unanswered


class RecoveryProbe(LogisticsMobile):
    def on_running(self):
        start_native_check(self, type(self).check)

    async def check(self):
        result = await exercise_recovery(self)
        (Path(self.paths.cache) / 'transfer-recovery-result.json').write_text(json.dumps(result, indent=2))


async def exercise_recovery(app):
    result = dict(success=False)
    surfaces = []
    previous_timeout = renderer.RENDER_TIMEOUT
    renderer.RENDER_TIMEOUT = .1
    try:
        if getattr(app, 'startup_task', None) is not None:
            await asyncio.shield(app.startup_task)
        calls = []
        async def command(action, args):
            calls.append((action, args))
        async def recover(model):
            surface = StalledSurface(app, command)
            surfaces.append(surface)
            surface.update(model)
            app.show_view(surface, route='transfer-recovery', title='Transfer')
            deadline = app.loop.time() + 8
            while surface.native_fallback is None:
                if app.loop.time() >= deadline:
                    raise TimeoutError('Native transfer fallback did not appear.')
                await asyncio.sleep(.05)
            assert surface.recovery_count == 2 and surface.web is None
            assert surface.ready and surface.delivered_revision == surface.revision
            assert surface.native_fallback.parent is surface
            return surface
        surface = await recover(dict(mode='progress', workspace='Recovery fixture',
            source='Local/private', destination='QA:', phase='transfer', busy=True,
            files=2, total_files=4, done=100, total=200, percentage=50,
            active_files=(dict(name='private-file.txt'),)))
        from .web_checks import wait_for_transfer_surface
        proof = await wait_for_transfer_surface(surface, timeout=5)
        assert proof['renderer'] == 'native', proof
        result['native_acceptance_helper'] = proof
        fallback = surface.native_fallback
        assert '50%' in fallback.metrics.text and 'Files: 2 / 4' in fallback.metrics.text
        await fallback.buttons.children[0].on_press()
        assert calls[-1][0] == 'stop'
        await fallback.buttons.children[1].on_press()
        assert calls[-1][0] == 'background'
        surface.update(dict(surface.model, phase='complete', busy=False, files=4, percentage=100))
        assert 'Files: 4 / 4' in fallback.metrics.text
        assert [button.text for button in fallback.buttons.children] == ['Continue browsing']
        result['progress_controls'] = True

        review = await recover(dict(mode='review', workspace='Review fixture', operation='Push',
            source='Local/private', destination='QA:', can_confirm=True, complete=True,
            counts=dict(add=1, delete=1), rows=(('delete', 'private-file.txt'),),
            page=0, page_size=30, total=31))
        fallback = review.native_fallback
        assert 'no undo' in fallback.metrics.text
        approve = next(button for button in fallback.buttons.children if button.text.startswith('Approve'))
        # The review-specific driver waits for actual attachment/layout and
        # checks the displayed native model before clicking its guarded action.
        from .review_checks import press_review
        from .web_checks import verify_native_transfer_fallback
        await press_review(review, 'approve', timeout=5)
        review_proof = verify_native_transfer_fallback(review)
        assert review_proof['renderer'] == 'native' and review_proof['mode'] == 'review'
        result['native_review_acceptance_helper'] = review_proof
        assert calls[-1][0] == 'approve'
        await next(button for button in fallback.buttons.children if button.text == 'Next changes').on_press()
        assert calls[-1][0] == 'next'
        review.update(dict(review.model, can_confirm=False, notice='Files changed'))
        before = len(calls)
        await approve.on_press()
        assert len(calls) == before
        retained = fallback.rows.children[0]
        review.revoke()
        assert retained.text == '' and fallback.paths.text == ''
        await approve.on_press()
        assert len(calls) == before
        result['review_revision_and_lock'] = True

        setup = await recover(dict(mode='setup', workspace='Folder', operation='Push',
            source='Local/Folder', destination='Folder:', remotes=['QA']))
        fallback = setup.native_fallback
        fallback.scope.value = True
        await fallback.scope.on_change()
        assert calls[-1][0] == 'scope' and calls[-1][1]['specific'] == '1'
        await fallback.buttons.children[0].on_press()
        assert calls[-1][0] == 'start-review'
        result['setup_controls'] = True
        result['success'] = True
    except BaseException:
        result['error'] = traceback.format_exc()
    finally:
        renderer.RENDER_TIMEOUT = previous_timeout
        for surface in surfaces:
            surface.dispose()

    return result


def main():
    return RecoveryProbe('Transfer Recovery QA', 'io.github.ispaure.logisticsnotebookqa')
