"""Window-level system-region wakeups for every native navigation bar."""


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
    bounds = getattr(native, 'bounds', None)
    safe = getattr(native, 'safeAreaInsets', None)
    geometry = (() if bounds is None or safe is None else
                (float(bounds.size.width), float(bounds.size.height), float(safe.top), float(safe.bottom)))
    state = (regions, geometry)
    if getattr(app, '_ios_window_occlusions', None) == state:
        return
    app._ios_window_occlusions = state
    if getattr(app, '_ios_occlusion_refresh_pending', False):
        return
    app._ios_occlusion_refresh_pending = True

    def refresh():
        app._ios_occlusion_refresh_pending = False
        if not getattr(app, 'active_host', False):
            return
        adapter = app.native_host.adapter
        navigation = list(getattr(adapter, 'navigation', ()))
        # UIKit can move a destination into More's navigation controller. Its
        # live owner is not necessarily in the original controller array.
        for destination in getattr(app.native_host, 'destinations', ()):
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
    """Place bar controls around current system regions and destination tabs.

    Vertical bars share space with destination tabs: let UIKit compress those
    tabs first instead of moving actions into them. Horizontal bars reserve only
    a missing top inset. Keep other owners' insets and all live target/actions.
    """
    from .ios_reader_chrome import occlusion_geometry
    view, bar = controller.view, controller.navigationBar
    previous = getattr(controller, '_logistics_occlusion_top', 0)
    safe = max(0, float(view.safeAreaInsets.top) - previous)
    frame = bar.convertRect(bar.bounds, toView=view)
    left, right = float(frame.origin.x), float(frame.origin.x + frame.size.width)
    content = getattr(controller, 'topViewController', None)
    from .ios_toolbar import vertical_edge
    # The adaptive bar's public frame can span the whole window, including
    # the horizontal title area, while its buttons run down the side.
    vertical = bool(vertical_edge(content)) if content is not None else frame.size.height > frame.size.width
    if content is not None:
        from rubicon.objc import SEL
        item = content.navigationItem
        if item.respondsToSelector(SEL('setVerticalBarCompressionBehavior:')):
            behavior = 1 if vertical and not bar.isHidden() else 0
            if int(item.verticalBarCompressionBehavior) != behavior:
                item.verticalBarCompressionBehavior = behavior
    top = control_top_clearance(occlusion_geometry(view), left, right, safe)
    extra = max(0, top - safe) if not vertical and not bar.isHidden() else 0
    if abs(extra - previous) <= .5:
        return False
    from rubicon.objc import UIEdgeInsets
    insets = controller.additionalSafeAreaInsets
    controller.additionalSafeAreaInsets = UIEdgeInsets(
        max(0, float(insets.top) - previous + extra), insets.left, insets.bottom, insets.right)
    controller._logistics_occlusion_top = extra
    return True
