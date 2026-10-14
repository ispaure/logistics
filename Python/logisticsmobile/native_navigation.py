"""Native navigation adapters for the pinned Toga 0.5.7 mobile hosts.

Backend access stays here. Neither feature controllers nor shared Python state
need to know about UIKit/Java containment, insets or navigation bar placement.
"""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from .navigation import DESTINATIONS, NavigationState

LABELS = ('Home', 'Files', 'Documents', 'Settings')


class NativeNavigationHost:
    def __init__(self, *, state=None, on_select=None, prefer_sidebar=True):
        self.state = state or NavigationState()
        self.on_select = on_select
        self.prefer_sidebar = prefer_sidebar
        self.changing = False
        self.bodies = {key: toga.Box(style=Pack(direction=COLUMN, flex=1)) for key in DESTINATIONS}
        self.root = toga.OptionContainer(content=[(label, self.bodies[key])
            for key, label in zip(DESTINATIONS, LABELS)], on_select=self._selected,
            style=Pack(flex=1))
        self.adapter = None
        self.window = None
        self.activate(self.state.destination)

    def _selected(self, widget, **kwargs):
        if self.changing or widget.current_tab is None:
            return
        destination = DESTINATIONS[widget.current_tab.index]
        if self.on_select is not None and self.on_select(destination) is False:
            self.activate(self.state.destination)
            return
        self.state.select(destination)

    def activate(self, destination):
        if destination not in DESTINATIONS:
            raise ValueError('Unknown mobile destination.')
        self.changing = True
        try:
            self.root.current_tab = DESTINATIONS.index(destination)
            self.state.select(destination)
        finally:
            self.changing = False

    def install(self, window):
        if self.window is not None:
            raise RuntimeError('Navigation host is already installed.')
        self.window = window
        backend = type(self.root._impl).__module__
        if backend.startswith('toga_iOS.'):
            self.adapter = AppleNavigation(self, window)
        elif backend.startswith('toga_android.'):
            self.adapter = AndroidNavigation(self, window)

    def uninstall(self):
        if self.adapter is not None:
            self.adapter.dispose()
            self.adapter = None
        self.window = None

    def dispose(self):
        self.uninstall()
        if type(self.root._impl).__module__.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass
            impl = self.root._impl
            ObjCClass('NSObject').cancelPreviousPerformRequestsWithTarget(impl.native_controller)
            impl.native_controller.delegate = None
            impl.native_controller.setViewControllers([], animated=False)
            for container in impl.sub_containers:
                container.controller.view = ObjCClass('UIView').alloc().init()
        self.on_select = None

    def diagnostics(self):
        return self.adapter.diagnostics() if self.adapter else {'platform': 'host'}


class AppleNavigation:
    def __init__(self, host, window):
        from rubicon.objc import ObjCClass, SEL
        self.host, self.window = host, window
        self.impl = host.root._impl
        self.controller = self.impl.native_controller
        self.parent = window._impl.container.content_controller
        self.old_layout = window._impl.container.on_native_layout
        self.old_get_size = window._impl.get_size
        self.outer_navigation = window._impl.native.rootViewController
        self.old_bar_hidden = bool(self.outer_navigation.isNavigationBarHidden())
        self.outer_navigation.setNavigationBarHidden(True, animated=False)
        self.containers = []
        self.panes = []
        self.navigation = []
        # Toga normally attaches only the controller's view. Managed containment
        # is required for native safe areas, bars and appearance callbacks.
        if self.controller.parentViewController != self.parent:
            self.parent.addChildViewController(self.controller)
            self.controller.didMoveToParentViewController(self.parent)
        self.controller.setViewControllers([], animated=False)
        symbols = ('house', 'folder', 'doc.on.doc', 'gearshape')
        for label, symbol, container in zip(LABELS, symbols, self.impl.sub_containers):
            content = container.controller
            content.title = label
            navigation = ObjCClass('UINavigationController').alloc().initWithRootViewController(content)
            navigation.tabBarItem = content.tabBarItem
            navigation.tabBarItem.image = ObjCClass('UIImage').systemImageNamed(symbol)
            container.controller = navigation
            container.on_native_layout = self.layout_content
            self.containers.append((container, content))
            self.navigation.append(navigation)
        self.impl.refresh_tabs()
        self.sidebar_available = bool(self.controller.respondsToSelector(SEL('setMode:')))
        self.sidebar_used = self.sidebar_available and host.prefer_sidebar
        if self.sidebar_used:
            self.controller.setMode(2)  # UITabBarController.Mode.tabSidebar
        window._impl.container.on_native_layout = self.layout_window
        window._impl.get_size = self.get_size
        self.layout_window(window._impl.container)

    def get_size(self):
        from toga.types import Size
        bounds = self.window._impl.native.bounds.size
        return Size(int(bounds.width), int(bounds.height))

    @staticmethod
    def layout_content(container):
        insets = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = insets.top, insets.bottom
        container.left_inset, container.right_inset = insets.left, insets.right
        if container.content is not None:
            container.content.interface.refresh()

    def layout_window(self, container):
        # Status-bar frame height is not an inset on Duo's vertical bar axis.
        insets = container.native.safeAreaInsets
        container.top_inset, container.bottom_inset = insets.top, insets.bottom
        container.left_inset, container.right_inset = insets.left, insets.right
        self.window._impl.notify_resize(container)

    def push(self, destination, widget, title):
        from toga_iOS.container import ControlledContainer
        container = ControlledContainer(on_refresh=lambda value: None,
                                        on_native_layout=self.layout_content)
        widget.app = self.window.app
        widget.window = self.window
        container.content = widget._impl
        container.controller.title = title
        self.panes.append(container)
        self.navigation[DESTINATIONS.index(destination)].pushViewController(container.controller, animated=False)
        return container

    def pop(self, destination):
        return self.navigation[DESTINATIONS.index(destination)].popViewControllerAnimated(False)

    def prove_split(self, leading, detail):
        from rubicon.objc import ObjCClass
        from toga_iOS.container import ControlledContainer
        split = ObjCClass('UISplitViewController').alloc().initWithStyle(1)  # doubleColumn
        containers = []
        for column, widget in zip((0, 2), (leading, detail)):
            container = ControlledContainer(on_refresh=lambda value: None,
                                            on_native_layout=self.layout_content)
            widget.app = self.window.app
            widget.window = self.window
            container.content = widget._impl
            containers.append(container)
            split.setViewController(container.controller, forColumn=column)
        split.preferredDisplayMode = 2  # oneBesideSecondary
        self.panes.extend(containers)
        self.split = split
        # Exercise as a full-screen native presentation, avoiding unsupported
        # split-controller nesting inside an OptionContainer tab.
        split.modalPresentationStyle = 0  # fullScreen
        self.controller.presentViewController(split, animated=False, completion=None)
        return containers

    def diagnostics(self):
        from rubicon.objc import ObjCClass
        bounds = self.window._impl.native.bounds.size
        bar = self.controller.tabBar.frame.size
        application = ObjCClass('UIApplication').sharedApplication
        if callable(application):
            application = application()
        return dict(platform='ios', native_tabs=str(self.controller.objc_class.name),
                    contained=self.controller.parentViewController == self.parent,
                    sidebar_available=self.sidebar_available,
                    sidebar_used=self.sidebar_used,
                    width=float(bounds.width), height=float(bounds.height),
                    bar_axis='vertical' if bar.height > bar.width else 'horizontal',
                    application_active=int(application.applicationState) == 0,
                    main_thread=bool(ObjCClass('NSThread').isMainThread))

    def dispose(self):
        if getattr(self, 'split', None):
            self.split.dismissViewControllerAnimated(False, completion=None)
        for container in self.panes:
            from rubicon.objc import ObjCClass
            container.controller.view = ObjCClass('UIView').alloc().init()
            container.on_native_layout = None
            if container.content is not None:
                container.content.interface.window = None
                container.content.interface.app = None
            container.content = None
        self.panes.clear()
        self.window._impl.container.on_native_layout = self.old_layout
        self.window._impl.get_size = self.old_get_size
        self.outer_navigation.setNavigationBarHidden(self.old_bar_hidden, animated=False)
        for container, content in self.containers:
            container.controller = content
            container.on_native_layout = None
        self.impl.refresh_tabs()
        self.controller.willMoveToParentViewController(None)
        self.controller.removeFromParentViewController()


class AndroidNavigation:
    def __init__(self, host, window):
        from android import R
        from com.google.android.material.navigation import NavigationBarView
        from java import dynamic_proxy
        import weakref
        self.host, self.window = host, window
        self.impl = host.root._impl
        self.bottom = self.impl.native_navigationview
        self.rail = None
        self.old_resize = self.impl.resize_tab_content
        self.old_window_resize = window.on_resize
        self.native_window = self.impl._native_activity.getWindow()
        self.old_soft_input = self.native_window.getAttributes().softInputMode
        from android.view import WindowManager
        self.native_window.setSoftInputMode((self.old_soft_input & ~WindowManager.LayoutParams.SOFT_INPUT_MASK_ADJUST)
                                           | WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        self.layout_events = 0
        self.mode = 'bottom'
        self.old_listener = self.impl.onItemSelectedListener
        class SelectionListener(dynamic_proxy(NavigationBarView.OnItemSelectedListener)):
            def __init__(self, adapter):
                super().__init__()
                self.adapter = weakref.ref(adapter)

            def onNavigationItemSelected(self, item):
                owner = self.adapter()
                if owner is None:
                    return False
                index = next((index for index, option in enumerate(owner.impl.options)
                              if option.menu_item == item), None)
                if index is None:
                    return False
                destination = DESTINATIONS[index]
                if owner.host.on_select and owner.host.on_select(destination) is False:
                    return False
                # Material calls its listener before checking the new item.
                # Reading Toga.current_tab inside that callback sees the old tab.
                owner.host.changing = True
                try:
                    owner.host.state.select(destination)
                    owner.impl.set_current_tab_index(index, programmatic=False)
                finally:
                    owner.host.changing = False
                return True

        self.impl.onItemSelectedListener = SelectionListener(self)
        self.bottom.setOnItemSelectedListener(self.impl.onItemSelectedListener)
        self.impl.resize_tab_content = self.resize_content
        window.on_resize = self.window_resized
        resources = (None, R.drawable.ic_menu_agenda,
                     R.drawable.ic_menu_edit, R.drawable.ic_menu_preferences)
        self.bottom.getMenu().clear()
        for index, (option, resource) in enumerate(zip(self.impl.options, resources)):
            option.menu_item = self.bottom.getMenu().add(0, index + 1, index, option.text)
            option.menu_item.setIcon(resource if resource is not None else self.home_icon())
        self.impl.set_current_tab_index(DESTINATIONS.index(host.state.destination))
        self.window_resized(window)

    @staticmethod
    def home_icon():
        from android.graphics import Path, Paint
        from android.graphics.drawable import ShapeDrawable
        from android.graphics.drawable.shapes import PathShape
        path = Path()
        path.moveTo(2, 11)
        path.lineTo(12, 3)
        path.lineTo(22, 11)
        path.moveTo(5, 9)
        for x, y in ((5, 21), (9, 21), (9, 14), (15, 14), (15, 21), (19, 21), (19, 9)):
            path.lineTo(x, y)
        drawable = ShapeDrawable(PathShape(path, 24, 24))
        drawable.getPaint().setStyle(Paint.Style.STROKE)
        drawable.getPaint().setStrokeWidth(1.6)
        drawable.getPaint().setAntiAlias(True)
        drawable.setIntrinsicWidth(24)
        drawable.setIntrinsicHeight(24)
        return drawable

    def window_resized(self, window, **kwargs):
        self.layout_events += 1
        if self.old_window_resize:
            self.old_window_resize(window)
        self.update_keyboard_inset()
        width = self.impl.scale_out(self.impl.native.getWidth())
        if width > 0:
            self.set_mode('rail' if width >= 600 else 'bottom')

    def update_keyboard_inset(self):
        from android.graphics import Rect
        visible, own = Rect(), Rect()
        self.impl.native.getWindowVisibleDisplayFrame(visible)
        self.impl.native.getGlobalVisibleRect(own)
        overlap = max(0, own.bottom - visible.bottom)
        if self.impl.native.getPaddingBottom() != overlap:
            self.impl.native.setPadding(0, 0, 0, overlap)

    def set_mode(self, mode):
        from android.widget import LinearLayout
        from com.google.android.material.navigationrail import NavigationRailView
        from android.view import ContextThemeWrapper
        from com.google.android.material import R as MaterialR
        if mode == self.mode:
            return
        if mode not in {'rail', 'bottom'}:
            raise ValueError('Invalid Android navigation presentation.')
        old = self.impl.native_navigationview
        old.setOnItemSelectedListener(None)
        self.impl.native.removeView(old)
        if mode == 'rail':
            if self.rail is None:
                context = ContextThemeWrapper(self.impl._native_activity,
                    MaterialR.style.Theme_MaterialComponents_DayNight)
                self.rail = NavigationRailView(context)
                self.rail.setLabelVisibilityMode(1)  # LABEL_VISIBILITY_LABELED
                for index, label in enumerate(LABELS):
                    self.rail.getMenu().add(0, index + 1, index, label).setIcon(
                        self.bottom.getMenu().getItem(index).getIcon())
            view = self.rail
            self.impl.native.setOrientation(LinearLayout.HORIZONTAL)
            self.impl.native_content.setLayoutParams(LinearLayout.LayoutParams(0, -1, 1))
            self.impl.native.addView(view, 0, LinearLayout.LayoutParams(-2, -1))
        else:
            view = self.bottom
            self.impl.native.setOrientation(LinearLayout.VERTICAL)
            self.impl.native_content.setLayoutParams(LinearLayout.LayoutParams(-1, 0, 1))
            self.impl.native.addView(view, LinearLayout.LayoutParams(-1, -2))
        self.mode = mode
        self.impl.native_navigationview = view
        for index, option in enumerate(self.impl.options):
            option.menu_item = view.getMenu().getItem(index)
        self.impl.set_current_tab_index(DESTINATIONS.index(self.host.state.destination))
        view.setOnItemSelectedListener(self.impl.onItemSelectedListener)
        self.impl.native.requestLayout()

    def resize_content(self):
        native = self.impl.native_content
        width, height = native.getWidth(), native.getHeight()
        if width and height:
            self.impl.resize_content(width, height)

    def diagnostics(self):
        from android.os import Looper
        view = self.impl.native_navigationview
        return dict(platform='android', native_tabs=str(view.getClass().getName()),
                    mode=self.mode, width=self.impl.scale_out(self.impl.native.getWidth()),
                    height=self.impl.scale_out(self.impl.native.getHeight()),
                    content_height=self.impl.scale_out(self.impl.native_content.getHeight()),
                    keyboard_inset=self.impl.scale_out(self.impl.native.getPaddingBottom()),
                    layout_events=self.layout_events,
                    main_thread=Looper.myLooper() == Looper.getMainLooper())

    def dispose(self):
        self.set_mode('bottom')
        self.impl.onItemSelectedListener = self.old_listener
        self.bottom.setOnItemSelectedListener(self.old_listener)
        self.impl.resize_tab_content = self.old_resize
        self.window.on_resize = self.old_window_resize
        self.native_window.setSoftInputMode(self.old_soft_input)
        self.impl.native.setPadding(0, 0, 0, 0)
        if self.rail is not None:
            self.rail.setOnItemSelectedListener(None)
