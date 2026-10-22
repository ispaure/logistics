"""Bounded checks for content rendered by the actual native WebView."""
import asyncio


async def wait_for_text(view, expected, *, absent=None, timeout=30):
    last = None
    async def loaded():
        nonlocal last
        while True:
            try:
                value = await view.evaluate_javascript('String(document.body ? document.body.textContent || "" : "")')
            except RuntimeError as error:
                # WKWebView can reject evaluation while replacing a document.
                # An error never counts as cleared/rendered content; retry until
                # the replacement actually returns the required text.
                if 'WKErrorDomain Code=5' not in str(error):
                    raise
                last = str(error)
                await asyncio.sleep(.1)
                continue
            if not isinstance(value, str):
                raise RuntimeError('WebView body text did not return a string.')
            last = value
            if expected in str(value) and (absent is None or absent not in str(value)):
                return
            await asyncio.sleep(.1)
    # Toga Android can re-enter its cooperative loop from native callbacks;
    # asyncio's current-task timeout context is not reliable at that boundary.
    # wait() uses a loop timer without requiring a current-task context.
    task = asyncio.create_task(loaded())
    done, _ = await asyncio.wait([task], timeout=timeout)
    if not done:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise RuntimeError(f'WebView did not render {expected!r}; last value={last!r}, url={view.url!r}') from None
    await task
