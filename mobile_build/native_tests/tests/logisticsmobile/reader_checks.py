"""Actual native image zoom, compact reading and sanitized appearance content."""
import asyncio
import base64
import json
from pathlib import Path
from commonUtils.runtime.resources.documents import LocalDocuments
from commonUtils.runtime.platform import get_os, OS
from .web_checks import wait_for_text


def _assert_comic_centered(view, *, fullscreen=False):
    """Measure the rendered page in the actual native viewport."""
    native = view._impl.native
    if hasattr(view._impl, 'picture'):
        assert view._impl.container is not None, 'Comic canvas is not attached to a native viewport'
        picture = view._impl.picture
        frame = picture.convertRect(picture.bounds, toView=native)
        bounds = native.bounds
        dx = frame.origin.x + frame.size.width / 2 - (bounds.origin.x + bounds.size.width / 2)
        dy = frame.origin.y + frame.size.height / 2 - (bounds.origin.y + bounds.size.height / 2)
    else:
        from java import jclass
        image = native.getDrawable()
        rect = jclass('android.graphics.RectF')(0, 0, image.getIntrinsicWidth(), image.getIntrinsicHeight())
        native.getImageMatrix().mapRect(rect)
        dx, dy = rect.centerX() - native.getWidth() / 2, rect.centerY() - native.getHeight() / 2
    assert abs(dx) < 2 and abs(dy) < 2, ('Comic is off center', dx, dy)
    if fullscreen:
        if hasattr(view._impl, 'picture'):
            window = native.window
            if callable(window):
                window = window()
            rect = picture.convertRect(picture.bounds, toView=window)
            # Comic fullscreen deliberately zeros the host's content insets in
            # ios_reader_chrome. Measure its full native column on iPad and
            # screen on iPhone; UIKit's retained safeAreaInsets must not be
            # subtracted again. The reentry checks also reject host shrinkage.
            host = view._impl.container.native
            host_rect = host.convertRect(host.bounds, toView=window)
            dy = rect.origin.y + rect.size.height / 2 - (
                host_rect.origin.y + host_rect.size.height / 2)
        else:
            from java import jarray, jint
            location = jarray(jint)(2)
            native.getLocationOnScreen(location)
            decor = view._impl._native_activity.getWindow().getDecorView()
            decor_location = jarray(jint)(2)
            decor.getLocationOnScreen(decor_location)
            insets = decor.getRootWindowInsets()
            Types = jclass('android.view.WindowInsets$Type')
            system_bars = insets.getInsets(Types.systemBars())
            # Hidden system bars do not remove the camera's safe cutout. Query
            # the union so viewport and centering use the actual safe screen.
            bars = insets.getInsets(Types.systemBars() | Types.displayCutout())
            cutout = insets.getInsets(Types.displayCutout())
            inset_proof = dict(bars=[int(system_bars.left),int(system_bars.top),int(system_bars.right),int(system_bars.bottom)],
                               cutout=[int(cutout.left),int(cutout.top),int(cutout.right),int(cutout.bottom)],
                               location=list(location), decor_location=list(decor_location))
            assert abs(native.getWidth() - (decor.getWidth() - bars.left - bars.right)) <= 2, ('Comic viewport loses screen width', native.getWidth(), decor.getWidth(), inset_proof)
            assert abs(native.getHeight() - (decor.getHeight() - bars.top - bars.bottom)) <= 2, ('Comic viewport loses screen height', native.getHeight(), decor.getHeight(), inset_proof)
            # Both positions are in screen coordinates. A pre-edge-to-edge
            # decor can start below the display origin even with hidden bars.
            dx = location[0] + rect.centerX() - (decor_location[0] +
                (bars.left + decor.getWidth() - bars.right) / 2)
            dy = location[1] + rect.centerY() - (decor_location[1] +
                (bars.top + decor.getHeight() - bars.bottom) / 2)
            assert abs(dx) < 2, ('Comic misses horizontal screen centre', dx, inset_proof)
        assert abs(dy) < 2, ('Comic misses screen centre', dy,
            float(native.bounds.size.height) if hasattr(view._impl, 'picture') else
            (list(location), native.getHeight(), decor.getHeight(), bars.top, bars.bottom, list(decor_location)))


async def assert_comic_centered(view, *, fullscreen=False):
    """Wait for native chrome/layout to settle, retaining exact geometry checks."""
    deadline = asyncio.get_running_loop().time() + 15
    centered = 0
    while True:
        await asyncio.sleep(.1)
        try:
            current = view() if callable(view) else view
            _assert_comic_centered(current, fullscreen=fullscreen)
        except AssertionError:
            centered = 0
            if asyncio.get_running_loop().time() >= deadline:
                raise
        else:
            centered += 1
            if centered >= 3:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError('Comic geometry did not settle before the deadline')


async def wait_for_reader(owner, *, position=None):
    """Wait for real reader operations, including queued position saves."""
    # Hosted emulators can take longer than 15 seconds to decode/reload a
    # page after chrome changes. Require the same settled state within a
    # bounded minute rather than racing the background reader operation.
    deadline = asyncio.get_running_loop().time() + 60
    settled = 0
    while True:
        pending = getattr(owner, '_epub_location_task', None)
        ready = (not owner.book_busy and (pending is None or pending.done())
                 and (position is None or owner.book_record['position'] == position))
        settled = settled + 1 if ready else 0
        if settled >= 3:
            return
        assert asyncio.get_running_loop().time() < deadline, 'Reader operation did not settle'
        await asyncio.sleep(.05)


async def exercise_reader(app, passed):
    owner = app.reader_manager().active
    def current_view():
        displayed = owner.book_content.children[0]
        return displayed.canvases[0] if hasattr(displayed, 'canvases') else displayed
    async def toggle_controls():
        await wait_for_reader(owner)
        previous = owner.reader_immersive
        current_view().toggle_controls()
        assert owner.reader_immersive is not previous, 'Reader controls did not toggle'
    current_view().set_zoom(2)
    await asyncio.sleep(.2)
    assert 1.9 <= current_view().zoom_scale <= 2.1, current_view().zoom_scale
    current_view().fit_page()
    assert current_view().zoom_scale == 1
    assert owner.reader_immersive and owner.library_view._comic_fullscreen
    assert owner.reader_header not in owner.library_view.children
    await toggle_controls()
    assert not owner.reader_immersive
    # Native document controls now live in the platform title bar rather than
    # an extra Toga header row. Verify that actual bar after leaving fullscreen.
    if get_os() is OS.IOS:
        controller = app._reader_toolbar_controller
        from .fixtures import ios_toolbar_items
        assert ios_toolbar_items(controller) or controller.navigationItem.additionalOverflowItems is not None
        assert owner.reader_header not in owner.library_view.children
    else:
        bar = app._impl.native.getSupportActionBar()
        deadline = asyncio.get_running_loop().time() + 10
        while not bar.isShowing() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(.05)
        assert bar.isShowing(), ('Reader title bar did not restore',
            app.native_host.state.destination, app.native_host.adapter.keyboard_chrome)
        assert app.native_host.adapter._reader_action_bar_buttons
    await toggle_controls()
    assert owner.reader_immersive
    await assert_comic_centered(current_view, fullscreen=True)
    def viewport_height():
        return float(current_view()._impl.native.bounds.size.height) if hasattr(current_view()._impl, 'picture') else current_view()._impl.native.getHeight()
    full_height = viewport_height()
    # Reuse the existing reader, leave through another destination, and repeat
    # control/fullscreen transitions. This catches retained native scroll offsets.
    for _ in range(3):
        app.show_settings()
        await asyncio.sleep(.1)
        owner.show_library()
        await toggle_controls()
        await asyncio.sleep(.1)
        await toggle_controls()
        await assert_comic_centered(current_view, fullscreen=True)
        assert abs(viewport_height() - full_height) < 1, ('Fullscreen viewport shrank', full_height, viewport_height())
    await wait_for_reader(owner)
    previous = app.reader_manager().active.book_record['position']
    # Exercise native gesture target dispatch, rather than only the controller.
    if hasattr(current_view()._impl, 'swipes'):
        swipe = current_view()._impl.swipes[0]  # UIKit right swipe -> previous.
        assert current_view()._impl.native.gestureRecognizerShouldBegin(swipe)
        current_view()._impl.native.pageSwipe(swipe)
    else:
        from java import jclass
        Event = jclass('android.view.MotionEvent')
        native = current_view()._impl.native
        now = jclass('android.os.SystemClock').uptimeMillis()
        x, y = native.getWidth()*.35, native.getHeight()*.5
        down = Event.obtain(now, now, Event.ACTION_DOWN, x, y, 0)
        up = Event.obtain(now, now+200, Event.ACTION_UP, native.getWidth()*.8, y, 0)
        native.onTouchEvent(down)
        native.onTouchEvent(up)
        down.recycle()
        up.recycle()
    await wait_for_reader(owner, position=previous - 1)
    assert app.reader_manager().active.book_record['position'] == previous - 1
    app.reader_manager().active.book_content.children[0].page(1)
    await wait_for_reader(owner, position=previous)
    assert app.reader_manager().active.book_record['position'] == previous
    owner.show_reader_appearance()
    owner.reader_layout.value = 'single'
    await owner.apply_reader_appearance()
    assert app.preferences.values['comic_layout'] == 'single'
    assert app.reader_manager().active.book_record['position'] == previous
    owner.show_reader_tools()
    assert owner.bookmark_selector not in owner.reader_tools_view.content.children
    assert owner.chapter_selector in owner.reader_tools_view.content.children
    owner.show_library()
    await assert_comic_centered(current_view, fullscreen=True)
    passed.append('native_comic_fullscreen_reentry')
    passed.append('native_reader_presentation')


def exercise_sampled_apple_decode(app):
    backend = type(app._impl).__module__
    if not backend.startswith('toga_iOS.'):
        return
    from .reader_parity_probe import image_bytes
    from features.comics.mobile.decoding import decode_page
    data = image_bytes(b'\xff\x00\x00\xff', width=1024, height=1536)
    image = decode_page(data, (1024, 1536), (64, 96), backend)
    assert (image.width, image.height) == (64, 96), (image.width, image.height)


def _ios_webview_state(native):
    from commonUtils.ui.native.keyboard import native_value
    from rubicon.objc import ObjCClass
    window = native_value(native.window)
    application = ObjCClass('UIApplication').sharedApplication
    return dict(url=str(native.URL), loading=bool(native_value(native.isLoading)),
        progress=float(native_value(native.estimatedProgress)),
        width=float(native.bounds.size.width), height=float(native.bounds.size.height),
        attached=window is not None, hidden=bool(native_value(native.isHidden)),
        key_window=None if window is None else bool(native_value(window.isKeyWindow)),
        application_state=int(native_value(application.applicationState)))


def _log_ios_webview(phase, native, error=None):
    # Diagnostics cannot replace or change the toolkit's navigation decision.
    try:
        state = _ios_webview_state(native)
        state.update(phase=phase, error=None if error is None else str(error))
        print('LOGISTICS_EPUB_NATIVE=' + json.dumps(state), flush=True)
    except Exception as failure:
        print('LOGISTICS_EPUB_NATIVE_DIAGNOSTIC_ERROR=' + str(failure), flush=True)


async def exercise_library(app, fixtures, epub, comic, passed):
    """Retain actual native load events; preserve the original failure deadline."""
    from contextlib import ExitStack
    from features.books.mobile.presentation import ChapterBridge
    from unittest.mock import patch
    original = ChapterBridge.navigation
    initialize = ChapterBridge.__init__
    bridges = []
    def created(bridge, *args, **kwargs):
        initialize(bridge, *args, **kwargs)
        bridges.append(bridge)
    def navigation(bridge, widget, url, **kwargs):
        decision = original(bridge, widget, url, **kwargs)
        print('LOGISTICS_EPUB_NAVIGATION=' + json.dumps(dict(
            url=url, root=bridge.root, closed=bridge.closed,
            ready=bridge.ready, decision=decision,
            allowed_url=getattr(bridge.view._impl, '_allowed_url', None))), flush=True)
        return decision
    with ExitStack() as stack:
        stack.enter_context(patch.object(ChapterBridge, 'navigation', navigation))
        stack.enter_context(patch.object(ChapterBridge, '__init__', created))
        if get_os() is OS.IOS:
            from rubicon.objc import objc_method, py_from_ns
            from toga_iOS.widgets import webview
            original_native = webview.TogaWebView
            class LogisticsDiagnosticWebView(original_native):
                @objc_method
                def webView_didStartProvisionalNavigation_(self, webview, navigation) -> None:
                    _log_ios_webview('start', self)
                @objc_method
                def webView_didCommitNavigation_(self, webview, navigation) -> None:
                    _log_ios_webview('commit', self)
                @objc_method
                def webView_didFailProvisionalNavigation_withError_(self, webview, navigation, error) -> None:
                    _log_ios_webview('provisional-error', self, py_from_ns(error))
                @objc_method
                def webView_didFailNavigation_withError_(self, webview, navigation, error) -> None:
                    _log_ios_webview('load-error', self, py_from_ns(error))
                @objc_method
                def webViewWebContentProcessDidTerminate_(self, webview) -> None:
                    _log_ios_webview('web-process-terminated', self)
            stack.enter_context(patch.object(webview, 'TogaWebView', LogisticsDiagnosticWebView))
        try:
            return await _exercise_library(app, fixtures, epub, comic, passed)
        except Exception:
            if get_os() is OS.IOS and bridges:
                bridge = bridges[-1]
                _log_ios_webview('original-failure', bridge.view._impl.native)
                # This probe never counts as passing acceptance. Always re-raise
                # the original failure, even if the document arrives later.
                await asyncio.sleep(60)
                _log_ios_webview('late-probe', bridge.view._impl.native)
                try:
                    value = await asyncio.wait_for(bridge.view.evaluate_javascript(
                        'String(document.body ? document.body.textContent || "" : "")'), 5)
                    print('LOGISTICS_EPUB_LATE_BODY=' + json.dumps(value[:200]), flush=True)
                except Exception as failure:
                    print('LOGISTICS_EPUB_LATE_ERROR=' + str(failure), flush=True)
            raise


async def _exercise_library(app, fixtures, epub, comic, passed):
    from .navigation_checks import wait_for_transitions
    await wait_for_transitions(app)
    exercise_sampled_apple_decode(app)
    app.show_library()
    await wait_for_transitions(app)
    record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), epub)
    app.refresh_library()
    await app.open_book(record['id'])
    assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
    await wait_for_transitions(app)
    await wait_for_text(app.reader_manager().active.book_content.children[0], 'Native EPUB first')
    original_reader = app.reader_manager().active.book_content.children[0]
    deadline = asyncio.get_running_loop().time() + 15
    pagination = None
    while True:
        raw = await original_reader.evaluate_javascript(
            'JSON.stringify(window.reader ? window.reader.pagination() : null)')
        pagination = json.loads(raw) if raw else None
        bridge = original_reader._chapter_bridge
        # The initial position acknowledgement proves the native navigation
        # channel is live and the tiny first chapter fits its settled viewport.
        # A JavaScript object can exist before its first animation-frame event.
        if (pagination and bridge.at_end
                and pagination['count'] <= pagination['columns']):
            break
        assert asyncio.get_running_loop().time() < deadline, (
            'EPUB navigation did not acknowledge initial pagination', pagination,
            bridge.ready, bridge.at_end)
        await asyncio.sleep(.05)
    print('LOGISTICS_EPUB_READY=' + json.dumps(pagination), flush=True)
    owner = app.reader_manager().active
    events = []
    original_event = owner.epub_event
    def event_state(reader, epoch, index, action):
        pending = getattr(owner, '_epub_location_task', None)
        return dict(action=action, received_index=index,
            reader_current=owner.book_reader is reader, epoch_current=owner.book_epoch == epoch,
            active_host=bool(owner.active_host), session_open=owner.session.id in owner.workspace.sessions,
            busy=owner.book_busy, position=owner.book_record['position'],
            pending_done=None if pending is None else pending.done(),
            status=owner.book_status.text,
            displayed_is_original=owner.book_content.children[0] is original_reader,
            retained_is_original=owner.epub_view is original_reader,
            bridge_root=owner.epub_view._chapter_bridge.root,
            bridge_ready=owner.epub_view._chapter_bridge.ready,
            allowed_url=getattr(owner.epub_view._impl, '_allowed_url', None),
            native_url=owner.epub_view.url)
    def trace(reader, epoch, index, action, offset):
        state = event_state(reader, epoch, index, action)
        events.append(state)
        if action in {'next', 'previous'}:
            print('LOGISTICS_EPUB_EVENT=' + json.dumps(state), flush=True)
        return original_event(reader, epoch, index, action, offset)
    from unittest.mock import patch
    with patch.object(owner, 'epub_event', side_effect=trace):
        await wait_for_reader(owner)
        print('LOGISTICS_EPUB_BEFORE_NEXT=' + json.dumps(event_state(
            owner.book_reader, owner.book_epoch, 0, 'request-next')), flush=True)
        await app.next_book_page()
        assert app.reader_manager().active.book_content.children[0] is original_reader
        try:
            await wait_for_text(original_reader, 'Native EPUB second')
        except BaseException:
            state = event_state(owner.book_reader, owner.book_epoch, 0, 'failed-next')
            state['events'] = events[-20:]
            print('LOGISTICS_EPUB_FAILURE=' + json.dumps(state), flush=True)
            raise
    # Silent synthesis still exercises the actual WebView text source, trusted
    # bridge, chapter publication, highlight delivery and current chapter row.
    class SilentSpeech:
        ready, error, default_voice = True, '', 'Offline'
        voices = {'Offline': None}
        def __init__(self, loop):
            self.calls = []
        def voice_for_language(self, language, preferred=''):
            return 'Offline'
        def speak(self, text, voice, speed, token):
            self.calls.append(text)
            self.started(token)
        def stop(self):
            pass
        def close(self):
            pass
    owner._epub_target = 0
    await owner.move_book_page(0)
    await wait_for_text(original_reader, 'Native EPUB first')
    await wait_for_reader(owner)
    with patch('features.books.mobile.speech_view.NativeSpeech', SilentSpeech):
        owner.show_read_aloud()
        speech = owner.speech_panel
        try:
            await speech.ready_task
            await speech.play()
            for _ in range(20):
                if speech.session.state == 'speaking':
                    speech.session.completed(speech.session.token)
                task = speech.continuation_task
                if task is not None:
                    await asyncio.wait_for(asyncio.shield(task), 20)
                if speech.session.state == 'stopped':
                    break
            assert owner.book_record['position'] == owner.chapter_tree.current == 1
            assert owner.speech_panel is speech and not speech.closed
            assert len(speech.engine.calls) == 2, speech.engine.calls
            assert 'first' in speech.engine.calls[0] and 'second' in speech.engine.calls[1]
        finally:
            owner.close_read_aloud()
    passed.append('native_epub_reader')
    await app.toggle_bookmark()
    assert app.reader_manager().catalog.library_store.open(record['id'])[0]['epub_bookmarks'] == [
        dict(path=app.reader_manager().active.book_reader.spine[1], offset=app.reader_manager().active.epub_offset)]
    passed.append('native_bookmarks')
    record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), comic)
    background_comic = record['id']
    app.refresh_library()
    await app.open_book(record['id'])
    assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
    assert app.reader_manager().active.book_reader.pages == ['page2.png', 'page10.png']
    assert app.reader_manager().active.book_content.children[0].image.width == 1
    await app.next_book_page()
    assert app.reader_manager().active.book_record['position'] == 1
    await exercise_reader(app, passed)
    # Exercise a real archive larger than the former ordinary-library cap.
    from zipfile import ZipFile
    large = fixtures / 'large-ordinary.cbz'
    def make_large():
        with ZipFile(comic) as original, ZipFile(large, 'w') as archive:
            archive.writestr('page2.png', original.read('page2.png'))
            archive.writestr('page10.png', original.read('page10.png'))
            with archive.open('unrelated.bin', 'w') as output:
                for _ in range(257):
                    output.write(b'x' * 1024 * 1024)
    await asyncio.to_thread(make_large)
    record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), large)
    app.refresh_library()
    await app.open_book(record['id'])
    assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
    assert app.reader_manager().catalog.library_store.path(record['id'], '.cbz').stat().st_size > 256 * 1024 * 1024
    assert app.reader_manager().active.book_content.children[0].image.width == 1
    await app.next_book_page()
    assert app.reader_manager().active.book_record['position'] == 1 and app.reader_manager().active.book_content.children[0].image.width == 1
    large.unlink()
    protected_fixture = json.loads(Path(__file__).with_name('comic_fixture.json').read_text())
    from commonUtils.archives.zip_access import ArchivePasswordError
    from mobile.library import LibraryStore
    for codec in ('aes', 'legacy'):
        protected_comic = fixtures / (codec + '-standalone.cbz')
        original = base64.b64decode(protected_fixture[codec])
        protected_comic.write_bytes(original)
        protected_record = await asyncio.to_thread(app.reader_manager().catalog.library_store.import_book, LocalDocuments(), protected_comic)
        app.refresh_library()
        await app.open_book(protected_record['id'])
        assert app.reader_manager().active.book_reader is None and app.reader_manager().active.book_pending_key == protected_record['id'], app.reader_manager().active.book_status.text
        assert app.reader_manager().active.book_unlock_panel in app.reader_manager().active.library_view.children
        app.reader_manager().active.book_password.value = 'wrong password'
        await app.unlock_book()
        assert app.reader_manager().active.book_reader is None and app.reader_manager().active.book_pending_key == protected_record['id'], app.reader_manager().active.book_status.text
        assert app.reader_manager().active.book_password.value == '' and 'Try again' in app.reader_manager().active.book_status.text
        app.reader_manager().active.book_password.value = protected_fixture['password']
        await app.unlock_book()
        assert app.reader_manager().active.book_reader is not None, app.reader_manager().active.book_status.text
        assert app.reader_manager().active.book_reader.right_to_left and app.reader_manager().active.book_reader.pages == ['page2.png', 'page10.png']
        assert app.reader_manager().active.book_content.children[0].image.width == 1
        assert app.reader_manager().active.book_password.value == '' and app.reader_manager().active.book_unlock_panel not in app.reader_manager().active.library_view.children
        await app.next_book_page()
        assert app.reader_manager().active.book_record['position'] == 1
        assert app.reader_manager().active.bookmark_button not in app.reader_manager().active.reader_tools_view.content.children
        raw_source = app.reader_manager().active.book_reader.document.source
        owner = app.reader_manager().active
        assert app.close_session(owner.session.id)
        assert owner.book_reader is None and not owner.book_content.children
        assert raw_source.password is None and not raw_source.cache
        assert app.reader_manager().catalog.library_store.path(protected_record['id'], '.cbz').read_bytes() == original
        assert protected_fixture['password'].encode() not in app.reader_manager().catalog.library_store.path(protected_record['id'], '.json').read_bytes()
        reopened_store = LibraryStore(app.reader_manager().catalog.library_store.root)
        try:
            reopened_store.open(protected_record['id'])
        except ArchivePasswordError:
            pass
        else:
            raise AssertionError('Standalone comic password persisted across reader restart.')
        assert protected_comic.read_bytes() == original
    # Password detection must not grab keyboard focus after leaving reading.
    from threading import Event
    from unittest.mock import patch
    started, release = Event(), Event()
    original_open = app.reader_manager().catalog.library_store.open
    def delayed_password(*args, **kwargs):
        started.set()
        if not release.wait(10):
            raise RuntimeError('Native password fixture was not released')
        return original_open(*args, **kwargs)
    with patch.object(app.reader_manager().catalog.library_store, 'open', side_effect=delayed_password):
        task = asyncio.create_task(app.open_book(protected_record['id']))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(.01)
            assert started.is_set()
            owner = app.readers.active
            with patch.object(owner.book_password, 'focus') as focus:
                app.show_settings()
                body = app.body
                release.set()
                await task
                focus.assert_not_called()
                assert app.native_host.state.destination == 'settings' and app.body is body
                assert owner.book_pending_key == protected_record['id']
            app.cancel_book_unlock()
        finally:
            release.set()
            await task
    passed.append('native_comic_reader')
    return background_comic
