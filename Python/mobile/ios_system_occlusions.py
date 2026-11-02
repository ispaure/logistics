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
    if getattr(app, '_ios_window_occlusions', None) == regions:
        return
    app._ios_window_occlusions = regions
    if getattr(app, '_ios_occlusion_refresh_pending', False):
        return
    app._ios_occlusion_refresh_pending = True

    def refresh():
        app._ios_occlusion_refresh_pending = False
        if not getattr(app, 'active_host', False):
            return
        adapter = app.native_host.adapter
        navigation = list(getattr(adapter, 'navigation', ()))
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
            controller.view.setNeedsLayout()
            controller.navigationBar.setNeedsLayout()
            controller.view.layoutIfNeeded()
        app.resize_workspace()

    app.loop.call_soon(refresh)
