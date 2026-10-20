"""Idle readers have no periodic layout wakeups or strong host subscriptions."""
import asyncio
import gc
from types import SimpleNamespace
import unittest
from logisticsmobile.layout_events import layout_waiter, notify_layout


class LayoutEventTests(unittest.TestCase):
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
        self.assertEqual(len(app._reader_layout_events), 0)
