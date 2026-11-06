"""Window-level system-region wakeups for every native navigation bar."""

from weakref import ref


def native_geometry(native):
    """Geometry in the current window, including equal-size window moves.

    Never use a screen/model size or a previously retained tab's allocation.
    The window frame matters for system Split View even when its size is stable.
    """
    if native is None:
        return ()
    bounds, safe = getattr(native, 'bounds', None), getattr(native, 'safeAreaInsets', None)
    if bounds is None or safe is None:
        return ()
    window = getattr(native, 'window', None)
    window = window() if callable(window) else window
    frame = native.convertRect(bounds, toView=window) if window is not None else bounds
    window_frame = getattr(window, 'frame', None)
    def rect(value):
        return (float(value.origin.x), float(value.origin.y),
                float(value.size.width), float(value.size.height))
    return (rect(frame), tuple(float(getattr(safe, side, 0)) for side in ('top', 'left', 'bottom', 'right')),
            rect(window_frame) if window_frame is not None else ())


def compact_content_top(container):
    """Reclaim an empty rectangular band beside a vertical system rail.

    Horizontal title/Back bars retain UIKit's safe area. Reader title headers
    and Home's measured header have their own shared policies below this one.
    """
    from .ios_toolbar import vertical_edge
    controller = getattr(container, 'controller', None)
    if controller is None or not vertical_edge(controller):
        return False
    navigation = getattr(controller, 'navigationController', None)
    navigation = navigation() if callable(navigation) else navigation
    if hasattr(controller, 'navigationBar'):
        navigation = controller
    content = getattr(navigation, 'topViewController', controller)
    item = getattr(content, 'navigationItem', None)
    if (navigation is not None and not navigation.isNavigationBarHidden() and item is not None
            and (item.titleView is not None or item.prompt or item.title)):
        return False
    window = getattr(container.native, 'window', None)
    window = window() if callable(window) else window
    if window is None:
        return False
    from .reader_edges import apple_reader_top
    top = apple_reader_top(container, window)
    if abs(container.top_inset - top) <= .5:
        return False
    container.top_inset = top
    return True


def observe_window_occlusions(app, native):
    """Read inside root layout, independently of toolkit size notifications.

    The toolkit's window callback suppresses equal-size notifications. An
    expanding media Island does not resize the window, and need not lay out
    an unchanged leaf container. Query the root here so UIKit also tracks this
    root's dependency on reserved regions.
    """
    from .ios_reader_chrome import occlusion_geometry
    regions = occlusion_geometry(native)
    if app is None or not getattr(app, 'active_host', False):
        return
    adapter = app.native_host.adapter
    if adapter is None:
        app._ios_window_occlusions = None
        return
    state = (regions, native_geometry(native))
    owner = getattr(app, '_ios_window_occlusion_owner', None)
    if owner is not None and owner() is adapter and getattr(app, '_ios_window_occlusions', None) == state:
        return
    app._ios_window_occlusion_owner = ref(adapter)
    app._ios_window_occlusions = state
    if getattr(app, '_ios_occlusion_refresh_pending', False):
        return
    app._ios_occlusion_refresh_pending = True

    def refresh():
        app._ios_occlusion_refresh_pending = False
        if not getattr(app, 'active_host', False):
            app._ios_window_occlusions = None
            return
        host = app.native_host
        adapter = host.adapter
        if adapter is None:
            app._ios_window_occlusions = None
            return
        navigation = list(getattr(adapter, 'navigation', ()))
        # UIKit can move a destination into More's navigation controller. Its
        # live owner is not necessarily in the original controller array.
        for destination in getattr(host, 'destinations', ()):
            navigation.append(adapter.navigation_for(destination))
        outer = getattr(adapter, 'outer_navigation', None)
        if outer is not None:
            navigation.append(outer)
        secondary = getattr(getattr(app, 'adaptive', None), 'secondary', None)
        if secondary is not None:
            navigation.append(secondary)
        seen = set()
        for controller in navigation:
            pointer = getattr(controller, 'ptr', None)
            key = pointer.value if pointer is not None else id(controller)
            if key in seen:
                continue
            seen.add(key)
            # Invalidate the owner as well as its bar. Recreating button groups
            # alone does not establish that the navigation layout was updated.
            # Retain all live items, menu providers and UIKit's own placement.
            reserve_bar_clearance(controller)
            controller.view.setNeedsLayout()
            controller.navigationBar.setNeedsLayout()
            controller.view.layoutIfNeeded()
        app.resize_workspace()

    app.loop.call_soon(refresh)


def control_top_clearance(regions, left, right, safe_top, *, target=44, gap=8):
    """Reserve the full top cluster intersecting a column of touch targets.

    Include detached activity bubbles as well as the camera region. The next
    target must fit below every intersecting region; unrelated columns and
    regions farther down the screen do not consume top clearance.
    """
    top = max(0, safe_top)
    pending = [(y, y + height) for x, y, width, height in regions
               if width > 0 and height > 0 and x < right and x + width > left
               and y + height > 0]
    for start, end in sorted(pending):
        if start < top + target:
            top = max(top, end + gap)
    return top


def reserve_bar_clearance(controller):
    """Let UIKit place native items; configure only its compression preference.

    Reserved regions belong to custom content layout. Native navigation bars
    already avoid system activity and own overflow. Never add a camera/Island
    inset to them; clear only a contribution left by the older app policy.
    """
    from .ios_toolbar import vertical_edge
    from rubicon.objc import SEL
    content = getattr(controller, 'topViewController', None)
    if content is not None:
        item = content.navigationItem
        if item.respondsToSelector(SEL('setVerticalBarCompressionBehavior:')):
            behavior = 1 if vertical_edge(content) else 0
            if int(item.verticalBarCompressionBehavior) != behavior:
                item.verticalBarCompressionBehavior = behavior
    previous = getattr(controller, '_logistics_occlusion_top', 0)
    if not previous:
        return False
    from rubicon.objc import UIEdgeInsets
    insets = controller.additionalSafeAreaInsets
    # Assigning native insets can synchronously call layout again.
    controller._logistics_occlusion_top = 0
    controller.additionalSafeAreaInsets = UIEdgeInsets(
        max(0, float(insets.top) - previous), insets.left, insets.bottom, insets.right)
    return True
