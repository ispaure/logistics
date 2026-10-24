"""Destination-owned drawers and adaptive document panes over native routes.

The native tab and Back stacks stay authoritative. A pane moves existing widget
owners rather than copying editor buffers or mounting a widget twice.
"""
import weakref

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .appearance import list_button
from .adaptive_workspace import AdaptiveWorkspace
from .file_drawer import FileDrawer, detach
from .navigation import DESTINATION_ITEMS
from .workspace_policy import WorkspaceSelection, session_view

DESTINATION_LABELS = {key: label for key, label, *_ in DESTINATION_ITEMS}


def menu_button(callback, label='Browse files'):
    button = toga.Button('☰', on_press=callback, style=Pack(width=52, height=52))
    button._workspace_menu_label = label
    if type(button._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass, SEL
        button.text = ''
        button._impl.native.setImage(ObjCClass('UIImage').systemImageNamed('line.3.horizontal'), forState=0)
        native = button._impl.native
        # A scroll starting on this control must not open a drawer on touch-down.
        native.removeTarget(native, action=SEL('onPress:'), forControlEvents=1)
        native.addTarget(native, action=SEL('onPress:'), forControlEvents=1 << 6)
        from .appearance import paint_surface
        button._impl._native_glass_control = True
        paint_surface(button._impl, 0)
        symbol = ObjCClass('UIImageSymbolConfiguration').configurationWithPointSize(22, weight=5)
        native.setPreferredSymbolConfiguration(symbol, forImageInState=0)
        native.accessibilityLabel = label
    elif type(button._impl).__module__.startswith('toga_android.'):
        button._impl.native.setContentDescription(label)
    return button


def mount_native_menu(app, menu, destination):
    """All workspace menus occupy the Documents navigation-bar slot."""
    from rubicon.objc import ObjCClass, SEL
    adapter = app.native_host.adapter
    controller = adapter.navigation[app.native_host.destinations.index(destination)].topViewController
    detach(menu)
    menu.app, menu.window = app, app.main_window
    if not hasattr(menu, '_native_workspace_item'):
        menu._native_workspace_item = ObjCClass('UIBarButtonItem').alloc().initWithImage(
            ObjCClass('UIImage').systemImageNamed('line.3.horizontal'), style=0,
            target=menu._impl.native, action=SEL('onPress:'))
        menu._native_workspace_item.accessibilityLabel = getattr(menu, '_workspace_menu_label', 'Browse files')
        menu._native_workspace_item.title = menu._native_workspace_item.accessibilityLabel
    item = controller.navigationItem
    item.leftItemsSupplementBackButton = True
    item.leftBarButtonItem = menu._native_workspace_item
    return menu._native_workspace_item


def sync_reader_toolbar(app, view, destination=None):
    """Share UIKit's title bar rather than spending a second row on reading."""
    app.refresh_reader_exit(view)
    if not app.routes.apple:
        if type(app._impl).__module__.startswith('toga_android.'):
            from .android_reader_chrome import sync
            sync(app, view, destination or app.native_host.state.destination)
        return
    from .ios_toolbar import mount_actions, mount_leading, vertical_edge, clear_actions
    adapter = app.native_host.adapter
    destination = destination or app.native_host.state.destination
    controller = adapter.navigation[app.native_host.destinations.index(destination)].topViewController
    owned = getattr(app, '_reader_toolbar_controllers', None)
    if owned is None:
        owned = app._reader_toolbar_controllers = set()
    key = controller.ptr.value
    controls = getattr(view, '_native_reader_buttons', None)
    if controls is None:
        # Tabs retain their controllers. Clear reader-owned chrome even when a
        # different tab was the most recent reader toolbar to be rendered.
        if key in owned:
            clear_actions(controller.navigationItem)
            controller.navigationItem.prompt = None
            controller.navigationItem.titleView = None
            owned.discard(key)
            if getattr(app, '_reader_toolbar_controller', None) == controller:
                app._reader_toolbar_controller = None
                app._reader_toolbar_state = None
                app._reader_toolbar_prompt = None
            if getattr(app, '_reader_title_controller', None) == controller:
                app._reader_title_controller = None
                app._reader_title_state = None
        return
    toolbar = view._native_reader_toolbar
    detach(toolbar)
    for control in getattr(view, '_native_reader_hidden', ()):
        detach(control)
    from .reader_chrome import reader_buttons
    buttons = [] if getattr(view, '_reader_fullscreen', False) else reader_buttons(app, view)
    state = (controller.ptr.value, tuple(id(button) for button in buttons), vertical_edge(controller))
    for button in buttons:
        detach(button)
        button.app, button.window = app, app.main_window
    mount_actions(controller, view, buttons)
    app._reader_toolbar_state = state
    status = getattr(view, '_native_reader_status', None)
    text = status.text if status is not None else ''
    prompt = text if text.lower().startswith(('save failed', 'cannot ', 'unsaved changes:',
        'book import failed', 'could not ')) else None
    if getattr(app, '_reader_toolbar_prompt', None) != (controller.ptr.value, prompt):
        controller.navigationItem.prompt = prompt
        app._reader_toolbar_prompt = (controller.ptr.value, prompt)
    owned.add(key)
    app._reader_toolbar_controller = controller
    title = getattr(view, '_native_reader_title', None)
    text = str(title() if callable(title) else title or controller.navigationItem.title or '').replace('\n', ' ')
    # UIKit sizes the title inside the actual container, including vertical bars
    # and split panes; don't reserve horizontal gutters for now-vertical actions.
    controller.navigationItem.titleView = None
    controller.navigationItem.title = text
    app._reader_title_controller = controller
    close = getattr(view, '_reader_close_button', None)
    if close is not None:
        detach(close)
        close.app, close.window = app, app.main_window
        frame = getattr(view, '_workspace_frame', None)
        menu = frame.menu if frame is not None else getattr(view, '_workspace_menu_button', None)
        leading = [close]
        if menu is not None:
            detach(menu)
            menu.app, menu.window = app, app.main_window
            leading.append(menu)
        mount_leading(controller, leading, replaces_back=True)
        close._native_reader_close_item = close._ios_action_item


class WorkspaceNavigation(AdaptiveWorkspace):
    def __init__(self, app):
        super().__init__(app)
        self.frames = weakref.WeakSet()
        self.browsers = {}
        self.menu_open = dict(files=False, documents=False)
        self.selection = WorkspaceSelection()
        self.rendering = False
        self.last_layout = None

    @property
    def pinned(self):
        return self.selection.pinned

    @pinned.setter
    def pinned(self, value):
        self.selection.pinned = value

    def install(self):
        # Both Apple and Android use the same measured content split, inside
        # their existing native navigation controller, including compact Back.
        adapter = self.app.native_host.adapter
        if adapter is not None and hasattr(adapter, 'navigation'):
            home = adapter.navigation[self.app.native_host.destinations.index('home')]
            home.topViewController.navigationItem.title = 'Home'
            self.sync_home_bar()
        self.render()

    def sync_home_bar(self):
        adapter = self.app.native_host.adapter
        if adapter is None or not hasattr(adapter, 'navigation'):
            return
        home = adapter.navigation[self.app.native_host.destinations.index('home')]
        # Home owns its heading. Nested routes still need UIKit's Back button.
        hidden = not bool(self.app.routes.screens['home'])
        if bool(home.isNavigationBarHidden()) != hidden:
            home.setNavigationBarHidden(hidden, animated=False)

    def uninstall(self):
        for frame in list(self.frames):
            frame.restore()
        self.last_layout = None

    def width(self):
        window = getattr(self.app, '_main_window', None)
        return window.size.width if window is not None else 0

    def content_width(self, destination, *, margin=24):
        """Measure the native allocation, never a child-driven minimum width."""
        available = self.width()
        adapter = self.app.native_host.adapter
        if adapter is not None and hasattr(adapter, 'navigation'):
            index = self.app.native_host.destinations.index(destination)
            native = adapter.navigation[index].view
            bounds, insets = native.bounds.size, native.safeAreaInsets
            if bounds.width > 0:
                available = float(bounds.width - insets.left - insets.right)
        elif (adapter is not None and getattr(adapter, 'mode', None) == 'rail'
              and adapter.impl.native_navigationview.getVisibility() != 8):
            density = self.app._impl.native.getResources().getDisplayMetrics().density
            available -= float(adapter.impl.native_navigationview.getWidth()) / density
        return max(1, int(available) - margin)

    def prepare(self, view, destination, route=None, root=False):
        # A retained session can be opened from another tab. Unwrap its old
        # workspace chrome before applying the new destination's presentation.
        frame = getattr(view, '_workspace_frame', None)
        if frame is not None and frame.destination != destination:
            frame.restore()
            detach(frame.menu)
            if hasattr(frame, 'pair'):
                detach(frame.pair)
            detach(frame.row)
            if frame.compact_toolbar is None:
                detach(frame.header)
            for child in list(frame.main.children):
                frame.main.remove(child)
                view.add(child)
            self.frames.discard(frame)
            del view._workspace_frame
        for frame in list(self.frames):
            frame.restore()
        self.last_layout = None
        if (getattr(view, '_workspace_menu', False)
                and getattr(view, '_workspace_menu_destination', None) != destination):
            detach(view._workspace_menu_button)
            del view._workspace_menu_button
            view._workspace_menu = False
        if destination not in ('files', 'documents'):
            return view
        if root and (isinstance(view, toga.ScrollContainer) or getattr(view, '_hub_sections', False)):
            original = view
            view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
            # Keep the overview's content available to its existing callers.
            view.content = original.content
        # Focused prompts and reader controls retain their own layout. Main
        # workspaces and each editor get a permanent top-left drawer control.
        eligible = (isinstance(view, toga.Box) and not getattr(view, '_reading_frame', False)
                    and not getattr(view, '_hub_sections', False) and
                    (root or route in ('editor', 'browser', 'remote-browser', 'folder-options', 'workspace-browser')
                     or (route or '').startswith('private:')))
        if eligible and not hasattr(view, '_workspace_frame'):
            view._workspace_frame = WorkspaceFrame(self, view, destination)
            view._workspace_frame.folder_options = route == 'folder-options'
            self.frames.add(view._workspace_frame)
        if eligible and destination == 'files':
            view._workspace_frame.folder_root = root
            view._workspace_frame.folder_detail = not root and route in ('browser', 'remote-browser', 'folder-options', 'workspace-browser')
        if route == 'preview' and isinstance(view, toga.Box) and not getattr(view, '_workspace_menu', False):
            menu = menu_button(lambda widget, **kw: self.show_browser(destination))
            toolbar = getattr(view, '_workspace_toolbar', view)
            toolbar.insert(0, menu)
            view._workspace_menu_button = menu
            view._workspace_menu = True
            view._workspace_menu_destination = destination
        menu = getattr(view, '_workspace_menu_button', None)
        if menu is not None and self.app.routes.apple:
            detach(menu)
        return view

    def browser(self, destination):
        if destination not in self.browsers:
            self.browsers[destination] = FileDrawer(self, destination)
        return self.browsers[destination]

    def toggle(self, destination):
        # Revealing a menu retains the editor and its draft; file-opening
        # commands keep their own checkpoint guards.
        self.app.mark_navigation()
        self.menu_open[destination] = not self.menu_open[destination]
        drawer = self.browser(destination) if self.menu_open[destination] else None
        self.render(preserve_drawer=True)
        if drawer is not None:
            drawer.extensions = None
            drawer.schedule_refresh()

    def show_browser(self, destination):
        body = self.app.routes.body(destination)
        view = body.children[0] if body.children else None
        if getattr(view, '_workspace_frame', None) is not None:
            self.toggle(destination)
            return
        # Immersive readers and focused prompts keep their existing route.
        drawer = self.browser(destination)
        if destination == 'home':
            self.app.loop.create_task(drawer.show_main_browser(drawer.storage.value,
                folder=drawer.folder, provider=drawer.provider))
            return
        detach(drawer.widget)
        box = toga.Box(children=[toga.Button('Close file browser', on_press=lambda widget, **kw:
            self.app.routes.back(), style=Pack(height=48)), drawer.widget],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        self.app.show_view(box, destination=destination, route='workspace-browser', title='Browse files')
        drawer.schedule_refresh()

    def session_view(self, key):
        return session_view(self.app, key)

    def focus_session(self, key):
        current = self.app.workspace.active
        self.selection.focus(key, current, self.session_view)

    def show_pair_picker(self, widget=None, **kwargs):
        current = self.app.workspace.active
        if self.width() < 640 or self.session_view(current) is None or not self.app.checkpoint():
            return
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Open beside this document', style=Pack(font_size=20, margin_bottom=12)))
        for key in self.selection.candidates(self.app.workspace.sessions, current, self.session_view):
            session = self.app.workspace.sessions[key]
            title = self.app.session_summary(session)[0]
            def choose(widget=None, selected=key, **kw):
                self.pinned = current
                self.menu_open['documents'] = False
                self.app.session_opener(selected)()
            box.add(list_button(toga.Button(title, on_press=choose, style=Pack(height=48))))
        if len(box.children) == 1:
            box.add(toga.Label('Open another text or Markdown file first.'))
        def browse(widget=None, **kwargs):
            self.pinned = current
            self.app.session_opener(current)()
            self.show_browser('documents')
        box.add(toga.Button('Browse for another file…', on_press=browse, style=Pack(height=48)))
        box.add(toga.Button('Use one document', on_press=self.unpin, style=Pack(height=48)))
        self.app.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                           destination='documents', route='pair-document', title='Two documents')

    def unpin(self, widget=None, **kwargs):
        self.pinned = None
        self.app.routes.back()
        self.render()

    def render(self, destination=None, *, preserve_drawer=False):
        if self.rendering:
            return
        self.rendering = True
        try:
            self.sync_home_bar()
            adapter = self.app.native_host.adapter
            if (adapter is not None and type(self.app._impl).__module__.startswith('toga_android.')
                    and adapter.impl.native.getWidth() > 0):
                # Retained Android roots can keep an old content minimum after
                # changing tabs. Use the actual allocation, including rail space.
                pixels = adapter.impl.native.getWidth()
                if adapter.mode == 'rail' and adapter.impl.native_navigationview.getVisibility() != 8:
                    pixels -= adapter.impl.native_navigationview.getWidth()
                width = adapter.impl.scale_out(pixels)
                key = destination or self.app.native_host.state.destination
                for panel in (self.app.native_host.bodies[key], self.app.routes.body(key)):
                    if panel.style.width != width:
                        panel.style.width = width
            self.layout_width = self.width()
            self.wide = self.layout_width >= 640
            from .action_menu import refresh_document_menus
            refresh_document_menus(self.app)
            self.selection.retire_unavailable(self.session_view)
            body = self.app.routes.body(destination)
            view = body.children[0] if body.children else None
            frame = getattr(view, '_workspace_frame', None)
            from .fold_layout import division
            fold = division(self.app, frame.row) if frame is not None else None
            self.wide = self.wide or fold is not None
            if frame is not None and frame.destination == 'files':
                minimum = 516 if self.app.preferences.values.get('android_eink') == 'true' else 640
                self.wide = self.content_width('files', margin=0) >= minimum or fold is not None
            layout = (id(frame), self.wide, self.layout_width, self.pinned,
                      tuple(self.menu_open.items()), frame.row.layout.content_width if frame else 0,
                      fold, frame.row.layout.content_height if frame else 0,
                      self.app.preferences.values.get('android_eink'))
            if layout != self.last_layout:
                transition = frame.begin_transition() if frame is not None else None
                for item in list(self.frames):
                    item.restore()
                if frame is not None:
                    frame.render()
                    frame.finish_transition(transition)
                self.last_layout = layout
            android = type(self.app._impl).__module__.startswith('toga_android.')
            if view is not None:
                self.app.refresh_reader_exit(view)
            if frame is not None:
                frame.sync_native_header()
            elif view is not None and self.app.routes.apple:
                menu = getattr(view, '_workspace_menu_button', None)
                if menu is not None:
                    mount_native_menu(self.app, menu, destination or self.app.native_host.state.destination)
            from .reader_chrome import sync_comic_chrome
            sync_comic_chrome(self.app, body, destination=destination)
            if view is not None:
                # Fullscreen restoration can restore the old ActionBar visibility.
                # The incoming route owns the final document-bar state.
                sync_reader_toolbar(self.app, view, destination or self.app.native_host.state.destination)
                from .ios_toolbar import sync_screen
                sync_screen(self.app, view, destination or self.app.native_host.state.destination)
            if hasattr(self.app, 'render_chat_workspace'):
                self.app.render_chat_workspace()
            from .appearance import reserve_navigation
            reserve_navigation(self.app)
            if hasattr(self.app, 'home_sections'):
                self.app.reflow_home()
            if hasattr(self.app, 'documents_sections'):
                self.app.reflow_documents_hub()
            from .browser_ui import sync_browser_population
            sync_browser_population(self.app, body)
        finally:
            self.rendering = False

    def diagnostics(self):
        destination = self.app.native_host.state.destination
        opened = self.menu_open.get(destination, False)
        paired = self.wide and destination == 'documents' and self.pinned is not None and not opened
        return dict(layout='two-documents' if paired else 'browser-detail' if self.wide and opened else 'compact',
                    width=self.layout_width, drawer_open=opened, pinned_session=self.pinned)


class WorkspaceFrame:
    def __init__(self, navigation, view, destination):
        self.navigation, self.view, self.destination = navigation, weakref.ref(view), destination
        self.main = toga.Box(style=Pack(direction=COLUMN, flex=1))
        for child in list(view.children):
            if child is getattr(view, 'transfer_banner', None):
                continue
            view.remove(child)
            self.main.add(child)
        self.compact_open = False
        self.menu = menu_button(lambda widget, **kw: navigation.toggle(destination))
        self.caption = toga.Label(destination.title(), style=Pack(flex=1, margin_top=10))
        self.compact_toolbar = getattr(view, '_workspace_toolbar', None)
        self.header = self.compact_toolbar or toga.Box(children=[self.menu, self.caption], style=Pack(direction=ROW, margin_bottom=4))
        if self.compact_toolbar is not None:
            self.header.insert(0, self.menu)
        if destination == 'documents':
            self.pair = toga.Button('Split', on_press=navigation.show_pair_picker, style=Pack(height=48))
            self.header.add(self.pair)
        self.row = toga.Box(children=[self.main], style=Pack(direction=ROW, flex=1))
        if destination != 'files' and self.compact_toolbar is None:
            view.add(self.header)
        view.add(self.row)

    def restore(self):
        self.compact_open = False
        self.main.style.margin_left = 0
        self.main.style.margin_top = 0
        self.row.style.direction = ROW
        del self.main.style.height
        del self.row.style.width
        if type(self.main._impl).__module__.startswith('toga_iOS.'):
            self.main._impl.native.userInteractionEnabled = True
        self.main.style.flex = 1
        del self.main.style.width
        if list(self.row.children) == [self.main]:
            return
        for child in list(self.row.children):
            child.style.margin_top = 0
            del child.style.height
            self.row.remove(child)
        detach(self.main)
        self.row.add(self.main)

    def sync_native_header(self):
        """Use the existing navigation bar's safe area and keep native Back."""
        app = self.navigation.app
        if not app.routes.apple:
            return
        from rubicon.objc import ObjCClass, SEL
        adapter = app.native_host.adapter
        index = app.native_host.destinations.index(self.destination)
        controller = adapter.navigation[index].topViewController
        if self.header in self.view().children:
            self.view().remove(self.header)
            self.header.remove(self.menu)
            if hasattr(self, 'pair') and self.pair in self.header.children:
                self.header.remove(self.pair)
        if self.compact_toolbar is not None:
            detach(self.menu)
            if hasattr(self, 'pair'):
                detach(self.pair)
        self.menu.app, self.menu.window = app, app.main_window
        item = controller.navigationItem
        item.leftItemsSupplementBackButton = True
        self.native_menu = mount_native_menu(app, self.menu, self.destination)
        # Workspaces enters browsers through its folder actions. Keep the drawer
        # implementation available without mounting a menu in this destination.
        item.leftBarButtonItem = self.native_menu if self.destination != 'files' else None
        if hasattr(self, 'pair'):
            self.pair.app, self.pair.window = app, app.main_window
            if not hasattr(self, 'native_pair'):
                self.native_pair = ObjCClass('UIBarButtonItem').alloc().initWithTitle(
                    'Split', style=0, target=self.pair._impl.native, action=SEL('onPress:'))
            self.native_pair.enabled = self.pair.enabled
            self.native_pair.accessibilityLabel = 'Open beside another document'
            if not hasattr(self.view(), '_native_reader_buttons'):
                item.rightBarButtonItem = self.native_pair if self.pair.enabled else None
        self.native_menu.accessibilityLabel = (
            'Close file browser' if self.navigation.menu_open[self.destination] else 'Browse files')
        self.native_menu.title = self.native_menu.accessibilityLabel

    def begin_transition(self):
        if not type(self.row._impl).__module__.startswith('toga_iOS.'):
            return None
        from ctypes import CDLL, c_bool
        reduce_motion = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduce_motion.restype = c_bool
        if reduce_motion():
            return None
        opened = self.navigation.menu_open[self.destination] and not self.navigation.wide
        if opened == self.compact_open:
            return None
        native = self.row._impl.native
        if native.bounds.size.width <= 0:
            return None
        snapshot = native.snapshotViewAfterScreenUpdates(False)
        if snapshot is None:
            return None
        return snapshot, native.bounds, opened

    def finish_transition(self, transition):
        if transition is None:
            return
        from rubicon.objc import ObjCClass, Block
        from rubicon.objc.types import CGRect
        snapshot, bounds, opened = transition
        native = self.row._impl.native
        native.addSubview(snapshot)
        snapshot.frame = bounds
        distance = min(320, max(1, bounds.size.width - 64))
        # The retained page moves right while the newly laid-out drawer is
        # revealed beneath it. Closing reverses the same movement.
        def animate():
            snapshot.frame = CGRect((distance if opened else -distance, 0), (bounds.size.width, bounds.size.height))
        def complete(finished):
            snapshot.removeFromSuperview()
        self.animation_blocks = (Block(animate, None), Block(complete, None, bool))
        ObjCClass('UIView').animateWithDuration(.28, delay=0, options=6 << 16,
            animations=self.animation_blocks[0], completion=self.animation_blocks[1])

    def render(self):
        navigation, destination = self.navigation, self.destination
        opened = navigation.menu_open[destination]
        self.caption.text = 'Browse files' if opened else DESTINATION_LABELS[destination]
        if hasattr(self, 'pair'):
            self.pair.enabled = navigation.wide and navigation.session_view(navigation.app.workspace.active) is not None
            if self.pair.enabled and self.pair not in self.header.children:
                if not navigation.app.routes.apple:
                    self.header.add(self.pair)
            elif not self.pair.enabled and self.pair in self.header.children:
                self.header.remove(self.pair)
        left = self._leading_pane(opened)
        if left is None:
            return
        if left is not self.main:
            detach(left)
        if navigation.wide:
            self._render_split(left, opened)
        else:
            self._render_drawer(left)

    def _leading_pane(self, opened):
        """Select retained content without rebuilding its widgets or scroll state."""
        navigation, destination = self.navigation, self.destination
        left = None
        if opened:
            left = navigation.browser(destination).widget
        elif navigation.wide and destination == 'files':
            if getattr(self, 'folder_root', False):
                # Keep a stable two-pane overview before a location is opened.
                if not hasattr(self, 'folder_placeholder'):
                    self.folder_placeholder = toga.Box(children=[toga.Label('Choose a workspace',
                        style=Pack(margin=16))], style=Pack(direction=COLUMN, flex=1))
                left = self.main
            elif getattr(self, 'folder_detail', False):
                root = navigation.app.routes.roots['files']
                overview = root.children[0] if root.children else None
                master = getattr(overview, '_workspace_frame', None)
                if master is not None:
                    # Borrow the actual overview: rebuilding it loses scroll
                    # state and overwrites the host's source-control references.
                    self.folder_master = master.main
                    left = self.folder_master
        elif navigation.wide and destination == 'documents':
            view = navigation.session_view(navigation.pinned)
            if view is not None and view is not self.view():
                frame = getattr(view, '_workspace_frame', None)
                left = frame.main if frame else view
        return left

    def _render_drawer(self, left):
        """Mount the compact browser while retaining the covered document."""
        available = self.navigation.content_width(self.destination)
        drawer_width = max(1, min(320, available - 64))
        left.style.width, left.style.flex = drawer_width, 0
        self.main.style.width, self.main.style.flex = available, 0
        self.row.insert(0, left)
        self.row.style.width = available
        self.compact_open = True
        if type(self.row._impl).__module__.startswith('toga_iOS.'):
            self.row._impl.native.clipsToBounds = True
            self.main._impl.native.userInteractionEnabled = False

    def _render_split(self, left, opened):
        """Apply the fold-aware allocation to the two retained panes."""
        navigation, destination = self.navigation, self.destination
        view = self.view()
        margin = view.style.margin_left + view.style.margin_right if destination == 'files' else 24
        available = navigation.content_width(destination, margin=margin)
        from .fold_layout import division, has_fold
        from .pane_layout import panes
        fold = division(navigation.app, self.row)
        priority = (destination == 'files' or opened) and (
            has_fold(navigation.app, self.row) or
            navigation.app.preferences.values.get('android_eink') == 'true')
        allocation = panes(available, self.row.layout.content_height or 1,
                           fold=fold, browser_priority=priority)
        right = self.folder_placeholder if left is self.main else self.main
        self.row.style.direction = ROW if allocation.axis == 'row' else COLUMN
        for pane, extent in ((left, allocation.leading), (right, allocation.trailing)):
            pane.style.flex = 0
            if allocation.axis == 'row':
                del pane.style.height
                pane.style.width = extent
            else:
                del pane.style.width
                pane.style.height = extent
        right.style.margin_left = allocation.gap if allocation.axis == 'row' else 0
        right.style.margin_top = allocation.gap if allocation.axis == 'column' else 0
        if left is self.main:
            self.row.add(right)
            return
        self.row.insert(0, left)
