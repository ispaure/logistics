"""Idle readers have no periodic layout wakeups or strong host subscriptions."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import gc
from types import SimpleNamespace
import unittest
from mobile.layout_events import defer_host_resize, layout_waiter, notify_layout


class LayoutEventTests(unittest.TestCase):
    def test_apple_defers_only_host_work_and_coalesces_the_latest_layout(self):
        from unittest.mock import Mock
        backend = type('Backend', (), {'__module__': 'toga_iOS.app'})
        app = SimpleNamespace(_impl=backend(), loop=Mock(), active_host=True)
        first, latest = Mock(), Mock()
        self.assertTrue(defer_host_resize(app, 'first', first))
        self.assertTrue(defer_host_resize(app, 'latest', latest))
        first.assert_not_called()
        latest.assert_not_called()
        app.loop.call_soon.assert_called_once()
        app.loop.call_soon.call_args.args[0]()
        latest.assert_called_once_with('latest')
        first.assert_not_called()
        self.assertIsNone(app._pending_host_resize)
        self.assertFalse(app._host_resize_scheduled)

    def test_retired_apple_host_drops_queued_work_and_android_stays_synchronous(self):
        from unittest.mock import Mock
        backend = type('Backend', (), {'__module__': 'toga_iOS.app'})
        app = SimpleNamespace(_impl=backend(), loop=Mock(), active_host=True)
        callback = Mock()
        defer_host_resize(app, 'window', callback)
        app.active_host = False
        app.loop.call_soon.call_args.args[0]()
        callback.assert_not_called()
        app._reset_scheduled = True
        defer_host_resize(app, 'reset-window', callback)
        app.loop.call_soon.call_args.args[0]()
        callback.assert_called_once_with('reset-window')
        app._impl = type('Backend', (), {'__module__': 'toga_android.app'})()
        self.assertFalse(defer_host_resize(app, 'window', callback))
        self.assertEqual(app.loop.call_soon.call_count, 2)

    def test_notifications_coalesce_and_idle_wait_is_cancelled_on_retirement(self):
        async def exercise():
            app = SimpleNamespace()
            changed = layout_waiter(app)
            await changed()
            task = asyncio.create_task(changed())
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            for _ in range(100):
                notify_layout(app)
            await task
            task = asyncio.create_task(changed())
            await asyncio.sleep(0)
            self.assertFalse(task.done())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            return app
        app = asyncio.run(exercise())
        gc.collect()
        self.assertEqual(len(app._reader_layout_signal._listeners), 0)
