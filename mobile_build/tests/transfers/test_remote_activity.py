"""Progress lifetime and worker callbacks without constructing native controls."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import unittest
from unittest.mock import Mock

from features.rclone.mobile.activity import RemoteActivity


class RemoteActivityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.view = Mock()
        self.activity = RemoteActivity(self.view)

    async def test_nested_requests_share_timer_and_restore_outer_worker_progress(self):
        async with self.activity.track('Opening') as outer:
            timer = self.activity._timer
            async with self.activity.track('Listing') as inner:
                self.assertIs(self.activity._timer, timer)
                await asyncio.to_thread(outer, 'Decoding')
                self.assertEqual(self.view.show.call_args.args[0], 'Listing · 0s')
                await asyncio.to_thread(inner, 'Rendering')
                self.assertEqual(self.view.show.call_args.args[0], 'Rendering · 0s')
            self.assertEqual(self.view.show.call_args.args[0], 'Decoding · 0s')
            self.view.stop.assert_not_called()
        self.view.start.assert_called_once_with()
        self.view.stop.assert_called_once_with()
        self.assertTrue(timer.done())
        self.assertIsNone(self.activity._timer)

    async def test_callback_queued_before_retirement_cannot_restore_finished_status(self):
        async with self.activity.track('Opening') as progress:
            progress('Queued but obsolete')
        await asyncio.sleep(0)
        progress('Late worker')
        await asyncio.sleep(0)
        self.assertNotIn('Queued but obsolete · 0s', [call.args[0] for call in self.view.show.call_args_list])
        self.assertNotIn('Late worker · 0s', [call.args[0] for call in self.view.show.call_args_list])
        self.view.stop.assert_called_once_with()

    async def test_cancelled_request_retires_timer_and_can_be_retried(self):
        started = asyncio.Event()
        async def request():
            async with self.activity.track('Waiting'):
                started.set()
                await asyncio.Event().wait()
        task = asyncio.create_task(request())
        await started.wait()
        timer = self.activity._timer
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(timer.done())
        self.assertIsNone(self.activity._timer)
        async with self.activity.track('Retry'):
            self.assertEqual(self.view.show.call_args.args[0], 'Retry · 0s')
        self.assertEqual(self.view.stop.call_count, 2)

    async def test_failed_request_releases_progress_and_propagates_error(self):
        with self.assertRaisesRegex(OSError, 'offline'):
            async with self.activity.track('Opening'):
                raise OSError('offline')
        self.assertIsNone(self.activity._timer)
        self.view.stop.assert_called_once_with()

    async def test_overlapping_requests_can_retire_out_of_order(self):
        first = self.activity.track('First')
        second = self.activity.track('Second')
        await first.__aenter__()
        await second.__aenter__()
        timer = self.activity._timer
        await first.__aexit__(None, None, None)
        self.assertEqual(self.view.show.call_args.args[0], 'Second · 0s')
        self.view.stop.assert_not_called()
        await second.__aexit__(None, None, None)
        self.assertTrue(timer.done())
        self.view.stop.assert_called_once_with()
