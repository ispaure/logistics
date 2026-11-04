"""Native review driver follows fresh completed comparisons, with a hard bound."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace as State
import unittest
from unittest.mock import AsyncMock, patch
from mobile_build.native_tests.tests.logisticsmobile.review_checks import approve_transfer, wait_for_held_review, save_transfer_settings, cancel_review, press_review


class NativeReviewDriverTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_fallback_click_uses_revision_guard_and_restores_observer(self):
        from features.rclone.transfers.mobile.surface import TransferSurface
        handler = AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1, pending=None,
            host=State(active_host=True), model=dict(can_confirm=True), handler=handler, web=None)
        view.native_fallback = State(buttons=State(children=[]))
        clicks = []
        def button(revision):
            async def press():
                clicks.append(revision)
                if len(clicks) == 1:
                    view.revision = view.delivered_revision = 2
                    view.native_fallback.buttons.children = [button(2)]
                await TransferSurface.dispatch(view, 'approve', dict(revision=str(revision)))
            return State(text='Approve Push', enabled=True, on_press=press)
        view.native_fallback.buttons.children = [button(1)]
        with patch('mobile_build.native_tests.tests.logisticsmobile.review_checks.verify_native_transfer_fallback') as verify:
            await press_review(view, 'approve', timeout=1)
        self.assertEqual(clicks, [1, 2])
        handler.assert_awaited_once_with('approve', dict(revision='2'))
        self.assertIs(view.handler, handler)
        self.assertEqual(verify.call_count, 2)

    async def test_native_button_without_guarded_acceptance_cannot_pass(self):
        handler, press = AsyncMock(), AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1,
            handler=handler, web=None, native_fallback=State(buttons=State(children=[
                State(text='Proceed without full review…', enabled=True, on_press=press)])))
        with patch('mobile_build.native_tests.tests.logisticsmobile.review_checks.verify_native_transfer_fallback'):
            with self.assertRaisesRegex(AssertionError, 'not accepted: early'):
                await press_review(view, 'early', timeout=.01)
        press.assert_awaited_once()
        handler.assert_not_awaited()
        self.assertIs(view.handler, handler)

    async def test_invalid_native_fallback_restores_observer_without_pressing(self):
        handler, press = AsyncMock(), AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1,
            handler=handler, web=None, native_fallback=State(buttons=State(children=[
                State(text='Approve Push', enabled=True, on_press=press)])))
        with patch('mobile_build.native_tests.tests.logisticsmobile.review_checks.verify_native_transfer_fallback',
                side_effect=AssertionError('Native review rows are stale')):
            with self.assertRaisesRegex(AssertionError, 'rows are stale'):
                await press_review(view, 'approve', timeout=.01)
        press.assert_not_awaited()
        handler.assert_not_awaited()
        self.assertIs(view.handler, handler)

    async def test_delayed_native_acceptance_does_not_issue_an_extra_click(self):
        from unittest.mock import AsyncMock
        from features.rclone.transfers.mobile.surface import TransferSurface
        handler = AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1,
            pending=None, host=State(active_host=True), model=dict(can_confirm=True), handler=handler)
        clicks = []
        tasks = []
        async def evaluate(script):
            clicks.append(view.revision)
            def delivered():
                tasks.append(asyncio.create_task(TransferSurface.dispatch(
                    view, 'approve', dict(revision=str(view.revision)))))
            asyncio.get_running_loop().call_later(.01, delivered)
            return True
        view.web = State(evaluate_javascript=evaluate)
        await press_review(view, 'approve', timeout=1)
        await asyncio.sleep(.03)
        await asyncio.gather(*tasks)
        self.assertEqual(clicks, [1])
        handler.assert_awaited_once()

    async def test_click_waits_for_native_acceptance_after_a_stale_revision(self):
        from unittest.mock import AsyncMock
        from features.rclone.transfers.mobile.surface import TransferSurface
        handler = AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1,
            pending=None, host=State(active_host=True), model=dict(can_early=True), handler=handler)
        clicks = []
        async def evaluate(script):
            revision = view.revision
            clicks.append(revision)
            if len(clicks) == 1:
                # Native comparison progress lands after the DOM click, before
                # its navigation message is dispatched. Keep the real guard.
                view.revision += 1
                view.delivered_revision = view.revision
            await TransferSurface.dispatch(view, 'early', dict(revision=str(revision)))
            return True
        view.web = State(evaluate_javascript=evaluate)
        await press_review(view, 'early', timeout=1)
        self.assertEqual(clicks, [1, 2])
        handler.assert_awaited_once_with('early', dict(revision='2'))

    async def test_dom_click_without_native_acceptance_fails(self):
        from unittest.mock import AsyncMock
        handler = AsyncMock()
        view = State(ready=True, closed=False, revision=1, delivered_revision=1,
            handler=handler, web=State(evaluate_javascript=AsyncMock(return_value=True)))
        with self.assertRaisesRegex(AssertionError, 'not accepted: early'):
            await press_review(view, 'early', timeout=.01)
        handler.assert_not_awaited()
        self.assertIs(view.handler, handler)

    def test_review_cancellation_uses_native_ios_back(self):
        from unittest.mock import Mock, patch
        from commonUtils.runtime.platform import OS
        navigation = State(popViewControllerAnimated=Mock())
        app = State(native_host=State(destinations=['files'], adapter=State(navigation=[navigation])))
        with patch('commonUtils.runtime.platform.get_os', return_value=OS.IOS):
            cancel_review(app)
        navigation.popViewControllerAnimated.assert_called_once_with(True)

    def test_review_cancellation_uses_native_android_back(self):
        from unittest.mock import Mock, patch
        from commonUtils.runtime.platform import OS
        dispatch = State(onBackPressed=Mock())
        activity = State(getOnBackPressedDispatcher=lambda: dispatch)
        app = State(native_host=State(adapter=State(impl=State(_native_activity=activity))))
        with patch('commonUtils.runtime.platform.get_os', return_value=OS.ANDROID):
            cancel_review(app)
        dispatch.onBackPressed.assert_called_once_with()

    def app(self, *, changes=1, finish=True):
        result = asyncio.get_running_loop().create_future()
        calls = []
        view = State(model=dict(complete=True, can_confirm=True, can_early=True, notice=''),
                     ready=True, closed=False, revision=1, delivered_revision=1)
        app = State(_transfer_review_view=view, transfer_task=result,
            main_window=State(dialog=None), cloud_status=State(value='Ready'),
            transfer_message='Transferring fixture')
        async def handle(action, args):
            await app.main_window.dialog(object())
            calls.append(True)
            view.revision += 1
            view.delivered_revision = view.revision
            if len(calls) <= changes:
                view.model['notice'] = 'Files changed. Review the updated results before confirming again.'
            else:
                view.model['notice'] = 'Checking that the completed review is still current…'
                view.model['can_confirm'] = False
                if finish:result.set_result(True)
        view.handler = handle
        async def evaluate(script):
            if '#approve' not in script or not view.model['can_confirm']:
                return False
            await view.handler('approve', dict(revision=str(view.revision)))
            return True
        view.web = State(evaluate_javascript=evaluate)
        self.addCleanup(lambda: result.cancel() if not result.done() else None)
        return app, calls

    def test_settings_save_finds_actions_moved_out_of_the_form(self):
        saved = []
        rename, bandwidth, excludes = State(value=False), State(value=''), State(value='*.tmp')
        form = State(children=[State(text='Transfer settings'), rename,
            State(text='Bandwidth limit (MB/s)'), bandwidth,
            State(text='Push exclusions (one pattern per line)'), excludes, State(text='Status')])
        save = State(text='Save settings', on_press=lambda: saved.append(True))
        app = State(body=State(children=[form, State(children=[save])]), show_transfer_options=lambda: None)
        save_transfer_settings(app)
        self.assertEqual(saved, [True])
        self.assertTrue(rename.value)
        self.assertEqual(bandwidth.value, '1')
        self.assertIn('*.skip', excludes.value)

    def test_settings_save_follows_promoted_ios_toolbar_action(self):
        saved = []
        save = State(text='Save settings', on_press=lambda: saved.append(True))
        form = State(children=[State(text='Transfer settings'), State(value=False),
            State(text='Bandwidth limit (MB/s)'), State(value=''),
            State(text='Push exclusions (one pattern per line)'), State(value='*.tmp'), State(text='Status')],
            _ios_toolbar_buttons=[save])
        app = State(body=State(children=[form]), show_transfer_options=lambda: None)
        save_transfer_settings(app)
        self.assertEqual(saved, [True])
        self.assertTrue(form.children[1].value)
        self.assertEqual(form.children[3].value, '1')

    async def test_confirms_changed_completed_review_again(self):
        app, calls = self.app()
        await approve_transfer(app, timeout=1)
        self.assertEqual(len(calls), 2)
        self.assertTrue(app.transfer_task.result())

    async def test_approval_waits_for_the_current_rendered_revision(self):
        app, calls = self.app(changes=0)
        view = app._transfer_review_view
        view.delivered_revision = 0
        task = asyncio.create_task(approve_transfer(app, timeout=1))
        await asyncio.sleep(.06)
        self.assertFalse(task.done())
        self.assertEqual(calls, [])
        view.delivered_revision = view.revision
        await task
        self.assertEqual(len(calls), 1)

    async def test_repeated_changes_fail_instead_of_auto_approving_forever(self):
        app, calls = self.app(changes=10)
        with self.assertRaisesRegex(AssertionError, 'three fresh confirmations'):
            await approve_transfer(app, timeout=2)
        self.assertEqual(len(calls), 4)

    async def test_timeout_reports_phase_and_does_not_cancel_transfer(self):
        app, _ = self.app(changes=0, finish=False)
        with self.assertRaisesRegex(AssertionError, 'Checking that the completed review is still current'):
            await approve_transfer(app, timeout=.01)
        self.assertFalse(app.transfer_task.cancelled())

    async def test_early_review_waits_for_actual_held_result_not_just_visible_incomplete(self):
        from threading import Event
        app, _ = self.app(changes=0, finish=False)
        app._transfer_review_view.model.update(complete=False, can_confirm=False)
        held = Event()
        task = asyncio.create_task(wait_for_held_review(app, held, timeout=2))
        await asyncio.sleep(.06)
        self.assertFalse(task.done())
        held.set()
        self.assertIs(await task, app._transfer_review_view)

    async def test_missing_held_native_result_fails_with_a_bound(self):
        from threading import Event
        app, _ = self.app(changes=0, finish=False)
        app._transfer_review_view.model.update(complete=False, can_confirm=False)
        with self.assertRaisesRegex(AssertionError, 'never reached the held-result fixture'):
            await wait_for_held_review(app, Event(), timeout=.01)
        self.assertFalse(app.transfer_task.cancelled())
