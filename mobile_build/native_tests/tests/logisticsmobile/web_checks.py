"""Bounded checks for content rendered by the actual native WebView."""
import asyncio
import json


def native_state(view):
    """Capture attachment/loading evidence only after a real render failure."""
    state = {}
    try:
        impl = getattr(view, '_impl', None)
        state.update(backend=type(impl).__module__, parent=getattr(view, 'parent', None) is not None,
                     navigation=getattr(view, '_native_policy_trace', []))
        if impl is None:
            return state
        native = impl.native
        if state['backend'].startswith('toga_iOS.'):
            from commonUtils.ui.native.keyboard import native_value
            state['loading'] = bool(native.isLoading())
            state['window'] = native_value(native.window) is not None
            chain = []
            node = native
            while node is not None and len(chain) < 12:
                bounds = native_value(node.bounds)
                chain.append(dict(hidden=bool(node.isHidden()), alpha=float(native_value(node.alpha)),
                    width=float(bounds.size.width), height=float(bounds.size.height)))
                node = native_value(node.superview)
            state['ancestors'] = chain
        elif state['backend'].startswith('toga_android.'):
            state.update(attached=bool(native.isAttachedToWindow()), visibility=int(native.getVisibility()),
                         width=int(native.getWidth()), height=int(native.getHeight()))
    except Exception as error:
        state['diagnostic_error'] = str(error)
    return state


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
        state = native_state(view)
        print('LOGISTICS_NATIVE_WEBVIEW_STATE=' + json.dumps(state), flush=True)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise RuntimeError(f'WebView did not render {expected!r}; last value={last!r}, url={view.url!r}, native={state!r}') from None
    await task
