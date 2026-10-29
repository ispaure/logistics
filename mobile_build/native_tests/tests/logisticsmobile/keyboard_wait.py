"""Bound native keyboard acknowledgement across rotation animation restarts."""
import asyncio


async def settled_keyboard(request, visible, *, ready=lambda: True, attempts=20):
    consecutive = 0
    for _ in range(attempts):
        if not consecutive:
            request()
        await asyncio.sleep(.25)
        if ready() and visible():
            consecutive += 1
            if consecutive == 3:
                return True
        else:
            consecutive = 0
    return False
