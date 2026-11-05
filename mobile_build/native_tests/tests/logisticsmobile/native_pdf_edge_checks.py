"""Android PDF link acceptance inside the existing disposable native suite."""
import asyncio
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION


def linked_pdf():
    from pypdf import PdfWriter
    from pypdf.annotations import Link
    from pypdf.generic import DecodedStreamObject, NameObject
    writer = PdfWriter()
    for _ in range(3):
        page = writer.add_blank_page(1400, 600)
        stream = DecodedStreamObject()
        stream.set_data(b'.95 .97 1 rg 0 0 1400 600 re f .2 .4 .8 rg '
                        b'0 240 70 120 re f 560 240 280 120 re f 1330 240 70 120 re f')
        page[NameObject('/Contents')] = writer._add_object(stream)
    for rect in ((0, 240, 70, 360), (560, 240, 840, 360), (1330, 240, 1400, 360)):
        writer.add_annotation(0, Link(rect=rect, target_page_index=2))
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def cleanup_pdf_fixture(app, owner, canvas, path, original_session, proof, primary):
    """Try every owned cleanup step; an existing failure remains authoritative."""
    errors = []
    def attempt(label, action):
        try:
            action()
        except BaseException as error:
            errors.append(label + ': ' + repr(error))
    def retired():
        assert canvas.return_timer is None and canvas.on_tap is None
        assert canvas._impl.listener is None
        proof['callbacks_retired'] = True
    def close():
        assert app.close_session(owner.session.id), 'Synthetic PDF session did not close'
    def restored():
        assert app.editor_view.session.id == original_session
        proof['original_session_restored'] = True
    if owner is not None:
        attempt('clear PDF', owner.clear_private_reader)
        if canvas is not None:
            attempt('retire callbacks', retired)
        attempt('close synthetic session', close)
    attempt('remove fixture', lambda: path.unlink(missing_ok=True))
    attempt('restore original session', lambda: app.session_opener(original_session)())
    attempt('show original document', app.show_documents)
    attempt('verify original session', restored)
    proof['cleanup_errors'] = errors
    if errors:
        detail = 'PDF cleanup: ' + '; '.join(errors)
        if primary is not None:
            primary.add_note(detail)
        else:
            raise AssertionError(detail)


def navigation_pending(owner, canvas):
    swipe = getattr(owner, '_comic_swipe_task', None)
    if swipe is not None and not swipe.done():
        return True
    # follow_link schedules jump_link without retaining a task field. Inspect
    # only this reader's production navigation coroutines, never unrelated work.
    for task in asyncio.all_tasks():
        if task is asyncio.current_task() or task.done():
            continue
        coroutine = task.get_coro()
        frame = getattr(coroutine, 'cr_frame', None)
        code = getattr(coroutine, 'cr_code', None)
        actor = frame.f_locals.get('self') if frame is not None else None
        if (actor is owner or actor is canvas) and code is not None and code.co_name in {
            'jump_link', 'move_private_page', 'read_crypt_page',
            'turn', 'next_private_page', 'previous_private_page',
        }:
            return True
    return False

async def wait_pdf_idle(owner, canvas, viewport):
    loop = asyncio.get_running_loop()
    deadline, stable = loop.time()+15, None
    while True:
        ready = (not owner.cloud_busy and not navigation_pending(owner, canvas) and
                 owner.crypt_reader.pdf_navigation.viewport == viewport(owner))
        stable = (stable if stable is not None else loop.time()) if ready else None
        if stable is not None and loop.time()-stable >= .25:
            return
        assert loop.time() < deadline, 'PDF provider/navigation/layout did not settle'
        await asyncio.sleep(.05)


async def exercise_pdf_edge_links(app):
    from commonUtils.runtime.platform import get_os, OS
    if get_os() is not OS.ANDROID:
        return dict(applicable=False, reason='Android Java edge admission; no iOS acceptance claim')
    from features.pdf.mobile.canvas import pdf_viewport
    from .notebook_link_probe import Probe
    from .fixtures import capture_window
    owner = canvas = None
    path = app.private_root / 'native-edge-links.pdf'
    original_session = app.editor_view.session.id
    proof = dict(applicable=True, success=False, cases=[], overall_budget_seconds=60,
                 dispatch='native View MotionEvent; not physical OS input')
    app._native_pdf_edge_links = proof

    async def wait(predicate, message):
        deadline = asyncio.get_running_loop().time() + 15
        while not predicate():
            assert asyncio.get_running_loop().time() < deadline, message
            await asyncio.sleep(.05)

    async def idle():
        await wait_pdf_idle(owner, canvas, pdf_viewport)

    async def point(x):
        return await Probe.pdf_point(SimpleNamespace(apple=False), canvas, x, .5)

    async def gesture(native, location, **kwargs):
        await Probe.android_gesture(None, native, location, **kwargs)

    async def returned():
        await wait(lambda: owner.crypt_reader.pdf_navigation.indices[0] == 0, 'Native Undo did not return')
        await idle()

    primary = None
    try:
        async with asyncio.timeout(60):
            path.write_bytes(linked_pdf())
            assert await app.open_download(path=path)
            owner = app.private_sessions.active
            canvas = owner.crypt_image
            await idle()
            native = canvas._impl.native
            await wait(lambda: native.getWidth() > 0 and native.getHeight() > 0 and native.getDrawable() is not None,
                       'PDF native image absent')
            assert owner.crypt_reader.pdf_navigation.indices == (0,), 'PDF fixture must display one page'
            density = native.getResources().getDisplayMetrics().density
            assert canvas._impl.listener.imageTaps(), 'PDF tap admission is not enabled'
            def edge(location):
                assert location[0] < 24*density or location[0] > native.getWidth()-24*density, location
            for x in (.5, .02, .98):
                canvas.fit_page()
                assert abs(canvas.zoom_scale-1) < .05
                location = await point(x)
                if x != .5:
                    edge(location)
                await gesture(native, location)
                await wait(lambda: canvas.return_page is not None, 'Native finger link did not navigate')
                assert owner.crypt_reader.pdf_navigation.indices[0] == 2
                await idle()
                if x != .5:
                    await capture_window(app, Path(app.paths.cache) / ('pdf-edge-left.png' if x < .5 else 'pdf-edge-right.png'))
                def undo_ready():
                    if not canvas.return_box.children:
                        return False
                    button = canvas.return_box.children[0]._impl.native
                    return (button.isAttachedToWindow() and button.isShown() and button.isEnabled()
                            and button.getWidth() > 0 and button.getHeight() > 0)
                await wait(undo_ready, 'Native Undo not mounted, laid out and enabled')
                button = canvas.return_box.children[0]._impl.native
                await gesture(button, [button.getWidth()/2, button.getHeight()/2])
                await returned()
                proof['cases'].append('finger_link_and_native_undo_'+str(x))
                if x != .5:
                    location = await point(x)
                    for label, kwargs in (
                        ('cancel', dict(cancel=True)), ('pen', dict(tool=2)),
                        ('swipe', dict(end=[location[0], location[1]-native.getHeight()*.2])),
                        ('move_back', dict(end=[location[0]+(60 if x<.5 else -60), location[1]], moved_back=True)),
                    ):
                        edge(location)  # Only the proven outer-24dp edge policy forbids paging.
                        await gesture(native, location, **kwargs)
                        await idle()  # Drain queued provider/layout work before claiming rejection.
                        assert owner.crypt_reader.pdf_navigation.indices[0] == 0 and canvas.return_page is None, label
                        proof['cases'].append('edge_no_link_'+str(x)+'_'+label)
            canvas.set_zoom(2)
            assert abs(canvas.zoom_scale-2) < .05
            await gesture(native, await point(.5))
            await wait(lambda: canvas.return_page is not None, 'Zoomed center link did not navigate')
            assert owner.crypt_reader.pdf_navigation.indices[0] == 2
            await asyncio.sleep(3.2)
            assert canvas.return_page is None and not canvas.return_box.children
            proof['cases'].append('zoom_2_center_link_real_3s_expiry')
    except BaseException as error:
        primary = error
        proof['error'] = repr(error)
        raise
    finally:
        cleanup_pdf_fixture(app, owner, canvas, path, original_session, proof, primary)
    proof['success'] = True
    return proof
