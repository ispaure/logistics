"""Bounded checks for content rendered by the actual native WebView."""
import asyncio


async def wait_for_text(view, expected, *, absent=None):
    last = None
    async def loaded():
        nonlocal last
        while True:
            value = await view.evaluate_javascript('document.body ? document.body.textContent : ""')
            last = str(value)
            if expected in str(value) and (absent is None or absent not in str(value)):
                return
            await asyncio.sleep(.1)
    # Toga Android can re-enter its cooperative loop from native callbacks;
    # asyncio's current-task timeout context is not reliable at that boundary.
    # wait() uses a loop timer without requiring a current-task context.
    task = asyncio.create_task(loaded())
    done, _ = await asyncio.wait([task], timeout=30)
    if not done:
        task.cancel()
        raise RuntimeError(f'WebView did not render {expected!r}; last value={last!r}, url={view.url!r}') from None
    await task
