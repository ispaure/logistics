"""Real orientation changes must preserve routes and respect the native safe area."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.EXTENDED
import asyncio
import json
from pathlib import Path
import sys

from commonUtils.testing.rotation import NativeRotation
from commonUtils.testing.waiting import wait_until, wait_for_assertion
from .settings import ROTATION_SETTLE, CONTROL_SETTLE_TIMEOUT


def panel_state(app):
    destination = app.native_host.state.destination
    body = app.body
    settings = getattr(app, 'settings_navigation', None)
    category = destination == 'settings' and settings is not None and settings.detail_requested
    route_state = tuple((key, tuple(row[0] for row in rows
                         if not (category and key == 'settings' and row[0] == 'settings-category')))
                        for key, rows in app.routes.screens.items())
    if category:
        panel = ('settings-category', settings.selected)
    else:
        # Wide Settings layouts move the category sidebar into the active route.
        sidebar = settings.sidebar if destination == 'settings' and settings is not None else None
        panel = tuple(id(child) for child in body.children if child is not sidebar)
        settings_routes = app.routes.screens['settings']
        if destination == 'settings' and settings_routes and settings_routes[-1][0] == 'documentation':
            reader = app.documentation
            panel += (id(reader.web), reader.path, tuple(reader.history), reader.history_index)
    source = getattr(app, 'folder_source', None) if destination == 'files' else None
    return (destination, route_state, panel, source, getattr(app, 'file_path', None),
            content_state(app),
            tuple(row[0] for row in app.adaptive.detail_routes), app.adaptive.in_detail)



def content_state(app):
    """Layout changes must retain logical content, not just the top route."""
    from hashlib import sha256
    reader = getattr(getattr(app, 'readers', None), 'active', None)
    record = getattr(reader, 'book_record', None) or {}
    private = getattr(getattr(app, 'private_sessions', None), 'active', None)
    comic = getattr(getattr(private, 'crypt_reader', None), 'comic_navigation', None)
    editor = getattr(app, 'editor_view', None)
    text = getattr(getattr(editor, 'editor', None), 'value', '') or ''
    return (record.get('id'), record.get('position'), getattr(comic, 'page', None),
            sha256(text.encode()).hexdigest())


def pose_snapshot(app):
    if sys.platform != 'ios':
        return dict(duo_capable=False)
    from dataclasses import asdict
    from mobile.fold_layout import reserved_divisions
    regions = reserved_divisions(app.main_window)
    all_regions = reserved_divisions(app.main_window, include_inactive=True)
    status = getattr(app, '_hinge_status', 0)
    native = app.main_window._impl.native
    return dict(duo_capable=bool(status or all_regions), hinge_status=status,
                division_regions=[asdict(region) for region in regions],
                horizontal_size_class=int(native.traitCollection.horizontalSizeClass),
                vertical_size_class=int(native.traitCollection.verticalSizeClass),
                interface_orientation=int(native.windowScene.interfaceOrientation),
                width=float(native.bounds.size.width), height=float(native.bounds.size.height))



async def rotate(app, orientation, *, settle=ROTATION_SETTLE, timeout=None):
    from .timings import section, measure
    rotation = NativeRotation(app.main_window,
                              activity=app._impl.native if sys.platform != 'ios' else None)
    def rejected(error):
        print('LOGISTICS_ROTATION_REJECTED=' + json.dumps(dict(
            orientation=orientation, error=error)), flush=True)
    with section(app, 'rotation-dispatch', orientation=orientation):
        rotation.request(orientation, on_rejected=rejected)
    with section(app, 'rotation-acknowledgement', orientation=orientation):
        from commonUtils.testing.settings import ROTATION_TIMEOUT
        await wait_until(lambda: rotation.acknowledged(orientation),
                         timeout=ROTATION_TIMEOUT if timeout is None else timeout,
                         message='Native rotation did not complete: ' + orientation)
    await measure(app, 'rotation-post-ack-settle', asyncio.sleep(settle), orientation=orientation)


def safe_geometry(app):
    if sys.platform != 'ios':
        from android.graphics import Rect
        from java import jarray, jint
        native = app.body.children[0]._impl.native
        viewport = Rect()
        app._impl.native.getWindow().getDecorView().getWindowVisibleDisplayFrame(viewport)
        position = jarray(jint)(2)
        native.getLocationOnScreen(position)
        result = dict(x=int(position[0]), y=int(position[1]),
                      view_width=int(native.getWidth()), view_height=int(native.getHeight()),
                      safe_left=viewport.left, safe_right=viewport.right,
                      safe_top=viewport.top, safe_bottom=viewport.bottom)
        assert result['view_width'] > 0 and result['view_height'] > 0, result
        assert result['x'] >= viewport.left - 1, result
        assert result['x'] + result['view_width'] <= viewport.right + 1, result
        assert result['y'] >= viewport.top - 1, result
        assert result['y'] + result['view_height'] <= viewport.bottom + 1, result
        return result
    view = app.body.children[0]
    container = view._impl.container
    size = container.native.bounds.size
    insets = container.native.safeAreaInsets
    native = view._impl.native
    rect = native.convertRect(native.bounds, toView=container.native)
    result = dict(width=float(size.width), height=float(size.height),
                  left=float(insets.left), right=float(insets.right),
                  top=float(insets.top), bottom=float(insets.bottom),
                  x=float(rect.origin.x), y=float(rect.origin.y),
                  view_width=float(rect.size.width), view_height=float(rect.size.height))
    from mobile.ios_content_background import preview_edge
    edge = preview_edge(app, container)
    result['image_preview_edge'] = edge
    window = app.main_window._impl.native
    window_rect = native.convertRect(native.bounds, toView=window)
    safe = window.safeAreaInsets
    minimum_top = float(insets.top)
    minimum_window_top = float(safe.top)
    from mobile.reader_edges import page_footer
    from mobile.ios_toolbar import vertical_edge
    from mobile.document_location import side_title_reader
    footer = page_footer(view)
    reader = side_title_reader(view)
    controller = (app.native_host.adapter.content_controller(app.native_host.state.destination)
                  if footer is not None or reader is not None else None)
    title = (reader._document_title_view if reader is not None else
             controller.navigationItem.titleView if controller is not None else None)
    if (title is not None and vertical_edge(controller)
            and title.superview is not None and not controller.navigationItem.prompt):
        title_rect = title.convertRect(title.bounds, toView=window)
        title_bottom = float(title_rect.origin.y + title_rect.size.height)
        title_gap = float(title_rect.origin.y - safe.top)
        body_rect = window_rect
        if reader is not None:
            frame = getattr(reader, '_reading_frame_owner', None)
            # Managed Markdown has a title row and WebView without a paginated
            # ReadingFrame. Measure its first actual content row after the title.
            from mobile.document_location import side_title_header
            content_view = (frame.content if frame is not None else next(
                child for child in reader.children
                if child is not side_title_header(reader) and child.layout.content_height > 0))
            content = content_view._impl.native
            body_rect = content.convertRect(content.bounds, toView=window)
        content_gap = float(body_rect.origin.y) - title_bottom
        result.update(reader_title_top_gap=title_gap, reader_title_content_gap=content_gap)
        outer_top = float(reader.style.margin_top or 0) if reader is not None else 0
        result['reader_title_outer_margin_top'] = outer_top
        assert 4 <= title_gap - outer_top <= 8, result
        assert 4 <= content_gap <= 8, result
        origin = container.native.convertRect(container.native.bounds, toView=window).origin
        minimum_top = (float(safe.top) if reader is not None else title_bottom + 4) - float(origin.y)
    # An internal navigation inset can exceed the window's hardware clearance.
    # If there is hardware clearance to reclaim, require measured top regions
    # outside the content column before allowing content into that strip.
    layout_top = getattr(container, 'top_inset', minimum_top)
    if (controller is None and layout_top < minimum_top
            and vertical_edge(getattr(container, 'controller', None))):
        from mobile.ios_reader_chrome import occlusion_geometry
        origin = container.native.convertRect(container.native.bounds, toView=window).origin
        hardware_top = max(0, minimum_window_top - float(origin.y))
        rectangular_top = max(minimum_top, hardware_top)
        regions = [(x, y, w, h) for x, y, w, h in occlusion_geometry(container.native)
                   if w > 0 and h > 0 and y <= rectangular_top and y + h > 0]
        result.update(top_regions=regions, hardware_top=hardware_top,
                      layout_top=float(layout_top), window_y=float(window_rect.origin.y))
        if (regions or hardware_top == 0) and all(
                x + w <= insets.left or x >= size.width - insets.right for x, _, w, _ in regions):
            minimum_top = max(0, float(layout_top))
            minimum_window_top = max(0, float(origin.y) + minimum_top)
    assert window_rect.origin.x >= (0 if edge == 1 else safe.left) - 1, result
    assert window_rect.origin.x + window_rect.size.width <= window.bounds.size.width - (0 if edge == 2 else safe.right) + 1, result
    assert window_rect.origin.y >= minimum_window_top - 1, result
    # A root background/scroll surface may extend beneath the Home indicator
    # and keyboard. Fixed foreground controls have their own stricter audit.
    assert window_rect.origin.y + window_rect.size.height <= window.bounds.size.height + 1, result
    assert result['view_width'] > 0 and result['view_height'] > 0, result
    assert rect.origin.x >= (0 if edge == 1 else insets.left) - 1, result
    assert rect.origin.x + rect.size.width <= size.width - (0 if edge == 2 else insets.right) + 1, result
    assert rect.origin.y >= minimum_top - 1, result
    assert rect.origin.y + rect.size.height <= size.height + 1, result
    return result


def epub_width_snapshot(app):
    """Content-free native/layout facts; no refresh, script, or style mutation."""
    result = {}
    def scalar(value):
        return value if value is None or isinstance(value, (bool, int, float)) else type(value).__name__
    def rect(value):
        return [float(value.origin.x), float(value.origin.y), float(value.size.width), float(value.size.height)]
    owner = getattr(getattr(app, 'private_sessions', None), 'active', None) or app
    panel = getattr(owner, 'provider_epub_view', None)
    widgets = [('root', app.body.children[0]), ('content', getattr(owner, 'crypt_content', None)),
               ('panel', panel), ('web', getattr(panel, 'webview', None))]
    result['window_bounds'] = rect(app.main_window._impl.native.bounds)
    result['toga_window_width'] = float(app.main_window.size.width)
    for role, widget in widgets:
        if widget is None:
            continue
        try:
            native = widget._impl.native
            container = getattr(widget._impl, 'container', None)
            result[role] = dict(style_width=scalar(widget.style.width),
                layout={key: scalar(getattr(widget.layout, key, None)) for key in
                        ('width', 'content_width', 'min_width', 'min_content_width')},
                native_frame=rect(native.frame), native_bounds=rect(native.bounds),
                window_rect=rect(native.convertRect(native.bounds, toView=app.main_window._impl.native)),
                container_width=scalar(getattr(container, 'width', None)),
                container_bounds=rect(container.native.bounds) if container is not None else None)
        except Exception as error:
            result[role] = dict(observer_error=type(error).__name__)
    result['sidebar_expanded'] = getattr(getattr(panel, 'sidebar', None), 'expanded', None)
    task = getattr(owner, '_provider_width_task', None)
    result['watcher'] = dict(present=task is not None,
        same_panel=getattr(owner, '_provider_width_panel', None) is panel)
    if task is not None:
        result['watcher'].update(done=task.done(), cancelled=task.cancelled(),
            stack=[frame.f_code.co_name for frame in task.get_stack(limit=4)])
        if task.done() and not task.cancelled():
            error = task.exception()
            result['watcher']['error_class'] = type(error).__name__ if error is not None else None
    return result


async def observe_epub_width_failure(app, *, panel, cycle, orientation):
    """Failure-only observations; never repair or accept the failed layout."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    report = dict(panel=panel, cycle=cycle, orientation=orientation, samples=[])
    try:
        native = rotation_failure_snapshot(app, panel=panel, cycle=cycle, orientation=orientation)
    except Exception as error:
        native = dict(schema=1, panel=panel, cycle=cycle, requested_orientation=orientation,
                      native_observer_error=type(error).__name__)
    path = Path(app.paths.cache) / 'logistics-native-ui-rotation-failure.json'
    def persist():
        native['reader_width'] = report
        text = json.dumps(native)
        if len(text.encode()) > 16384 and len(report['samples']) > 2:
            report['samples'] = [report['samples'][0], report['samples'][-1]]
            report['truncated'] = True
            text = json.dumps(native)
        if len(text.encode()) > 16384:
            raise ValueError('Rotation width diagnostics exceeded bounded budget')
        app._native_rotation_failure = native  # Existing cached result/chunk transport.
        temporary = path.with_suffix('.tmp')
        temporary.write_text(text + '\n')
        temporary.replace(path)
    def capture(stage):
        report['samples'].append(dict(stage=stage, elapsed=loop.time()-started,
                                      **epub_width_snapshot(app)))
        persist()
    try:
        capture('latched-failure')
        signal = getattr(app, '_reader_layout_signal', None)
        changed = signal.waiter(initial=False) if signal is not None else None
        turn = loop.create_future()
        loop.call_soon(lambda: None if turn.done() else turn.set_result(None))
        await turn
        capture('next-loop-turn')
        while changed is not None and len(report['samples']) < 4:
            remaining = CONTROL_SETTLE_TIMEOUT - (loop.time()-started)
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(changed(), timeout=remaining)
            except asyncio.TimeoutError:
                capture('observation-budget-ended')
                break
            capture('native-layout-notification')
    finally:
        persist()
        print('LOGISTICS_EPUB_WIDTH_FAILURE=' + json.dumps(native), flush=True)


async def capture_epub_width_failure(app, *, panel, cycle, orientation):
    """Observation failures/cancellation must not replace the latched assertion."""
    if sys.platform == 'ios' and panel == 'provider-epub':
        try:
            await observe_epub_width_failure(app, panel=panel, cycle=cycle, orientation=orientation)
        except BaseException as error:
            print('LOGISTICS_EPUB_WIDTH_OBSERVER_ERROR=' + type(error).__name__, flush=True)


def promoted_controls(widget):
    """Resolve both retained action lists and dynamic toolbar providers."""
    for field in ('title_actions', '_ios_toolbar_buttons', '_ios_toolbar_leading'):
        controls = getattr(widget, field, ())
        if callable(controls):
            controls = controls()
        yield from controls or ()


def assert_visible_controls(app):
    """Fixed controls must stay inside cutout/Home-indicator safe bounds."""
    if sys.platform != 'ios':
        return 0
    import toga
    window = app.main_window._impl.native
    checked = (toga.Button, toga.Selection, toga.TextInput, toga.MultilineTextInput)
    count = 0
    seen = set()
    from commonUtils.ui.native.keyboard import native_value
    def visit(widget, footer_view=None):
        nonlocal count
        if id(widget) in seen:
            return
        seen.add(id(widget))
        if getattr(widget, '_reader_page_footer', None) is not None:
            footer_view = widget
        native = widget._impl.native
        owner = native.window
        owner = owner() if callable(owner) else owner
        if (isinstance(widget, checked) and owner is not None
                and owner.ptr.value == window.ptr.value and not native.isHidden()):
            rect = native.convertRect(native.bounds, toView=window)
            if rect.size.width > 0 and rect.size.height > 0:
                count += 1
                label = getattr(widget, 'accessible_name', None) or getattr(widget, 'text', type(widget).__name__)
                from mobile.reader_edges import footer_touch_extension
                extension = footer_touch_extension(footer_view, float(window.safeAreaInsets.bottom)) if footer_view else 0
                assert_control_bounds(rect, window, label, bottom_extension=extension)
        # Promoted actions retain callbacks outside the Toga content tree.
        for control in promoted_controls(widget):
            visit(control)
        # Scrollable form content is deliberately allowed beyond its viewport.
        if not isinstance(widget, toga.ScrollContainer):
            for child in widget.children:
                visit(child, footer_view)
    visit(app.body)
    # UIKit bar items retain Toga callbacks, but mount UIKit-owned controls:
    # the original UIButton has no window and cannot provide their geometry.
    adapter = getattr(getattr(app, 'native_host', None), 'adapter', None)
    if adapter is not None:
        from rubicon.objc import ObjCClass
        navigation = adapter.navigation[app.native_host.destinations.index(app.native_host.state.destination)]
        bar = native_value(navigation.navigationBar)
        control_class = ObjCClass('UIControl')
        def visit_bar(native):
            nonlocal count
            if native.isHidden() or float(native.alpha) <= 0:
                return
            owner = native_value(native.window)
            label = str(native_value(native.accessibilityLabel) or '')
            # UIKit lays out its own controls in the navigation bar, outside
            # the window's stricter content-safe inset on landscape iPhones.
            if (native.isKindOfClass(control_class) and owner is not None
                    and owner.ptr.value == window.ptr.value):
                rect = native.convertRect(native.bounds, toView=bar)
                if rect.size.width > 0 and rect.size.height > 0:
                    assert_bar_control_bounds(rect, bar.bounds, label)
                    count += 1
            for child in native_value(native.subviews):
                visit_bar(child)
        visit_bar(bar)
    return count



async def settled_visible_controls(app):
    """Wait briefly for UIKit's rotation morph, retaining strict final bounds."""
    return await wait_for_assertion(lambda: assert_visible_controls(app),
                                    timeout=CONTROL_SETTLE_TIMEOUT)


async def settled_rotation_layout(app):
    """Controls and content must pass together within one animation budget."""
    def ready():
        controls = assert_visible_controls(app)
        safe_geometry(app)
        return controls
    return await wait_for_assertion(ready, timeout=CONTROL_SETTLE_TIMEOUT)


async def assert_welcome_actions_reachable(app):
    """Exercise both ends of the empty Notes Library's scrollable actions."""
    if sys.platform != 'ios':
        return
    owner = app.vault_browser
    scroll = owner.welcome
    original = scroll.vertical_position
    window = app.main_window._impl.native
    try:
        for button, position in ((owner.open_card, 0),
                                 (owner.new_card, scroll.max_vertical_position)):
            if button not in owner.welcome_content.children:
                continue
            scroll.vertical_position = position
            native = button._impl.native
            if native.isHidden():
                continue
            # Toga's iOS ScrollContainer animates setContentOffset. Observe the
            # completed movement rather than measuring a partial animation.
            await wait_for_assertion(lambda: assert_control_bounds(
                native.convertRect(native.bounds, toView=window), window, button.text),
                timeout=CONTROL_SETTLE_TIMEOUT)
    finally:
        scroll.vertical_position = original


def assert_bar_control_bounds(rect, bounds, label):
    details = (label, str(rect), str(bounds))
    assert rect.origin.x >= bounds.origin.x - 1, details
    assert rect.origin.y >= bounds.origin.y - 1, details
    assert rect.origin.x + rect.size.width <= bounds.origin.x + bounds.size.width + 1, details
    assert rect.origin.y + rect.size.height <= bounds.origin.y + bounds.size.height + 1, details


def assert_control_bounds(rect, window, label, *, bottom_extension=0):
    safe, size = window.safeAreaInsets, window.bounds.size
    details = (label, float(rect.origin.x), float(rect.origin.y),
               float(rect.size.width), float(rect.size.height))
    assert rect.origin.x >= safe.left - 1, details
    assert rect.origin.x + rect.size.width <= size.width - safe.right + 1, details
    assert rect.origin.y >= safe.top - 1, details
    assert rect.origin.y + rect.size.height <= size.height - safe.bottom + bottom_extension + 1, details


def rotation_failure_snapshot(app, *, panel, cycle, orientation):
    """Synchronous failure-only observations; never change the failed operation."""
    import time
    import threading
    def value(owner, name):
        try:
            result = getattr(owner, name)
            return result() if callable(result) else result
        except Exception:
            return None
    def view(native):
        if native is None:
            return None
        layer = value(native, 'layer')
        presented = value(layer, 'presentationLayer')
        return dict(class_name=str(value(native, 'className')), attached=value(native, 'window') is not None,
                    hidden=value(native, 'isHidden'), bounds=str(value(native, 'bounds')),
                    model_frame=str(value(layer, 'frame')), presentation_frame=str(value(presented, 'frame')),
                    has_animations=bool(value(layer, 'animationKeys')))
    def controller(native):
        if native is None:
            return None
        coordinator = value(native, 'transitionCoordinator')
        modal = value(native, 'presentedViewController')
        return dict(class_name=str(value(native, 'className')), view=view(value(native, 'viewIfLoaded')),
                    transition_active=coordinator is not None,
                    transition_animated=value(coordinator, 'isAnimated'),
                    transition_interactive=value(coordinator, 'isInteractive'),
                    modal_present=modal is not None, modal_class=str(value(modal, 'className')),
                    being_presented=value(native, 'isBeingPresented'), being_dismissed=value(native, 'isBeingDismissed'))
    window = app.main_window._impl.native
    privacy = getattr(app, 'screen_privacy', None)
    adapter = app.native_host.adapter
    destination = app.native_host.state.destination
    scene = value(window, 'windowScene')
    result = dict(schema=1, captured_ns=time.time_ns(), monotonic=time.monotonic(),
                  main_thread=threading.current_thread() is threading.main_thread(),
                  scene_attached=scene is not None,
                  panel=panel, cycle=cycle, requested_orientation=orientation,
                  interface_orientation=value(scene, 'interfaceOrientation'),
                  scene_active=value(scene, 'activationState') == 0,
                  window=view(window),
                  controllers=[controller(value(window, 'rootViewController')),
                               controller(adapter.content_controller(destination)),
                               controller(adapter.navigation_for(destination))],
                  privacy={key: bool(getattr(privacy, key, False))
                           for key in ('inactive', 'resume_locked', 'disposed', 'interrupted')},
                  privacy_shield=view(getattr(privacy, 'shield', None)))
    path = Path(app.paths.cache) / 'logistics-native-ui-rotation-failure.json'
    text = json.dumps(result)
    if len(text.encode()) > 16384:
        raise ValueError('Rotation failure snapshot exceeded its bounded budget')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(text + '\n')
    temporary.replace(path)
    print('LOGISTICS_NATIVE_ROTATION_FAILURE=' + text, flush=True)
    return result


async def rotate_panel(app, *, panel, cycle, orientation):
    """Keep original deadline/exception even when the observer itself fails."""
    from .timings import measure
    try:
        await measure(app, 'rotation-request', rotate(app, orientation),
                      panel=panel, orientation=orientation, cycle=cycle)
    except AssertionError:
        try:
            if sys.platform == 'ios':
                rotation_failure_snapshot(app, panel=panel, cycle=cycle, orientation=orientation)
        except Exception:
            pass
        raise


async def exercise_rotation(app, *, record=None, cycles=2, panels=None):
    from .rotation_screens import select_screens
    # Validate before any navigation or native orientation request.
    panels = tuple(screen.panel for screen in select_screens(panels))
    if type(cycles) is not int or cycles < 1:
        raise ValueError('Rotation cycles must be a positive integer.')
    samples = []
    captured = set()
    from .timings import measure, section
    async def check_panel(name):
        if panels is not None and name not in panels:
            return
        await asyncio.sleep(.4)
        print('LOGISTICS_ROTATION_PANEL=' + name, flush=True)
        expected = panel_state(app)
        for cycle in range(cycles):
            for orientation in ('portrait', 'landscape-left', 'portrait', 'landscape-right', 'portrait'):
                await rotate_panel(app, panel=name, orientation=orientation, cycle=cycle)
                try:
                    controls = await measure(app, 'rotation-control-settle', settled_rotation_layout(app),
                                             panel=name, orientation=orientation, cycle=cycle)
                except AssertionError:
                    await capture_epub_width_failure(app, panel=name, cycle=cycle, orientation=orientation)
                    raise
                if name == 'notes-library':
                    await assert_welcome_actions_reachable(app)
                actual = panel_state(app)
                assert actual == expected, (name, orientation, expected, actual)
                try:
                    with section(app, 'rotation-geometry', panel=name, orientation=orientation, cycle=cycle):
                        sample = dict(panel=name, cycle=cycle, orientation=orientation,
                                      pose=pose_snapshot(app), **safe_geometry(app))
                except AssertionError:
                    await capture_epub_width_failure(app, panel=name, cycle=cycle, orientation=orientation)
                    raise
                sample['fixed_controls'] = controls
                if sys.platform == 'ios' and name in ('folder', 'nested-folder', 'home-file-picker'):
                    assert sample['fixed_controls'] >= 1, ('No mounted controls audited', name)
                samples.append(sample)
                print('LOGISTICS_ROTATION_SAMPLE=' + json.dumps(sample), flush=True)
                if record:
                    record(samples)
                    key = (name, orientation)
                    if cycle == 0 and key not in captured:
                        from .fixtures import capture_window
                        captured.add(key)
                        await capture_window(app, Path(app.paths.cache) / f'rotation-{name}-{orientation}.png')
    async def check(name):
        if panels is not None and name not in panels:
            return
        return await measure(app, 'rotation-panel', check_panel(name), panel=name)

    from .rotation_screens import coverage_inventory, visit_screens
    await visit_screens(app, check, panels=panels)
    from mobile.navigation import DESTINATION_ITEMS
    from mobile.settings.categories import CATEGORIES
    return {'rotation_preserves_panels': True, 'rotation_samples': samples,
            'rotation_inventory': coverage_inventory(DESTINATION_ITEMS, CATEGORIES, panels=panels)}
