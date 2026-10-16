"""Window-local fullscreen image policy over the pinned UIKit host."""
import weakref

_hosts = weakref.WeakValueDictionary()
_installed = False


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
        original_layout(container)
        if fullscreen(container.native.window, images=True):
            # Only the image presentation extends under system safe areas.
            # Normal routes get their measured insets back on the next layout.
            changed = any((container.top_inset, container.bottom_inset,
                           container.left_inset, container.right_inset))
            container.top_inset = container.bottom_inset = 0
            container.left_inset = container.right_inset = 0
            if changed and container.content is not None:
                container.content.interface.refresh()

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
