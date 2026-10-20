"""Coalesced reader layout wakeups; no timer and no retained reader owners."""
import asyncio
from weakref import WeakSet


def layout_waiter(app):
    event = asyncio.Event()
    event.set()  # Apply initial post-mount geometry.
    listeners = getattr(app, '_reader_layout_events', None)
    if listeners is None:
        app._reader_layout_events = listeners = WeakSet()
    listeners.add(event)

    async def changed():
        await event.wait()
        event.clear()
    return changed


def notify_layout(app):
    for event in tuple(getattr(app, '_reader_layout_events', ())):
        event.set()
