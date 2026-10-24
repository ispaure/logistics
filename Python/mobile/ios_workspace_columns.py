"""Keep Workspaces' retained sidebar outside UIKit's folder transition area."""
from types import SimpleNamespace

_controller_class = None


def columns_controller():
    global _controller_class
    if _controller_class is None:
        from rubicon.objc import ObjCClass, objc_method, objc_property, send_super

        class LogisticsWorkspaceColumns(ObjCClass('UIViewController')):
            owner = objc_property(object, weak=True)

            @objc_method
            def viewDidLayoutSubviews(self) -> None:
                send_super(__class__, self, 'viewDidLayoutSubviews')
                if self.owner is not None:
                    self.owner.layout()

        _controller_class = LogisticsWorkspaceColumns
    return _controller_class


class WorkspaceColumns:
    def __init__(self, workspace, master):
        from toga_iOS.container import ControlledContainer
        self.workspace, self.master = workspace, master
        self.app = workspace.app
        self.adapter = self.app.native_host.adapter
        self.index = self.app.native_host.destinations.index('files')
        self.navigation = self.adapter.navigation[self.index]
        self.navigation_autoresizing = self.navigation.view.autoresizingMask
        self.controller = columns_controller().alloc().init()
        self.controller.owner = self
        self.controller.view.autoresizingMask = 18  # flexible width and height
        from rubicon.objc import ObjCClass
        item = self.navigation.tabBarItem
        self.controller.tabBarItem = ObjCClass('UITabBarItem').alloc().initWithTitle(
            item.title, image=item.image, tag=self.index)
        self.controller.tabBarItem.accessibilityLabel = item.accessibilityLabel
        self.sidebar = ControlledContainer(on_refresh=lambda value: None,
                                          on_native_layout=self.layout_sidebar)
        from .file_drawer import detach
        detach(master.main)
        master.main.style.flex = 1
        del master.main.style.width
        del master.main.style.height
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.sidebar_box = toga.Box(children=[master.main],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        self.sidebar_box.app, self.sidebar_box.window = self.app, self.app.main_window
        self.sidebar.content = self.sidebar_box._impl
        from .appearance import apple_color
        self.sidebar.native.backgroundColor = apple_color('window')
        self.controller.view.backgroundColor = apple_color('window')
        # Replace the tab's controller before reparenting navigation. Modern
        # UIKit tabs retain their child association even after an empty list.
        self.root_container = self.adapter.impl.sub_containers[self.index]
        self.old_root_layout = self.root_container.on_native_layout
        self.root_container.controller = self.controller
        self.root_container.on_native_layout = self.layout_root
        self.adapter.impl.refresh_tabs()
        for child in (self.sidebar.controller, self.navigation):
            if child.parentViewController is not None:
                child.willMoveToParentViewController(None)
                child.view.removeFromSuperview()
                child.removeFromParentViewController()
            self.controller.addChildViewController(child)
            child.view.autoresizingMask = 0
            self.controller.view.addSubview(child.view)
            child.didMoveToParentViewController(self.controller)
        self.app.native_host.activate(self.app.native_host.state.destination)
        self.layout()

    def layout_sidebar(self, container):
        # navigationController can resolve to the window's outer navigation
        # controller through the tab hierarchy. This column owns its own frame.
        safe = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = safe.top, safe.bottom
        container.left_inset, container.right_inset = safe.left, safe.right
        from .folder_hub_ui import reflow_folder_notice
        reflow_folder_notice(self.app, float(container.native.bounds.size.width - safe.left - safe.right) - 24)
        if container.content is not None:
            container.content.interface.refresh()
        from .appearance import reserve_navigation
        reserve_navigation(self.app, view=self.sidebar_box)

    def layout_root(self, container):
        # The tab exposes the wrapper, but its retained root content belongs to
        # the inner navigation controller. Never temporarily change controller:
        # Toga can synchronously refresh the tab list during content layout.
        container.native.frame = self.navigation.view.bounds
        safe = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = safe.top, safe.bottom
        container.left_inset, container.right_inset = safe.left, safe.right
        if container.content is not None:
            container.content.interface.refresh()

    def layout(self):
        from rubicon.objc import CGRect
        from .pane_layout import panes
        from dataclasses import replace
        from .fold_layout import division, has_fold
        native = self.controller.view
        parent = native.superview
        parent = parent() if callable(parent) else parent
        if parent is not None and parent.bounds.size.width > 0 and parent.bounds.size.height > 0:
            # UIKit can leave a nonzero keyboard-era frame on a custom tab
            # controller. The actual native parent owns its final allocation.
            native.frame = parent.bounds
        bounds, safe = native.bounds, native.safeAreaInsets
        width = float(bounds.size.width - safe.left - safe.right)
        height = float(bounds.size.height)
        if width <= 0 or height <= 0:
            return
        # Fold queries use the full owning container, before allocating panes.
        impl = type('ColumnsImpl', (), {'__module__': 'toga_iOS.container'})()
        impl.native = native
        widget = SimpleNamespace(_impl=impl)
        fold = division(self.app, widget)
        foldable = has_fold(self.app, widget)
        if fold is not None:
            fold = replace(fold, x=fold.x - float(safe.left))
        allocation = panes(width, height, fold=fold, browser_priority=foldable,
                           leading_fraction=.4 if foldable else None)
        if allocation.axis == 'row':
            frames = (CGRect((safe.left, 0), (allocation.leading, height)),
                      CGRect((safe.left + allocation.leading + allocation.gap, 0),
                             (allocation.trailing, height)))
        else:
            frames = (CGRect((safe.left, 0), (width, allocation.leading)),
                      CGRect((safe.left, allocation.leading + allocation.gap),
                             (width, allocation.trailing)))
        targets = tuple((float(frame.origin.x), float(frame.origin.y),
                         float(frame.size.width), float(frame.size.height)) for frame in frames)
        if targets == getattr(self, '_layout_targets', None):
            return
        previous = getattr(self, '_layout_targets', None)
        self._layout_targets = targets
        children = (self.sidebar.controller, self.navigation)
        from ctypes import CDLL, c_bool
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        animate = previous is not None and native.window is not None and not reduced()
        if animate:
            for child in children:
                layer = child.view.layer.presentationLayer()
                if layer is not None:
                    child.view.frame = layer.frame

        def apply():
            for child, frame in zip(children, frames):
                child.view.frame = frame
            self.layout_sidebar(self.sidebar)
            # Toga commits constraints, so lay out descendants in this same
            # animation transaction rather than reading stale native frames.
            for child in children:
                child.view.layoutIfNeeded()

        if animate:
            from rubicon.objc import ObjCClass, Block
            self.animation = Block(apply, None)
            ObjCClass('UIView').animateWithDuration(.28, delay=0, options=(1 << 2) | (1 << 1),
                animations=self.animation, completion=None)
        else:
            apply()

    def close(self):
        self.adapter.controller.setViewControllers([], animated=False)
        for child in (self.navigation, self.sidebar.controller):
            child.willMoveToParentViewController(None)
            child.view.removeFromSuperview()
            child.removeFromParentViewController()
        self.navigation.view.autoresizingMask = self.navigation_autoresizing
        from .file_drawer import detach
        detach(self.master.main)
        self.sidebar.content = None
        self.master.row.add(self.master.main)
        self.sidebar_box.window, self.sidebar_box.app = None, None
        self.root_container.controller = self.navigation
        self.root_container.on_native_layout = self.old_root_layout
        self.adapter.impl.refresh_tabs()
        self.app.native_host.activate(self.app.native_host.state.destination)
        self.controller.owner = None


def sync(workspace):
    """Wrap only wide Apple Workspaces; resizing never changes route history."""
    if not type(workspace.app._impl).__module__.startswith('toga_iOS.'):
        return
    adapter = workspace.app.native_host.adapter
    if adapter is None or not hasattr(adapter, 'navigation'):
        return
    root = workspace.app.routes.roots['files']
    view = root.children[0] if root.children else None
    master = getattr(view, '_workspace_frame', None)
    active = getattr(workspace, 'file_columns', None)
    from .fold_layout import division
    wide = (workspace.content_width('files', margin=0) >= 640 or
            division(workspace.app, workspace.app.main_window) is not None)
    if not wide or master is None:
        if active is not None:
            active.close()
            workspace.file_columns = None
        return
    if active is None:
        workspace.file_columns = WorkspaceColumns(workspace, master)
    else:
        active.layout()
