"""Executor allocations must not finalize retired native UI cycles."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from ctypes import c_void_p
import gc
import sys
import threading
from types import SimpleNamespace
import unittest
import weakref
from unittest.mock import Mock, patch

from mobile.cycle_collection import UICycleCollection, bind_ios_timer_ownership


class CycleCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rubicon_retires_each_timer_once_before_user_code_or_collection(self):
        loop = asyncio.get_running_loop()
        loop._timers = set()
        loop._cfrunloop = object()
        cf = Mock()
        cf.CFAbsoluteTimeGetCurrent.return_value = 100
        cf.CFRunLoopTimerCreate.side_effect = (c_void_p(1000), c_void_p(2000))
        eventloop = SimpleNamespace(CFTimerHandle=object, libcf=cf, CFRunLoopTimerRef=c_void_p,
                                    CFRunLoopTimerCallBack=lambda callback: callback,
                                    kCFRunLoopCommonModes=object())
        with patch.dict(sys.modules, {'rubicon.objc': SimpleNamespace(eventloop=eventloop)}), \
                patch('importlib.metadata.version', return_value='0.5.7'):
            bind_ios_timer_ownership()
            handle_type = eventloop.CFTimerHandle
            bind_ios_timer_ownership()
            self.assertIs(eventloop.CFTimerHandle, handle_type)

        calls_at_dispatch = []

        def run_callback(arg):
            calls_at_dispatch.extend(cf.mock_calls)
            firing_handle().cancel()
            gc.collect()

        callback = Mock(side_effect=run_callback)
        fired = handle_type(loop=loop, timeout=1, callback=callback, args=('fired',))
        firing_handle = weakref.ref(fired)
        cancelled = handle_type(loop=loop, timeout=2, callback=callback, args=('cancelled',))
        first, second = fired._timer, cancelled._timer
        dispatch = cf.CFRunLoopTimerCreate.call_args_list[0].args[5]
        self.assertIs(dispatch, cf.CFRunLoopTimerCreate.call_args_list[1].args[5])
        dispatch(first, None)
        cancelled.cancel()
        cancelled.cancel()
        dispatch(second, None)  # Native delivery that was already queued.
        self.assertTrue(cancelled.cancelled())
        self.assertFalse(loop._timers)
        callback.assert_called_once_with('fired')
        self.assertEqual([call[0] for call in calls_at_dispatch[-2:]],
                         ['CFRunLoopTimerInvalidate', 'CFRelease'])
        references = weakref.ref(fired), weakref.ref(cancelled)
        del fired, cancelled
        gc.collect()
        self.assertTrue(all(reference() is None for reference in references))
        self.assertEqual([call.args[0] for call in cf.CFRunLoopTimerInvalidate.call_args_list], [first, second])
        self.assertEqual([call.args[0] for call in cf.CFRelease.call_args_list], [first, second])

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
