"""Destination-owned drawers and equal-width document panes over native routes.

The native tab and Back stacks stay authoritative. A pane moves existing widget
owners rather than copying editor buffers or mounting a widget twice.
"""
import asyncio
from pathlib import Path
import weakref

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.resource_selection import ResourceSelection
from .appearance import list_button
from .adaptive_workspace import AdaptiveWorkspace
from .files_ui import local_read_available
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


def detach(widget):
    if widget.parent is not None:
        widget.parent.remove(widget)


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
    from .ios_reader_chrome import bar_control, bar_group, bar_separator, action_groups
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
            controller.navigationItem.rightBarButtonItems = None
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
    state = (controller.ptr.value, tuple(id(button) for button in buttons))
    if getattr(app, '_reader_toolbar_state', None) != state:
        for button in buttons:
            detach(button)
            button.app, button.window = app, app.main_window
        mounted = [bar_group(group) for group in action_groups(buttons)]
        items = []
        # UIKit orders trailing items from the outside edge inward.
        for item, group in reversed(mounted):
            if items:
                items.append(bar_separator())
            items.append(item)
        controller.navigationItem.rightBarButtonItems = items
        app._reader_toolbar_groups = [group for _, group in mounted]
        app._reader_toolbar_group = mounted[0][1] if mounted else None
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
    leading = 104 if getattr(view, '_workspace_menu_button', None) is not None or hasattr(view, '_workspace_frame') else 52
    width = max(44, app.adaptive.content_width(destination, margin=0)
                - 2 * max(leading, 44 * len(buttons) + 8 * max(0, len(action_groups(buttons)) - 1)) - 24)
    title_state = (controller.ptr.value, text, width, state)
    if getattr(app, '_reader_title_state', None) != title_state:
        from .ios_reader_chrome import reader_title
        title_view, label = reader_title(text, width, app._reader_toolbar_group)
        controller.navigationItem.titleView = title_view
        app._reader_title_label = label
        app._reader_title_state = title_state
    app._reader_title_controller = controller
    close = getattr(view, '_reader_close_button', None)
    if close is not None:
        detach(close)
        close.app, close.window = app, app.main_window
        if not hasattr(close, '_native_reader_close_item'):
            close._native_reader_close_item, close._native_reader_close_group = bar_group([close])
        close._native_reader_close_item.accessibilityLabel = close.accessible_name
        bar_control(close)
        frame = getattr(view, '_workspace_frame', None)
        menu = frame.menu if frame is not None else getattr(view, '_workspace_menu_button', None)
        items = [close._native_reader_close_item]
        if menu is not None:
            items.extend([bar_separator(), mount_native_menu(app, menu, destination)])
        controller.navigationItem.leftItemsSupplementBackButton = False
        controller.navigationItem.hidesBackButton = True
        controller.navigationItem.leftBarButtonItems = items


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
            home.setNavigationBarHidden(False, animated=False)
        self.render()

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
            from .fold_layout import seam_fraction
            seam = (seam_fraction(self.app, frame.row, include_open=True)
                    if frame is not None and frame.destination == 'files' else None)
            if frame is not None and frame.destination == 'files':
                self.wide = self.content_width('files', margin=0) >= 640 or seam is not None
            layout = (id(frame), self.wide, self.layout_width, self.pinned,
                      tuple(self.menu_open.items()), frame.row.layout.content_width if frame else 0,
                      seam)
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
        del self.row.style.width
        if type(self.main._impl).__module__.startswith('toga_iOS.'):
            self.main._impl.native.userInteractionEnabled = True
        self.main.style.flex = 1
        del self.main.style.width
        if list(self.row.children) == [self.main]:
            return
        for child in list(self.row.children):
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
            if not hasattr(self.view(), '_native_reader_buttons'):
                item.rightBarButtonItem = self.native_pair if self.pair.enabled else None
        self.native_menu.accessibilityLabel = (
            'Close file browser' if self.navigation.menu_open[self.destination] else 'Browse files')

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
        if left is None:
            return
        if left is not self.main:
            detach(left)
        if not navigation.wide:
            available = navigation.content_width(destination)
            drawer_width = max(1, min(320, available - 64))
            left.style.width, left.style.flex = drawer_width, 0
            self.main.style.width, self.main.style.flex = available, 0
            self.row.insert(0, left)
            self.row.style.width = available
            self.compact_open = True
            if type(self.row._impl).__module__.startswith('toga_iOS.'):
                self.row._impl.native.clipsToBounds = True
                self.main._impl.native.userInteractionEnabled = False
        else:
            view = self.view()
            margin = view.style.margin_left + view.style.margin_right if destination == 'files' else 24
            available = navigation.content_width(destination, margin=margin)
            from .fold_layout import seam_fraction
            seam = seam_fraction(navigation.app, self.row, include_open=True) if destination == 'files' else None
            half = max(1, available * (seam if seam is not None else .5))
            # Leave a real gutter between navigation and content on both backends.
            gap = 16
            left.style.width, left.style.flex = max(1, half - gap / 2), 0
            right = self.folder_placeholder if left is self.main else self.main
            right.style.margin_left = gap
            right.style.width, right.style.flex = max(1, available - half - gap / 2), 0
            if left is self.main:
                self.row.add(right)
                return
            self.row.insert(0, left)


class FileDrawer:
    """Independent browser state; opening never rewrites the Workspaces tab's selection."""
    def __init__(self, navigation, destination):
        from .browser_ui import FileBrowser, browser_command
        self.navigation, self.app, self.destination = navigation, navigation.app, destination
        self.roots = {'Local files': None}
        self.provider = None
        self.extensions = None
        self.folder = ''
        self.generation = 0
        self.task = None
        self.refresh_requested = False
        from .folder_listing import FolderListing
        self.listing = FolderListing(active=lambda: self.app.active_host,
            context=lambda: (self.generation, id(self.browser)),
            location=lambda: (self.storage.value, self.folder),
            credentials=lambda: (getattr(self.app, 'cloud_client', None),
                getattr(getattr(self.app, 'cloud_client', None), 'generation', None)))
        self.storage = toga.Selection(items=['Local files'], style=Pack(height=48))
        self.browser = FileBrowser(folder_visible=self.app.folder_path_visible, contextual_selection=False,
                                   selected=lambda row: None, open_folder=self.open_folder,
                                   navigate=self.navigate, open_file=self.open_file, preview=False)
        self.status = self.browser.status_label('')
        self.parent_button = browser_command(toga.Button('Parent folder', on_press=self.up,
                                                       enabled=False, style=Pack(height=48)))
        header = self.browser.attach_location_header(self.status, self.parent_button)
        self.breadcrumb = header.folder_name
        self.workspaces_button = toga.Button('Workspaces', on_press=self.app.show_locations, style=Pack(height=48))
        self.widget = toga.Box(children=[self.storage, header,
            self.browser.scroll_container(), self.workspaces_button],
            style=Pack(direction=COLUMN, flex=1))
        self.browser_widget = self.widget
        if destination == 'documents':
            self.menu_content = toga.Box(style=Pack(direction=COLUMN, margin=12))
            self.widget = toga.ScrollContainer(horizontal=False, content=self.menu_content, style=Pack(flex=1))
        self.storage.on_change = self.change_storage

    async def show_main_browser(self, storage, *, folder='', extensions=None, title='Browse files', provider=None):
        if not self.app.checkpoint():
            return False
        if self.destination == 'home' and hasattr(self, 'page'):
            # A second picker can be opened from a reader above the first one.
            # Each owns its controls and return edge rather than moving the
            # older picker's widget out from under its retained reader.
            drawer = FileDrawer(self.navigation, self.destination)
            self.navigation.browsers[self.destination] = drawer
            return await drawer.show_main_browser(storage, folder=folder, extensions=extensions,
                                                  title=title, provider=provider)
        self.extensions = extensions
        client = getattr(self.app, 'cloud_client', None)
        self.scoped_provider = (storage, provider, client, getattr(client, 'generation', None)) if provider else None
        self.folder = folder
        self.changing_storage = True
        try:
            self.storage.items = list(dict.fromkeys([*self.roots, storage]))
            self.storage.value = storage
        finally:
            self.changing_storage = False
        self.navigation.menu_open[self.destination] = False
        detach(self.browser_widget)
        page = toga.Box(children=[self.browser_widget], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.page = page
        if self.destination != 'files':
            page._folder_return_count = len(self.app.routes.screens[self.destination])
            page._folder_scope = str(id(page))
            page._folder_detail_return_count = len(self.app.adaptive.detail_routes)
            if self.workspaces_button in self.browser_widget.children:
                self.browser_widget.remove(self.workspaces_button)
            self.cancel_button = toga.Button('Cancel', on_press=self.cancel_browser,
                                            style=Pack(height=48, width=72))
            self.browser.location_bar.add(self.cancel_button)
        route = ('workspace-browser:' + page._folder_scope if self.destination == 'home' else 'workspace-browser')
        self.app.show_view(page, destination=self.destination, route=route, title=title)
        return await self.refresh()

    def cancel_browser(self, widget=None, **kwargs):
        if not self.app.checkpoint():
            return
        self.app.mark_navigation()
        self.listing.invalidate()
        self.refresh_requested = False
        if self.destination == 'documents' and self.app.adaptive.split is not None:
            self.app.adaptive.trim_details(self.page._folder_detail_return_count)
            if self.app.adaptive.detail_routes:
                self.app.body = self.app.adaptive.detail_routes[-1][1]
                self.app.route_changed(self.app.body)
            else:
                self.app.adaptive.show_list()
        else:
            self.app.routes.trim(self.destination, self.page._folder_return_count)
            self.app.routes.render(self.destination)

    def refresh_menu(self):
        from .hub_ui import heading
        for child in list(self.menu_content.children):
            self.menu_content.remove(child)
        # The tap path only renders cached results. Native rclone calls run
        # in refresh() on a worker after the drawer is already visible.
        self.menu_content.add(heading('Comics Library'))
        readers = getattr(self.app, 'readers', None)
        catalog = readers.catalog if readers is not None else None
        self.library_buttons = []
        for record in getattr(catalog, 'library_records', ()):
            if not self.app.library_folder_visible(record):
                continue
            async def browse_library(widget=None, library=record, **kwargs):
                provider = library['provider']
                if provider.private and (self.app.cloud_client is not library['client']
                        or self.app.cloud_client.generation != library['generation']):
                    self.status.text = 'Unlock the library connection again.'
                    self.schedule_refresh()
                    return
                storage = library['source'] if provider.private else 'Local files'
                await self.show_main_browser(storage, folder=library['folder'], provider=provider)
            button = list_button(toga.Button(record['name'], on_press=browse_library, style=Pack(height=48)))
            self.library_buttons.append(button)
            self.menu_content.add(button)
        if not self.library_buttons:
            self.menu_content.add(toga.Label('No configured libraries found.'))


    def schedule_refresh(self):
        self.generation += 1
        self.listing.invalidate()
        self.refresh_requested = True
        if self.destination == 'documents':
            self.refresh_menu()
        if self.task is None or self.task.done():
            self.task = self.app.loop.create_task(self.refresh_pending())

    async def refresh_pending(self):
        while self.refresh_requested and self.app.active_host:
            self.refresh_requested = False
            await self.refresh()

    def change_storage(self, widget=None, **kwargs):
        if getattr(self, 'changing_storage', False):
            return
        self.folder = ''
        self.scoped_provider = None
        self.schedule_refresh()

    def available_roots(self):
        roots = {'Local files': None}
        if local_read_available(self.app):
            roots.update(self.app.existing_crypt_locations())
            roots.update(self.app.linked_crypt_locations())
        return roots

    async def refresh(self):
        with self.browser.population_paused():
            self.generation += 1
            generation = self.generation
            work = self.listing.begin()
            try:
                roots = await asyncio.to_thread(self.available_roots)
            except (OSError, ValueError) as error:
                # A failed credential query must not strand the menu refresh task.
                # Keep Local files usable and report the connection error in-place.
                if not self.listing.accepts(work, private=True):
                    return False
                self.status.value = str(error)[:160]
                return False
            if not self.listing.accepts(work, private=True):
                return False
            scope = getattr(self, 'scoped_provider', None)
            if scope is not None:
                roots.setdefault(scope[0], None)
            selected = self.storage.value if self.storage.value in roots else 'Local files'
            self.changing_storage = True
            try:
                self.roots = roots
                self.storage.items = list(roots)
                self.storage.value = selected
            finally:
                self.changing_storage = False
            if self.app.routes.apple and self.destination == 'home' and hasattr(self, 'page'):
                if len(roots) == 1:
                    detach(self.storage)
                elif self.storage.parent is None:
                    self.browser_widget.insert(0, self.storage)
            request = None
            try:
                if selected != 'Local files' and not local_read_available(self.app):
                    raise ValueError('This connection is busy. Local files remain available.')
                if scope is not None and scope[0] == selected:
                    provider = scope[1]
                    if provider.private and (self.app.cloud_client is not scope[2]
                            or self.app.cloud_client.generation != scope[3]):
                        raise ValueError('Unlock the library connection again.')
                else:
                    provider = self.app.storage_provider(selected, roots)
                model = ResourceSelection(provider, extensions=self.extensions or ())
                folder = self.folder
                request = self.listing.capture(work, provider, folder, (selected, folder), source=model)
                rows = await self.listing.read(request)
                if rows is None:
                    return False
                self.provider = provider
                self.provider_client = getattr(self.app, 'cloud_client', None)
                self.provider_generation = getattr(self.provider_client, 'generation', None)
                self.browser.set_entries(model, folder, rows, location=(selected, folder))
                self.browser.location_bar.update_provider(folder, provider)
                self.parent_button.enabled = bool(folder)
                if hasattr(self, 'page'):
                    from .folder_navigation import record
                    record(self.app, self.page, self.browser, 'workspace-browser', selected, folder, self.navigate)
                self.status.value = ''
                if self.destination == 'documents':
                    self.refresh_menu()
                    catalog = self.app.reader_manager().catalog
                    await catalog.refresh_library_folders()
                    if generation == self.generation and self.app.active_host:
                        self.refresh_menu()
                return True
            except (OSError, ValueError) as error:
                if not self.listing.accepts(work, request, private=request is None):
                    return False
                self.provider = None
                self.browser.stop()
                self.status.value = str(error)[:160]
                return False

    async def open_folder(self, row):
        self.app.routes.folders.capture()
        self.folder = row['path']
        return await self.refresh()

    async def navigate(self, location):
        if self.destination == 'home':
            self.navigation.browsers[self.destination] = self
        if not self.app.routes.folders.restoring:
            self.app.routes.folders.capture()
        label, folder = location
        if label not in self.roots:
            return False
        self.changing_storage = True
        try:
            self.storage.value = label
        finally:
            self.changing_storage = False
        self.folder = folder
        return await self.refresh()

    async def up(self, widget=None, **kwargs):
        self.folder = self.folder.rpartition('/')[0]
        return await self.refresh()

    async def open_file(self, row):
        from features.text_editor.resources import LocalTextCopies
        from features.rclone.localcrypt.mobile.resources import encrypted_document
        provider = self.provider
        if provider is None or not self.app.checkpoint():
            return
        path = row['path']
        try:
            if provider.private and (self.app.cloud_client is not self.provider_client
                    or self.app.cloud_client.generation != self.provider_generation):
                raise ValueError('Unlock the connection again before opening private files.')
            if not local_read_available(self.app, private=provider.private):
                raise ValueError('This connection is busy. Local files remain available.')
            if not provider.private and Path(path).suffix.lower() not in {'.txt', '.md', '.markdown'}:
                if not await self.app.open_download(path=provider._locate(path), destination=self.destination):
                    self.status.value = str(self.app.cloud_status.value or 'Could not open this file. Try opening it again.')[:300]
                    return False
            else:
                self.app.show_cloud(present=False)
                source = encrypted_document(provider, path)
                copies, key = source if source is not None else (LocalTextCopies(provider), path)
                opened = await self.app.open_crypt(copies=copies, key=key, destination=self.destination)
                if not opened:
                    self.status.value = str(self.app.cloud_status.value or 'Could not open this private file. Unlock its connection and try again.')[:300]
                    return False
            if self.app.native_host.state.destination == self.destination:
                if not self.navigation.wide:
                    self.navigation.menu_open[self.destination] = False
                self.navigation.render()
            return True
        except (OSError, ValueError) as error:
            self.status.value = str(error)[:160]
            return False
