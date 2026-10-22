"""Native review driver follows fresh completed comparisons, with a hard bound."""
import asyncio
from types import SimpleNamespace as State
import unittest
from mobile_build.native_tests.tests.logisticsmobile.review_checks import approve_transfer, wait_for_held_review, save_transfer_settings


class NativeReviewDriverTests(unittest.IsolatedAsyncioTestCase):
    def app(self, *, changes=1, finish=True):
        result = asyncio.get_running_loop().create_future()
        calls = []
        status = State(text='Review complete')
        button = State(enabled=True)
        async def confirm():
            calls.append(True)
            if len(calls) <= changes:
                status.text = 'Files changed or could not be checked. Review the current results and confirm again.'
            else:
                status.text = 'Checking that the completed review is still current…'
                button.enabled = False
                if finish:result.set_result(True)
        button.on_press = confirm
        view = State(children=[None, None, status, None, None, State(children=[None, button])])
        app = State(_transfer_review_view=view, transfer_task=result,
            main_window=State(dialog=None), transfer_message='Transferring fixture')
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
        app._transfer_review_view.children[3] = State(value='Review incomplete')
        held = Event()
        task = asyncio.create_task(wait_for_held_review(app, held, timeout=2))
        await asyncio.sleep(.06)
        self.assertFalse(task.done())
        held.set()
        self.assertIs(await task, app._transfer_review_view)

    async def test_missing_held_native_result_fails_with_a_bound(self):
        from threading import Event
        app, _ = self.app(changes=0, finish=False)
        app._transfer_review_view.children[3] = State(value='Review incomplete')
        with self.assertRaisesRegex(AssertionError, 'never reached the held-result fixture'):
            await wait_for_held_review(app, Event(), timeout=.01)
        self.assertFalse(app.transfer_task.cancelled())
