"""Window-local UIKit safe-area wakeups and fullscreen image policy."""
import weakref

_hosts = weakref.WeakValueDictionary()
_installed = False


def content_control(button):
    """Restore inline UIKit glass when a reader leaves the navigation bar."""
    if not type(button._impl).__module__.startswith('toga_iOS.'):
        return
    from .appearance import paint_surface
    button._impl._native_bar_control = False
    if getattr(button, 'control_icon', None) in {'close', 'more', 'overflow'}:
        button._impl._native_glass_control = True
    paint_surface(button._impl, 0)


def bar_control(button):
    """Use UIKit's bar background, retaining the live button and its menu."""
    from .appearance import paint_surface
    button._impl._native_bar_control = True
    paint_surface(button._impl, 0)
    return button._impl.native


def bar_group(buttons, *, size=44):
    from commonUtils.ui.native.bars import apple_bar_group
    item, group = apple_bar_group(buttons, native_control=bar_control, size=size)
    for button in buttons:
        button._native_reader_item = item
    return item, group


from commonUtils.ui.native.bars import apple_bar_separator as bar_separator


from .ios_toolbar import action_groups


def reader_title(text, width, actions):
    from commonUtils.ui.native.bars import apple_bar_title
    from .appearance import apple_color
    return apple_bar_title(text, width, actions, color=apple_color('text'))


def fullscreen(window, *, images=False):
    window = window() if callable(window) else window
    app = _hosts.get(window.ptr.value) if window is not None else None
    return bool(app is not None and getattr(app,
        '_comic_chrome_hidden' if images else '_reader_chrome_hidden', False))


def install_shell_root(adapter, root_class):
    """Keep the tab/navigation hierarchy outside Toga's unused outer bar.

    A navigation controller above the tab controller prevents UIKit's shared
    vertical bar from coordinating tab compression with the inner bar items.
    Retain the toolkit's container, callbacks and title adapter; only its unused
    navigation wrapper leaves the window hierarchy for the host's lifetime.
    """
    from rubicon.objc import ObjCClass, SEL
    if (getattr(adapter, '_logistics_shell_root', None) is not None
            or not adapter.parent.respondsToSelector(SEL('setNeedsUpdateOfVerticalBarConfiguration'))):
        return
    window, outer, content = adapter.window._impl.native, adapter.outer_navigation, adapter.parent
    stack = list(outer.viewControllers)
    if window.rootViewController != outer or stack != [content]:
        return
    root = root_class.alloc().init()
    placeholder = ObjCClass('UIViewController').alloc().init()
    placeholder.title = content.title
    outer.setViewControllers([placeholder], animated=False)
    # UIKit can retain the departing child until its next layout even without
    # animation. Finish public containment removal before attaching it again.
    attached = content.parentViewController is not None
    if attached:
        content.willMoveToParentViewController(None)
    content.view.removeFromSuperview()
    if attached:
        content.removeFromParentViewController()
    root.addChildViewController(content)
    root.view.frame = window.bounds
    content.view.frame = root.view.bounds
    adapter._logistics_shell_autoresizing = content.view.autoresizingMask
    content.view.autoresizingMask = 18  # Flexible width and height, owned by UIKit.
    root.view.addSubview(content.view)
    content.didMoveToParentViewController(root)
    adapter._logistics_shell_root = root
    adapter._logistics_shell_stack = stack
    adapter._logistics_shell_placeholder = placeholder
    window.rootViewController = root


def restore_shell_root(adapter):
    """Return the original toolkit hierarchy before the native host retires."""
    root = getattr(adapter, '_logistics_shell_root', None)
    if root is None:
        return
    content, window = adapter.parent, adapter.window._impl.native
    content.willMoveToParentViewController(None)
    content.view.removeFromSuperview()
    content.removeFromParentViewController()
    content.view.autoresizingMask = adapter._logistics_shell_autoresizing
    content.title = adapter._logistics_shell_placeholder.title
    adapter.outer_navigation.setViewControllers(adapter._logistics_shell_stack, animated=False)
    if window.rootViewController == root:
        window.rootViewController = adapter.outer_navigation
    adapter._logistics_shell_root = None
    adapter._logistics_shell_stack = None
    adapter._logistics_shell_placeholder = None
    adapter._logistics_shell_autoresizing = None


def install():
    global _installed
    if _installed:
        return
    from ctypes import c_bool
    from rubicon.objc import ObjCInstance, objc_method, objc_id, send_super
    import toga_iOS.container as containers
    from commonUtils.ui.native.navigation import AppleNavigation

    class LogisticsReadingNavigationController(containers.UINavigationController):
        @objc_method
        def prefersStatusBarHidden(self) -> bool:
            if fullscreen(self.view.window):
                return True
            return bool(send_super(__class__, self, 'prefersStatusBarHidden', restype=c_bool))

        @objc_method
        def childViewControllerForStatusBarHidden(self) -> objc_id:
            if fullscreen(self.view.window):
                return None
            result = send_super(__class__, self, 'childViewControllerForStatusBarHidden', restype=objc_id)
            return ObjCInstance(result) if result else None

    class LogisticsShellController(containers.UIViewController):
        @objc_method
        def prefersStatusBarHidden(self) -> bool:
            return fullscreen(self.view.window)

        @objc_method
        def childViewControllerForStatusBarHidden(self) -> objc_id:
            children = list(self.childViewControllers)
            return None if fullscreen(self.view.window) or not children else children[0]

    # Toga constructs the outer window navigation controller through this symbol.
    # Leave unregistered windows and ordinary routes under UIKit's normal policy.
    containers.UINavigationController = LogisticsReadingNavigationController
    original_layout = AppleNavigation.layout_content
    original_window_layout = AppleNavigation.layout_window
    original_init, original_dispose = AppleNavigation.__init__, AppleNavigation.dispose

    def initialize(adapter, host, window):
        original_init(adapter, host, window)
        install_shell_root(adapter, LogisticsShellController)

    def dispose(adapter):
        restore_shell_root(adapter)
        original_dispose(adapter)

    AppleNavigation.__init__, AppleNavigation.dispose = initialize, dispose

    def layout_window(adapter, container):
        original_window_layout(adapter, container)
        from .ios_system_occlusions import observe_window_occlusions, reserve_bar_clearance
        reserve_bar_clearance(adapter.outer_navigation)
        reserve_bar_clearance(adapter.navigation_for(adapter.host.state.destination))
        window = adapter.window._impl.native
        observe_window_occlusions(_hosts.get(window.ptr.value), container.native)

    AppleNavigation.layout_window = layout_window

    def layout_content(container):
        if getattr(container, '_logistics_layout_active', False):
            return
        container._logistics_layout_active = True
        try:
            original_layout(container)
            controller = getattr(container, 'controller', None)
            if controller is not None and hasattr(controller, 'navigationBar'):
                from .ios_system_occlusions import reserve_bar_clearance
                reserve_bar_clearance(controller)
            if fullscreen(container.native.window, images=True):
                # Fullscreen image readers retain their existing all-edge policy.
                changed = any((container.top_inset, container.bottom_inset,
                               container.left_inset, container.right_inset))
                container.top_inset = container.bottom_inset = 0
                container.left_inset = container.right_inset = 0
            else:
                from .ios_system_occlusions import compact_content_top
                changed = compact_content_top(container)
                from .home_header import compact_content_top as compact_home
                changed = compact_home(container) or changed
                from .ios_content_background import expand_preview
                changed = expand_preview(container) or changed
                from .reader_edges import compact_apple_reader
                changed = compact_apple_reader(container) or changed
            if changed and container.content is not None:
                container.content.interface.refresh()
            # Observe effective geometry, not the intermediate safe layout.
            notify_viewport(container)
        finally:
            container._logistics_layout_active = False

    AppleNavigation.layout_content = staticmethod(layout_content)
    _installed = True


def sync(app):
    if not type(app._impl).__module__.startswith('toga_iOS.'):
        return
    adapter = app.native_host.adapter
    if adapter is None or not hasattr(adapter, 'navigation'):
        return
    window = app.main_window._impl.native
    _hosts[window.ptr.value] = app
    from .ios_content_background import sync as sync_background
    sync_background(app)
    state = (app._reader_chrome_hidden, app._comic_chrome_hidden)
    if getattr(app, '_ios_reader_chrome_state', None) == state:
        return
    app._ios_reader_chrome_state = state
    window.rootViewController.setNeedsStatusBarAppearanceUpdate()
    index = app.native_host.destinations.index(app.native_host.state.destination)
    container = adapter.containers[index][0]
    adapter.layout_content(container)
    body = app.routes.body()
    if body.children:
        leaf = body.children[0]._impl.container
        if leaf is not None and leaf is not container:
            adapter.layout_content(leaf)
    window.setNeedsLayout()


def notify_viewport(container):
    """Wake responsive panels after actual size/inset changes, including shrink."""
    if container.content is None or container.width <= 0 or container.height <= 0:
        return
    root = container.content.interface
    app = root.app
    if app is None or not getattr(app, 'active_host', False):
        return
    from .ios_toolbar import vertical_edge
    from .ios_system_occlusions import native_geometry
    regions = occlusion_geometry(getattr(container, 'native', None))
    geometry = (float(container.width), float(container.height),
                container.top_inset, container.bottom_inset, container.left_inset, container.right_inset,
                vertical_edge(getattr(container, 'controller', None)), regions,
                native_geometry(getattr(container, 'native', None)))
    if geometry == getattr(container, '_logistics_viewport', None):
        return
    container._logistics_viewport = geometry
    if getattr(app, '_viewport_resize_pending', False):
        return
    app._viewport_resize_pending = True
    def resized():
        app._viewport_resize_pending = False
        if app.active_host:
            app.resize_workspace()
    app.loop.call_soon(resized)


def occlusion_geometry(native):
    """Read during UIKit layout so reserved-region changes invalidate it again.

    A changing Dynamic Island need not change the rectangular safe area, window
    dimensions or bar edge. Keep that system-owned geometry in the viewport key.
    """
    if native is None:
        return ()
    from rubicon.objc import ObjCClass, SEL
    if not native.respondsToSelector(SEL('reservedRegionsOfKind:options:')):
        return ()
    kind = ObjCClass('UIViewReservedRegionKind').occlusionRegionKind()
    # Materialize Swift-backed NSArray results before Python iteration. The
    # pinned bridge can reenter lazy selector discovery for Swift array classes
    # during UIKit callbacks; a Foundation-owned array uses its stable adapter.
    regions = ObjCClass('NSMutableArray').arrayWithArray(native.reservedRegionsOfKind(kind, options=0))
    return tuple(sorted((float(r.frame.origin.x), float(r.frame.origin.y),
                  float(r.frame.size.width), float(r.frame.size.height))
                 for r in regions))
