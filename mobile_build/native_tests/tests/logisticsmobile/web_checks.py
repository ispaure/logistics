"""Bounded checks for content rendered by the actual native WebView."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
import json
import os
import sys
import time

TRANSFER_DIAGNOSTIC_DELAY = 15


def signal_transfer_stall(surface):
    """Keep host diagnostics when bounded app recovery rescues the screen."""
    if sys.platform == 'ios' and not getattr(surface, '_native_stall_capture_sent', False):
        surface._native_stall_capture_sent = True
        print('LOGISTICS_NATIVE_WEBVIEW_STALL=' + json.dumps(dict(
            pid=os.getpid(), expected='Transfer details', sent_ns=time.time_ns())), flush=True)


async def transfer_evaluate(view, script, *, timeout=1):
    """A retired renderer cannot hold the recovery-aware native driver open."""
    task = asyncio.ensure_future(view.evaluate_javascript(script))
    try:
        done, _ = await asyncio.wait((task,), timeout=timeout)
        return (True, task.result()) if done else (False, None)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def verify_native_transfer_fallback(surface):
    """Require attached native widgets containing the acknowledged model."""
    from commonUtils.ui.native.keyboard import native_value
    fallback = surface.native_fallback
    assert not surface.closed and fallback is not None and fallback.parent is surface
    assert surface.ready and surface.pending is None and surface.revision > 0
    assert surface.delivered_revision == surface.revision, 'Native transfer model was not acknowledged'
    assert fallback.surface is surface, 'Retired native transfer controls'
    impl = fallback._impl
    platform = next((base.__module__ for base in type(impl).__mro__
        if base.__module__.startswith(('toga_iOS.', 'toga_android.'))), '')
    native = impl.native
    if platform.startswith('toga_iOS.'):
        assert native_value(native.window) is not None, 'Native transfer view is detached'
        bounds = native_value(native.bounds)
        assert bounds.size.width > 0 and bounds.size.height > 0, 'Native transfer view has no layout'
        node = native
        for _ in range(12):
            if node is None:
                break
            assert not node.isHidden() and float(native_value(node.alpha)) > 0, 'Native transfer view is hidden'
            node = native_value(node.superview)
        def text(widget):
            value = str(native_value(widget._impl.native.text) or '')
            # Toga iOS 0.5.7 encodes an empty UILabel as exactly U+200B to
            # preserve intrinsic size; its own get_text decodes this sentinel.
            return '' if value == '\u200b' else value
    elif platform.startswith('toga_android.'):
        assert native.isAttachedToWindow(), 'Native transfer view is detached'
        assert int(native.getVisibility()) == 0 and native.isShown(), 'Native transfer view is hidden'
        assert native.getWidth() > 0 and native.getHeight() > 0, 'Native transfer view has no layout'
        def text(widget):
            value = widget._impl.native.getText()
            # Chaquopy converts TextView String values to Python str; other
            # CharSequence implementations retain their Java proxy.
            return value if isinstance(value, str) else str(value.toString())
    else:
        raise AssertionError('Transfer fallback requires actual iOS or Android widgets')
    model = surface.model
    assert text(fallback.title) == (model.get('workspace') or 'Transfers'), 'Native transfer title is stale'
    assert text(fallback.paths) == ('Source: ' + model.get('source', '—')
        + '\nDestination: ' + model.get('destination', '—')), 'Native transfer endpoints are stale'
    metrics = text(fallback.metrics)
    buttons = {button.text: button for button in fallback.buttons.children}
    if model.get('mode') == 'progress':
        assert text(fallback.status) == (model.get('phase', 'idle').capitalize() + '\n'
            + (model.get('message') or model.get('status', ''))), 'Native transfer status is stale'
        assert f"Files: {model.get('files', 0):,} / {model.get('total_files', 0):,}" in metrics, 'Native transfer file counts are stale'
        assert (f"Data: {model.get('done', 0) / 1_000_000:,.2f} / "
            + f"{model.get('total', 0) / 1_000_000:,.2f} MB") in metrics, 'Native transfer byte counts are stale'
        assert f"Checked: {model.get('checks', 0):,} · Listed: {model.get('listed', 0):,}" in metrics
        if model.get('percentage') is not None:
            assert f"{model['percentage']:.0f}%" in metrics
        assert 'Continue browsing' in buttons and buttons['Continue browsing'].enabled
        if model.get('busy'):
            assert 'Stop transfer' in buttons
            assert buttons['Stop transfer'].enabled == (model.get('phase') != 'stopping')
    elif model.get('mode') == 'review':
        assert text(fallback.status) == model.get('notice', ''), 'Native review notice is stale'
        for kind in ('add', 'replace', 'delete', 'cleanup'):
            assert f"{kind.capitalize()}: {model.get('counts', {}).get(kind, 0):,}" in metrics
        assert 'no undo' in metrics
        assert [text(child) for child in fallback.rows.children] == [
            f'{kind.capitalize()}: {path}' for kind, path in model.get('rows', ())], 'Native review rows are stale'
        approve = buttons.get('Approve ' + model.get('operation', 'transfer'))
        assert approve is not None and approve.enabled == bool(model.get('can_confirm'))
        assert 'Cancel review' in buttons and buttons['Cancel review'].enabled
        page, size, total = model.get('page', 0), model.get('page_size', 30), model.get('total', 0)
        assert f'Page {page + 1} · {total:,} matching changes' in metrics
        assert buttons['Previous changes'].enabled == (page > 0)
        assert buttons['Next changes'].enabled == ((page + 1) * size < total)
    else:
        raise AssertionError('Unexpected transfer mode for native acceptance')
    return dict(renderer='native', mode=model['mode'], revision=surface.revision,
                recoveries=surface.recovery_count)


async def wait_for_transfer_surface(surface, *, timeout=45):
    """Follow one rebuilt view or verify the supported native progress UI."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    deadline = started + timeout
    signalled = False
    last = None
    while loop.time() < deadline:
        assert not surface.closed, 'Transfer surface closed before rendering'
        assert surface.model.get('mode') == 'progress', 'Unexpected transfer surface mode'
        if surface.recovery_count:
            signal_transfer_stall(surface)
        if getattr(surface, 'native_fallback', None) is not None:
            try:
                proof = verify_native_transfer_fallback(surface)
            except AssertionError as error:
                last = str(error)
            else:
                print('LOGISTICS_NATIVE_TRANSFER_SURFACE=' + json.dumps(proof), flush=True)
                return proof
        else:
            web = surface.web
            if web is not None and surface.ready:
                try:
                    answered, value = await transfer_evaluate(web,
                        'String(document.body ? document.body.textContent || "" : "")',
                        timeout=min(1, max(.001, deadline - loop.time())))
                except RuntimeError as error:
                    last = str(error)
                else:
                    if web is surface.web and answered:
                        if not isinstance(value, str):
                            raise RuntimeError('Transfer body text did not return a string.')
                        last = value[:300]
                        if ('Transfer details' in value and 'Choose a remote to pull' not in value
                                and surface.pending is None and surface.delivered_revision == surface.revision):
                            proof = dict(renderer='web', mode=surface.model['mode'],
                                revision=surface.revision, recoveries=surface.recovery_count)
                            print('LOGISTICS_NATIVE_TRANSFER_SURFACE=' + json.dumps(proof), flush=True)
                            return proof
        if not signalled and loop.time() - started >= TRANSFER_DIAGNOSTIC_DELAY:
            signalled = True
            signal_transfer_stall(surface)
        await asyncio.sleep(.1)
    raise RuntimeError(f'Transfer surface did not render after bounded recovery; last={last!r}')


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
