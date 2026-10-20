"""Window-local UIKit safe-area wakeups and fullscreen image policy."""
import weakref

_hosts = weakref.WeakValueDictionary()
_installed = False
_title_view_type = None


def reader_title(text, width, actions):
    """Keep the visible title centered even with asymmetric UIKit bar groups."""
    global _title_view_type
    from rubicon.objc import ObjCClass, objc_method, objc_property, send_super, CGRect
    if _title_view_type is None:
        class LogisticsReaderTitle(ObjCClass('UIView')):
            readerActions = objc_property(object)
            readerWidth = objc_property(object)

            @objc_method
            def didMoveToWindow(self) -> None:
                send_super(__class__, self, 'didMoveToWindow')
                self.setNeedsLayout()

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(__class__, self, 'layoutSubviews')
                label, window = self.viewWithTag(7311), self.window
                window = window() if callable(window) else window
                if label is None or window is None:
                    return
                center = float(window.bounds.size.width) / 2
                available = float(self.bounds.size.width)
                group = self.readerActions
                group_window = group.window if group is not None else None
                group_window = group_window() if callable(group_window) else group_window
                if group_window is not None:
                    rect = group.convertRect(group.bounds, toView=window)
                    # On iPad UIKit can put tab/action groups in the row above
                    # the title. Only a group sharing the title row limits it.
                    own = self.convertRect(self.bounds, toView=window)
                    if abs(float(rect.origin.y - own.origin.y)) < 44:
                        available = min(available, max(44, 2 * (float(rect.origin.x) - center - 24)))
                if self.readerWidth is None:
                    label.translatesAutoresizingMaskIntoConstraints = False
                    width_constraint = label.widthAnchor.constraintEqualToConstant(available)
                    self.readerWidth = width_constraint
                    label.centerXAnchor.constraintEqualToAnchor(window.centerXAnchor).active = True
                    label.centerYAnchor.constraintEqualToAnchor(self.centerYAnchor).active = True
                    label.heightAnchor.constraintEqualToAnchor(self.heightAnchor).active = True
                    width_constraint.active = True
                else:
                    self.readerWidth.constant = available
        _title_view_type = LogisticsReaderTitle
    view = _title_view_type.alloc().initWithFrame(CGRect((0, 0), (width, 32)))
    view.readerActions = actions
    view.readerWidth = None
    label = ObjCClass('UILabel').alloc().initWithFrame(view.bounds)
    label.tag = 7311
    label.text = label.accessibilityLabel = text
    label.font = ObjCClass('UIFont').systemFontOfSize(17, weight=.6)
    label.textAlignment, label.lineBreakMode = 1, 5
    from .appearance import apple_color
    label.textColor = apple_color('text')
    view.addSubview(label)
    return view, label


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
            notify_viewport(container)
        finally:
            container._logistics_layout_active = False
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
