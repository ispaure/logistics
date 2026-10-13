"""Reproduce a cooperative callback entered with another running-loop context."""
import asyncio
from asyncio import events
import unittest
from logisticsmobile.native_loop import bind_cooperative_loop


class NativeLoopTests(unittest.TestCase):
    def test_callback_owns_its_loop_and_restores_the_native_caller_context(self):
        owned, caller = asyncio.new_event_loop(), asyncio.new_event_loop()
        previous = events._get_running_loop()
        observed = []
        try:
            owned.run_delayed_tasks = owned._run_once
            bind_cooperative_loop(owned)
            async def task():
                observed.append(asyncio.get_running_loop())
                observed.append(asyncio.current_task().get_loop())
                observed.append(asyncio.get_event_loop().create_future().get_loop())
            pending = owned.create_task(task())
            events._set_running_loop(caller)
            owned.run_delayed_tasks()
            self.assertEqual(observed, [owned, owned, owned])
            self.assertTrue(pending.done())
            self.assertIsNone(pending.exception())
            self.assertIs(asyncio.get_running_loop(), caller)
            wrapped = owned.run_delayed_tasks
            bind_cooperative_loop(owned)
            self.assertIs(owned.run_delayed_tasks, wrapped)
        finally:
            events._set_running_loop(previous)
            owned.close()
            caller.close()
            asyncio.set_event_loop(None)
