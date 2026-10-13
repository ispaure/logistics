"""Bind cooperative native dispatch to its owned asyncio loop."""
import asyncio
from asyncio import events


def bind_cooperative_loop(loop):
    """Repair Toga 0.5.7 Android's callback-local running-loop context.

    Java callbacks may enter Python with a different thread state than the one
    used by run_forever_cooperatively. Toga sets the running loop at startup but
    does not restore it around run_delayed_tasks. Own that context for each
    dispatch, while restoring the caller's context when the callback returns.
    """
    if getattr(loop, '_logistics_bound', False):
        return
    original = getattr(loop, 'run_delayed_tasks', None)
    if original is None:
        return
    asyncio.set_event_loop(loop)
    def dispatch():
        previous = events._get_running_loop()
        events._set_running_loop(loop)
        try:
            return original()
        finally:
            events._set_running_loop(previous)
    loop.run_delayed_tasks = dispatch
    loop._logistics_bound = True
