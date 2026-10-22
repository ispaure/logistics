"""Window-local UIKit safe-area wakeups and fullscreen image policy."""
import weakref

_hosts = weakref.WeakValueDictionary()
_installed = False


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

    # Toga constructs the outer window navigation controller through this symbol.
    # Leave unregistered windows and ordinary routes under UIKit's normal policy.
    containers.UINavigationController = LogisticsReadingNavigationController
    original_layout = AppleNavigation.layout_content

    def layout_content(container):
        if getattr(container, '_logistics_layout_active', False):
            return
        container._logistics_layout_active = True
        try:
            original_layout(container)
            if fullscreen(container.native.window, images=True):
                # Fullscreen image readers retain their existing all-edge policy.
                changed = any((container.top_inset, container.bottom_inset,
                               container.left_inset, container.right_inset))
                container.top_inset = container.bottom_inset = 0
                container.left_inset = container.right_inset = 0
            else:
                from .ios_content_background import expand_preview
                changed = expand_preview(container)
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
    geometry = (float(container.width), float(container.height),
                container.top_inset, container.bottom_inset, container.left_inset, container.right_inset)
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
