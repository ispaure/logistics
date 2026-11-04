"""Bounded checks for content rendered by the actual native WebView."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
import os
import sys
import time


def native_state(view):
    """Capture attachment/loading evidence only after a real render failure."""
    state = {}
    try:
        impl = getattr(view, '_impl', None)
        from .navigation_trace import lifecycle_snapshot
        counts = lifecycle_snapshot()
        if counts is not None:
            state.update(view_index=getattr(view, '_native_view_index', None), lifecycle=counts)
        state.update(backend=type(impl).__module__, parent=getattr(view, 'parent', None) is not None,
                     navigation=getattr(view, '_native_policy_trace', []))
        if impl is None:
            return state
        native = impl.native
        platform = next((base.__module__ for base in type(impl).__mro__
                         if base.__module__.startswith(('toga_iOS.', 'toga_android.'))), '')
        state['platform_backend'] = platform
        if platform.startswith('toga_iOS.'):
            from commonUtils.ui.native.keyboard import native_value
            from rubicon.objc import SEL
            state['load_events'] = getattr(view, '_native_load_trace', [])
            state['allowed_url'] = getattr(impl, '_allowed_url', None)
            state['progress'] = float(native_value(native.estimatedProgress))
            # Optional WebKit SPI is diagnostic-only, never a runtime dependency.
            # It distinguishes a missing provisional process from a live stall.
            for selector, key, convert in (
                    ('_webProcessIdentifier', 'web_process_pid', int),
                    ('_provisionalWebProcessIdentifier', 'provisional_process_pid', int),
                    ('_webProcessIsResponsive', 'web_process_responsive', bool)):
                if native.respondsToSelector(SEL(selector)):
                    state[key] = convert(native_value(getattr(native, selector)))
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
        elif platform.startswith('toga_android.'):
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
    first_wait = min(timeout, 15)
    done, _ = await asyncio.wait([task], timeout=first_wait)
    if not done and timeout > first_wait:
        state = native_state(view)
        if state.get('platform_backend', '').startswith('toga_iOS.'):
            # Capture the still-running process before the final failure exits
            # the app. This does not extend the existing render deadline.
            # Briefcase truncates individual app log lines around 1 KiB. Keep
            # this host-control signal small; full state is reported on failure.
            print('LOGISTICS_NATIVE_WEBVIEW_STALL=' + json.dumps(dict(
                pid=os.getpid(), expected=expected[:40], sent_ns=time.time_ns())), flush=True)
        done, _ = await asyncio.wait([task], timeout=timeout - first_wait)
    if not done:
        state = native_state(view)
        print('LOGISTICS_NATIVE_WEBVIEW_STATE=' + json.dumps(state), flush=True)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if sys.platform == 'ios' and state.get('platform_backend', '').startswith('toga_iOS.'):
            # Acceptance has already failed; do not await or accept a late
            # render. Keep the process and native view available while the
            # hosted sampler enumerates symbols and captures thread stacks.
            # Exiting during that work can leave only a binary-image inventory.
            await asyncio.sleep(60)
        raise RuntimeError(f'WebView did not render {expected!r}; last value={last!r}, url={view.url!r}, native={state!r}') from None
    await task
