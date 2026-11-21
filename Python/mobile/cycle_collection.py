"""Own iOS cyclic collection on the UIKit application thread.

Toga's constraint finalizers call UIKit. CPython's automatic collector can run
those finalizers during an unrelated executor allocation, so the iOS process
collects eligible generations from its UI loop instead. Reference counting is
unchanged; background jobs must not explicitly collect native widget cycles.
"""
import asyncio
import atexit
import gc
import threading


class UICycleCollection:
    """Keep generation thresholds while dispatching collection on the UI loop."""

    def __init__(self, loop, *, interval=.25):
        self._assert_main_thread()
        self.loop, self.interval = loop, interval
        self.was_enabled = gc.isenabled()
        self.closed = False
        self.pending = None
        gc.disable()
        try:
            self.pending = loop.call_later(interval, self.collect_due)
        except BaseException:
            if self.was_enabled:
                gc.enable()
            raise

    @staticmethod
    def _assert_main_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError('Native cycle collection must run on the UI thread.')

    def collect_due(self):
        self._assert_main_thread()
        if self.closed:
            return
        self.pending = None
        try:
            counts, thresholds = gc.get_count(), gc.get_threshold()
            if thresholds[0] and counts[0] > thresholds[0]:
                generation = (2 if counts[2] > thresholds[2] else
                              1 if counts[1] > thresholds[1] else 0)
                gc.collect(generation)
        finally:
            if not self.closed:
                self.pending = self.loop.call_later(self.interval, self.collect_due)

    def close(self):
        """Retire the timer and restore the process's previous GC setting."""
        self._assert_main_thread()
        if self.closed:
            return
        self.closed = True
        if self.pending is not None:
            self.pending.cancel()
            self.pending = None
        if self.was_enabled:
            gc.enable()


_owner = None


def bind_ios_timer_ownership():
    """Give Rubicon 0.5.7 timers an explicit registration and retirement path."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        pinned = version('rubicon-objc') == '0.5.7'
    except PackageNotFoundError:
        pinned = False
    if not pinned:
        return
    from rubicon.objc import eventloop
    if getattr(eventloop.CFTimerHandle, '_owns_native_timer', False):
        return
    cf = eventloop.libcf
    cf.CFRelease.restype = None
    cf.CFRunLoopTimerInvalidate.argtypes = [eventloop.CFRunLoopTimerRef]
    cf.CFRunLoopTimerInvalidate.restype = None
    pending = {}
    lock = threading.Lock()

    def retire(timer):
        # Stop native delivery while we still own the create reference.
        cf.CFRunLoopTimerInvalidate(timer)
        cf.CFRelease(timer)

    @eventloop.CFRunLoopTimerCallBack
    def dispatch(timer, _context):
        # One process-lived trampoline also covers delivery already in flight
        # when another thread cancels a timer.
        with lock:
            handle = pending.pop(timer.value, None)
            if handle is None:
                return
            handle._timer = None
            handle._loop._timers.discard(handle)
        retire(timer)
        handle._run()

    class TimerHandle(asyncio.TimerHandle):
        _owns_native_timer = True

        def __init__(self, *, loop, timeout, callback, args):
            super().__init__(cf.CFAbsoluteTimeGetCurrent() + timeout, callback, args, loop)
            timer = cf.CFRunLoopTimerCreate(None, self.when(), 0, 0, 0, dispatch, None)
            if not timer:
                raise RuntimeError('Unable to create the iOS event-loop timer.')
            self._timer = timer
            # Publish the handle before native registration can dispatch it.
            with lock:
                pending[timer.value] = self
                loop._timers.add(self)
                cf.CFRunLoopAddTimer(loop._cfrunloop, timer, eventloop.kCFRunLoopCommonModes)

        def cancel(self):
            with lock:
                timer = self._timer
                if timer is None:
                    return
                self._timer = None
                super().cancel()
                pending.pop(timer.value)
                self._loop._timers.discard(self)
            retire(timer)

    eventloop.CFTimerHandle = TimerHandle


def bind_ui_cycle_collection(loop):
    """Bind once for the iOS process; secondary window hosts share its loop."""
    global _owner
    if _owner is None or _owner.closed:
        _owner = UICycleCollection(loop)
        atexit.register(_owner.close)
    elif _owner.loop is not loop:
        raise RuntimeError('Native cycle collection already belongs to another UI loop.')
    return _owner
