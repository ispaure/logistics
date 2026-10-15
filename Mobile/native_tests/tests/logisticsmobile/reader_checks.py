"""Actual native image zoom, compact reading and sanitized appearance content."""
import asyncio


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
            # The native controller's root defines the readable column on iPad
            # and the screen on iPhone, excluding system/window chrome. This
            # is independent of the Python comic widget. The height-stability
            # assertion below also detects shrinkage of this entire host.
            host = view._impl.container.native
            host_rect = host.convertRect(host.bounds, toView=window)
            safe = host.safeAreaInsets
            dy = rect.origin.y + rect.size.height / 2 - (
                host_rect.origin.y + (safe.top + host_rect.size.height - safe.bottom) / 2)
        else:
            from java import jarray, jint
            location = jarray(jint)(2)
            native.getLocationOnScreen(location)
            decor = view._impl._native_activity.getWindow().getDecorView()
            bars = decor.getRootWindowInsets().getInsets(jclass('android.view.WindowInsets$Type').systemBars())
            dy = location[1] + rect.centerY() - (bars.top + decor.getHeight() - bars.bottom) / 2
        assert abs(dy) < 2, ('Comic misses screen centre', dy,
            float(native.bounds.size.height) if hasattr(view._impl, 'picture') else
            (list(location), native.getHeight(), decor.getHeight(), bars.top, bars.bottom))


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


async def exercise_reader(app, passed):
    owner = app.reader_manager().active
    def current_view():
        displayed = owner.book_content.children[0]
        return displayed.canvases[0] if hasattr(displayed, 'canvases') else displayed
    current_view().set_zoom(2)
    await asyncio.sleep(.2)
    assert 1.9 <= current_view().zoom_scale <= 2.1, current_view().zoom_scale
    current_view().fit_page()
    assert current_view().zoom_scale == 1
    assert owner.reader_immersive and owner.library_view._comic_fullscreen
    assert owner.reader_header not in owner.library_view.children
    current_view().toggle_controls()
    assert not owner.reader_immersive and owner.reader_header in owner.library_view.children
    current_view().toggle_controls()
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
        current_view().toggle_controls()
        await asyncio.sleep(.1)
        current_view().toggle_controls()
        await assert_comic_centered(current_view, fullscreen=True)
        assert abs(viewport_height() - full_height) < 1, ('Fullscreen viewport shrank', full_height, viewport_height())
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
    await asyncio.sleep(.4)
    assert app.reader_manager().active.book_record['position'] == previous - 1
    app.reader_manager().active.book_content.children[0].page(1)
    await asyncio.sleep(.4)
    assert app.reader_manager().active.book_record['position'] == previous
    owner.show_reader_appearance()
    owner.reader_margin.value, owner.reader_theme.value = '24', 'dark'
    await owner.apply_reader_appearance()
    assert app.preferences.values['reading_margin'] == '24'
    assert app.reader_manager().active.book_record['position'] == previous
    owner.show_reader_tools()
    assert owner.bookmark_selector in owner.reader_tools_view.content.children
    owner.show_library()
    await assert_comic_centered(current_view, fullscreen=True)
    passed.append('native_comic_fullscreen_reentry')
    passed.append('native_reader_presentation')
