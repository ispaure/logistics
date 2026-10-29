"""Executor allocations must not finalize retired native UI cycles."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import gc
import threading
import unittest
import weakref
from unittest.mock import patch

from mobile.cycle_collection import UICycleCollection


class CycleCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_allocations_leave_finalization_to_ui_loop(self):
        loop = asyncio.get_running_loop()
        was_enabled = gc.isenabled()
        owner = UICycleCollection(loop, interval=.01)
        finalized = []

        class NativeCycle:
            def __init__(self):
                self.cycle = self

            def __del__(self):
                finalized.append(threading.current_thread())

        try:
            gc.collect()
            widget = NativeCycle()
            reference = weakref.ref(widget)
            del widget

            def allocate():
                for _ in range(10000):
                    cycle = []
                    cycle.append(cycle)
                return [thread for thread in finalized if thread is not threading.main_thread()]

            self.assertEqual(await asyncio.to_thread(allocate), [])
            for _ in range(100):
                if reference() is None:
                    break
                await asyncio.sleep(.01)
            self.assertIsNone(reference())
            self.assertEqual(finalized, [threading.main_thread()])
        finally:
            owner.close()
            gc.collect()
        self.assertEqual(gc.isenabled(), was_enabled)

    async def test_generation_pressure_and_disabled_threshold(self):
        owner = UICycleCollection(asyncio.get_running_loop())
        try:
            for counts, thresholds, expected in (
                ((701, 0, 0), (700, 10, 10), 0),
                ((701, 11, 0), (700, 10, 10), 1),
                ((701, 0, 11), (700, 10, 10), 2),
                ((700, 0, 0), (700, 10, 10), None),
                ((900, 0, 0), (0, 10, 10), None),
            ):
                owner.pending.cancel()
                with patch('mobile.cycle_collection.gc.get_count', return_value=counts), \
                        patch('mobile.cycle_collection.gc.get_threshold', return_value=thresholds), \
                        patch('mobile.cycle_collection.gc.collect') as collect:
                    owner.collect_due()
                    if expected is None:
                        collect.assert_not_called()
                    else:
                        collect.assert_called_once_with(expected)
        finally:
            owner.close()

    async def test_closed_owner_cannot_restart_or_change_disabled_gc(self):
        original = gc.isenabled()
        gc.disable()
        try:
            owner = UICycleCollection(asyncio.get_running_loop())
            pending = owner.pending
            owner.close()
            owner.close()
            owner.collect_due()
            self.assertTrue(pending.cancelled())
            self.assertIsNone(owner.pending)
            self.assertFalse(gc.isenabled())
        finally:
            if original:
                gc.enable()

    async def test_worker_cannot_start_native_collection(self):
        with self.assertRaisesRegex(RuntimeError, 'UI thread'):
            await asyncio.to_thread(UICycleCollection, asyncio.get_running_loop())

    async def test_failed_timer_registration_restores_gc(self):
        was_enabled = gc.isenabled()
        with patch.object(asyncio.get_running_loop(), 'call_later', side_effect=RuntimeError('closed')):
            with self.assertRaisesRegex(RuntimeError, 'closed'):
                UICycleCollection(asyncio.get_running_loop())
        self.assertEqual(gc.isenabled(), was_enabled)
