"""Native review driver follows fresh completed comparisons, with a hard bound."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from types import SimpleNamespace as State
import unittest
from mobile_build.native_tests.tests.logisticsmobile.review_checks import approve_transfer, wait_for_held_review, save_transfer_settings, cancel_review


class NativeReviewDriverTests(unittest.IsolatedAsyncioTestCase):
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
        async def evaluate(script):
            if '#approve' not in script or not view.model['can_confirm']:
                return False
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
