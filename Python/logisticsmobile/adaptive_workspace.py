"""Measured-window Documents list/detail presentation over retained sessions."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .navigation import DESTINATIONS

_delegate_class = None


def workspace_delegate():
    global _delegate_class
    if _delegate_class is None:
        from rubicon.objc import ObjCClass, objc_method, objc_property

        class LogisticsWorkspaceDelegate(ObjCClass('NSObject')):
            owner = objc_property(object, weak=True)

            @objc_method
            def navigationController_didShowViewController_animated_(self, navigation, controller, animated: bool) -> None:
                if self.owner is not None:
                    self.owner.native_shown(controller, animated=animated)

            @objc_method
            def splitViewController_topColumnForCollapsingToProposedTopColumn_(self, split, proposed: int) -> int:
                return 2 if self.owner is not None and self.owner.in_detail else 0

        _delegate_class = LogisticsWorkspaceDelegate
    return _delegate_class


class AdaptiveWorkspace:
    def __init__(self, app):
        self.app = app
        self.row = toga.Box(style=Pack(direction=ROW, flex=1))
        self.placeholder = toga.Box(children=[toga.Label('Choose an open document')],
                                    style=Pack(direction=COLUMN, flex=1, margin=12))
        self.wide = False
        self.layout_width = 0
        self.split = None
        self.detail_routes = []
        self.in_detail = False
        self.changing = False

    def install(self):
        adapter = self.app.native_host.adapter
        if adapter is None or not hasattr(adapter, 'navigation'):
            self.render()
            return
        from rubicon.objc import ObjCClass
        from toga_iOS.container import ControlledContainer
        index = DESTINATIONS.index('documents')
        self.primary = adapter.navigation[index]
        self.delegate = workspace_delegate().alloc().init()
        self.delegate.owner = self
        self.primary.delegate = self.delegate
        self.split = ObjCClass('UISplitViewController').alloc().initWithStyle(1)
        self.split.delegate = self.delegate
        self.split.preferredDisplayMode = 2  # oneBesideSecondary, native collapse
        self.split.minimumPrimaryColumnWidth = 260
        self.split.maximumPrimaryColumnWidth = 320
        container = ControlledContainer(on_refresh=lambda value: None,
                                        on_native_layout=adapter.layout_content)
        self.placeholder.app, self.placeholder.window = self.app, self.app.main_window
        container.content = self.placeholder._impl
        self.placeholder_container = container
        self.secondary = ObjCClass('UINavigationController').alloc().initWithRootViewController(container.controller)
        self.secondary.delegate = self.delegate
        self.split.tabBarItem = self.primary.tabBarItem
        adapter.controller.setViewControllers([], animated=False)
        self.split.setViewController(self.primary, forColumn=0)
        self.split.setViewController(self.secondary, forColumn=2)
        adapter.impl.sub_containers[index].controller = self.split
        adapter.impl.refresh_tabs()
        self.app.native_host.activate(self.app.native_host.state.destination)

    def uninstall(self):
        if self.split is None:
            return
        adapter = self.app.native_host.adapter
        from rubicon.objc import ObjCClass
        self.split.delegate = None
        self.primary.delegate = None
        self.secondary.delegate = None
        self.changing = True
        self.secondary.setViewControllers([self.placeholder_container.controller], animated=False)
        for _, _, container in self.detail_routes:
            adapter.release_pane(container)
        self.detail_routes.clear()
        adapter.controller.setViewControllers([], animated=False)
        self.split.setViewController(None, forColumn=0)
        self.split.setViewController(None, forColumn=2)
        adapter.impl.sub_containers[DESTINATIONS.index('documents')].controller = self.primary
        adapter.impl.refresh_tabs()
        self.placeholder_container.controller.view = ObjCClass('UIView').alloc().init()
        self.placeholder_container.content = None
        self.placeholder.window, self.placeholder.app = None, None
        self.split = None
        self.changing = False

    def present(self, view, *, route=None, title=''):
        from toga_iOS.container import ControlledContainer
        adapter = self.app.native_host.adapter
        if self.detail_routes and self.detail_routes[-1][0].startswith('file-loading:'):
            self.trim_details(len(self.detail_routes) - 1)
        route = route or (self.detail_routes[-1][0] if self.detail_routes else 'detail')
        existing = next((index for index, item in enumerate(self.detail_routes) if item[0] == route), None)
        self.changing = True
        try:
            if existing is not None:
                retained = self.detail_routes[:existing + 1]
                self.secondary.setViewControllers([item[2].controller for item in retained], animated=False)
                for _, _, container in self.detail_routes[existing + 1:]:
                    adapter.release_pane(container)
                self.detail_routes = retained
                panel = retained[-1][1]
                if list(panel.children) != [view]:
                    for child in list(panel.children):
                        panel.remove(child)
                    panel.add(view)
            else:
                panel = toga.Box(children=[view], style=Pack(direction=COLUMN, flex=1))
                container = ControlledContainer(on_refresh=lambda value: None,
                                                on_native_layout=adapter.layout_content)
                panel.app, panel.window = self.app, self.app.main_window
                container.content = panel._impl
                container.controller.title = title
                adapter.panes.append(container)
                self.detail_routes.append((route, panel, container))
                self.secondary.setViewControllers([item[2].controller for item in self.detail_routes], animated=False)
            self.detail_routes[-1][2].controller.title = title
            self.app.native_host.state.routes['documents'] = [item[0] for item in self.detail_routes]
            self.app.body = panel
            self.in_detail = True
            self.split.showColumn(2)
        finally:
            self.changing = False

    def update_title(self, view, title):
        if (self.split is not None and self.detail_routes
                and view in self.detail_routes[-1][1].children):
            self.detail_routes[-1][2].controller.title = title

    def show_list(self):
        if self.split is not None:
            self.in_detail = False
            self.split.showColumn(0)
            self.app.body = self.app.routes.roots['documents']

    def clear_details(self):
        self.trim_details(0)

    def trim_details(self, count):
        """Retire secondary panels while retaining the earlier document views."""
        if self.split is None:
            return
        self.changing = True
        try:
            retained = self.detail_routes[:count]
            self.secondary.setViewControllers([item[2].controller for item in retained]
                or [self.placeholder_container.controller], animated=False)
            for _, _, container in self.detail_routes[count:]:
                self.app.native_host.adapter.release_pane(container)
            self.detail_routes = retained
            self.app.native_host.state.routes['documents'] = [item[0] for item in retained]
        finally:
            self.changing = False

    def native_shown(self, controller, *, animated=False):
        if self.changing or self.split is None:
            return
        shown = next((index for index, item in enumerate(self.detail_routes) if item[2].controller == controller), None)
        if shown is not None:
            if shown < len(self.detail_routes) - 1:
                self.app.mark_navigation()
            for _, _, container in self.detail_routes[shown + 1:]:
                self.app.native_host.adapter.release_pane(container)
            self.detail_routes = self.detail_routes[:shown + 1]
            self.app.native_host.state.routes['documents'] = [item[0] for item in self.detail_routes]
            if self.app.native_host.state.destination == 'documents':
                self.app.body = self.detail_routes[-1][1]
                self.app.route_changed(self.app.body)
            self.in_detail = True
        elif controller == self.app.native_host.adapter.containers[DESTINATIONS.index('documents')][1]:
            # UIKit also reports the primary root while presenting/collapsing
            # the secondary column. Explicit show_list already changes this
            # state; only an animated Back should retire a visible detail.
            if self.in_detail and not animated:
                return
            if animated and self.in_detail and self.app.native_host.state.destination == 'documents':
                self.app.mark_navigation()
            self.in_detail = False
            self.app.native_host.state.routes['documents'] = []
            if self.app.native_host.state.destination == 'documents':
                self.app.body = self.app.routes.roots['documents']
                self.app.route_changed(self.app.body)

    def render(self):
        host, routes = self.app.native_host, self.app.routes
        if host.adapter is None or not hasattr(host.adapter, 'mode'):
            return
        width = host.adapter.diagnostics()['width']
        wide = width >= 840
        self.layout_width = width
        outer = host.bodies['documents']
        leading = routes.roots['documents']
        detail = routes.body('documents') if routes.screens['documents'] else self.placeholder
        self.wide = wide
        if wide and list(outer.children) == [self.row] and list(self.row.children) == [leading, detail]:
            return
        if not wide and not self.row.children and list(outer.children) == [routes.body('documents')]:
            return
        for child in list(outer.children):
            outer.remove(child)
        for child in list(self.row.children):
            self.row.remove(child)
        if wide:
            leading.style.width, leading.style.flex = 280, 0
            self.row.add(leading, detail)
            outer.add(self.row)
        else:
            leading.style.width, leading.style.flex = None, 1
            outer.add(routes.body('documents'))

    def diagnostics(self):
        if self.split is not None:
            collapsed = self.split.isCollapsed
            return dict(layout='compact' if bool(collapsed() if callable(collapsed) else collapsed) else 'list-detail',
                        width=self.app.main_window._impl.native.bounds.size.width,
                        detail_visible=self.in_detail)
        return dict(layout='list-detail' if self.wide else 'compact', width=self.layout_width)
