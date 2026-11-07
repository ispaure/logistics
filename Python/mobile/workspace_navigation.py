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
    controller = adapter.content_controller(destination)
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
    current = item.leftBarButtonItem
    if current is None or current.ptr.value != menu._native_workspace_item.ptr.value:
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
    from .ios_toolbar import mount_actions, mount_leading, clear_actions, action_state, layout_geometry
    adapter = app.native_host.adapter
    destination = destination or app.native_host.state.destination
    controller = adapter.content_controller(destination)
    owned = getattr(app, '_reader_toolbar_controllers', None)
    if owned is None:
        owned = app._reader_toolbar_controllers = set()
    key = controller.ptr.value
    projections = getattr(app, '_reader_toolbar_projections', None)
    if projections is None:
        projections = app._reader_toolbar_projections = {}
    from .reader_top_band import project, release_other
    release_other(app, view)
    controls = getattr(view, '_native_reader_buttons', None)
    if controls is None:
        # Tabs retain their controllers. Clear reader-owned chrome even when a
        # different tab was the most recent reader toolbar to be rendered.
        if key in owned:
            clear_actions(controller.navigationItem)
            controller.navigationItem.prompt = None
            controller.navigationItem.titleView = None
            owned.discard(key)
            projections.pop(key, None)
            projections.pop((key, 'leading'), None)
            if getattr(app, '_reader_toolbar_controller', None) == controller:
                app._reader_toolbar_controller = None
                app._reader_toolbar_state = None
                app._reader_toolbar_prompt = None
            if getattr(app, '_reader_title_controller', None) == controller:
                app._reader_title_controller = None
                app._reader_title_state = None
        return
    status = getattr(view, '_native_reader_status', None)
    message = status.text if status is not None else ''
    prompt = message if message.lower().startswith(('save failed', 'cannot ', 'unsaved changes:',
        'book import failed', 'could not ')) else None
    drawing_tools = getattr(view, '_native_drawing_tools', None)
    inline_notice = (drawing_tools is not None and getattr(view, '_notebook_canvas', None) is not None
                     and prompt is not None and not getattr(view, '_reader_fullscreen', False)
                     and drawing_tools.wide_landscape(controller))
    if getattr(view, '_notebook_inline_notice', None) is not None and not inline_notice:
        detach(view._notebook_inline_notice)
        view._notebook_inline_notice = None
    if project(app, view, destination, controller):
        band = view._reader_top_band_state
        title = getattr(view, '_native_reader_title', '')
        title = str(title() if callable(title) else title or '').replace('\n', ' ')
        if str(controller.navigationItem.title or '') != title:
            controller.navigationItem.title = title
        projections.pop(key, None)
        projections.pop((key, 'leading'), None)
        owned.add(key)
        app._reader_toolbar_controller = controller
        app._reader_toolbar_state = band['signature']
        app._reader_toolbar_prompt = (key, None)
        app._reader_title_controller = controller
        return
    toolbar = view._native_reader_toolbar
    detach(toolbar)
    for control in getattr(view, '_native_reader_hidden', ()):
        detach(control)
    from .reader_chrome import reader_buttons
    buttons = [] if getattr(view, '_reader_fullscreen', False) else reader_buttons(app, view)
    geometry = layout_geometry(controller)
    state = (action_state(buttons), geometry)
    for button in buttons:
        detach(button)
        button.app, button.window = app, app.main_window
    # Replacing identical native groups during keyboard/layout notifications
    # cancels UIKit's in-progress menu presentation. Refresh only changed data.
    if projections.get(key) != state:
        mount_actions(controller, view, buttons)
        projections[key] = state
    app._reader_toolbar_state = state
    if inline_notice:
        prompt = None
    if getattr(app, '_reader_toolbar_prompt', None) != (controller.ptr.value, prompt):
        controller.navigationItem.prompt = prompt
        app._reader_toolbar_prompt = (controller.ptr.value, prompt)
    owned.add(key)
    app._reader_toolbar_controller = controller
    title = getattr(view, '_native_reader_title', None)
    text = str(title() if callable(title) else title or controller.navigationItem.title or '').replace('\n', ' ')
    # UIKit sizes the title inside the actual container, including vertical bars
    # and split panes; don't reserve horizontal gutters for now-vertical actions.
    controller.navigationItem.title = text
    from .document_location import mount_apple_title
    mount_apple_title(view, controller, text)
    if inline_notice and status.parent is not view:
        from features.notebooks.mobile.native_tools import LANDSCAPE_INSET
        header = view._document_title_header
        status.style.update(font_size=13, text_align='center', margin=(0, LANDSCAPE_INSET, 6, LANDSCAPE_INSET))
        view.insert(list(view.children).index(header) + 1, status)
        view._notebook_inline_notice = status
    app._reader_title_controller = controller
    close = getattr(view, '_reader_close_button', None)
    if close is not None:
        frame = getattr(view, '_workspace_frame', None)
        menu = frame.menu if frame is not None else getattr(view, '_workspace_menu_button', None)
        title_controls = getattr(view, '_document_title_controls', ())
        leading = [button for button in (close, menu) if button is not None and button not in title_controls]
        for button in leading:
            detach(button)
            button.app, button.window = app, app.main_window
        leading_state = (action_state(leading), geometry)
        if projections.get((key, 'leading')) != leading_state:
            mount_leading(controller, leading, replaces_back=True)
            projections[key, 'leading'] = leading_state
        close._native_reader_close_item = close._ios_action_item if close in leading else None


class WorkspaceNavigation(AdaptiveWorkspace):
    def __init__(self, app):
        super().__init__(app)
        self.frames = weakref.WeakSet()
        self.browsers = {}
        self.menu_open = dict(files=False, documents=False)
        self.selection = WorkspaceSelection()
        self.rendering = False
        self.last_layout = None
        self._pending_destination_bar = None

    @property
    def pinned(self):
        return self.selection.pinned

    @pinned.setter
    def pinned(self, value):
        self.selection.pinned = value

    def install(self):
        # Both Apple and Android use the same measured content split, inside
        # their existing native navigation controller, including compact Back.
        self.render()

    def update_destination_bar(self, destination):
        host = self.app.native_host
        adapter = host.adapter
        if not getattr(adapter, 'sidebar_used', False):
            self.sync_destination_bar(destination)
            return
        if host.state.destination != destination:
            return
        # The iPad sidebar can deliver a folder selection while UIKit is
        # mounting the pushed controller. Showing the bar performs layout
        # synchronously, so let that native transition unwind first.
        if self._pending_destination_bar is None:
            self.app.loop.call_soon(self._flush_destination_bar)
        self._pending_destination_bar = adapter, destination

    def _flush_destination_bar(self):
        pending, self._pending_destination_bar = self._pending_destination_bar, None
        if pending is None:
            return
        adapter, destination = pending
        host = self.app.native_host
        if host.adapter is adapter and host.state.destination == destination:
            self.sync_destination_bar(destination)

    def sync_destination_bar(self, destination):
        """Reclaim title-only root bars after the screen mounts its actions."""
        adapter = self.app.native_host.adapter
        if (adapter is None or not hasattr(adapter, 'navigation')
                or getattr(self.app, '_reader_chrome_hidden', False)):
            return
        navigation = adapter.navigation_for(destination)
        controller = adapter.content_controller(destination)
        item = controller.navigationItem
        body = self.app.routes.body(destination)
        view = body.children[0] if body is not None and body.children else None
        nested = (bool(self.app.routes.screens[destination])
                  or len(list(navigation.viewControllers)) > 1)
        if not nested and not hasattr(view, '_native_reader_buttons') and getattr(item, 'title', None):
            # A destination label belongs to its tab/rail, not a second heading.
            # Reader and native Back/More controllers retain their own titles.
            item.title = ''
        if getattr(view, '_reader_top_band_state', None) is not None:
            if not bool(navigation.isNavigationBarHidden()):
                navigation.setNavigationBarHidden(True, animated=False)
            return
        if not self.app.routes.screens[destination] and hasattr(view, '_destination_actions'):
            projected = (getattr(view, '_home_top_band', None) is not None
                         or getattr(view, '_destination_top_band', None) is not None)
            hidden = projected or not bool(view._ios_toolbar_buttons())
            if bool(navigation.isNavigationBarHidden()) != hidden:
                navigation.setNavigationBarHidden(hidden, animated=False)
            return
        # Include both legacy item arrays and modern grouped/overflow actions.
        # Disabled actions still need their toolbar, as do native More/Back routes.
        actions = any(list(getattr(item, name, None) or ()) for name in (
            'leftBarButtonItems', 'rightBarButtonItems', 'leadingItemGroups', 'trailingItemGroups'))
        actions = actions or any(getattr(item, name, None) is not None for name in (
            'pinnedTrailingGroup', 'additionalOverflowItems'))
        close = getattr(view, '_reader_close_button', None)
        inline_close = close is not None and close in getattr(view, '_document_title_controls', ())
        if inline_close:
            from .document_location import side_title_header
            inline_close = side_title_header(view) is not None
        hidden = not (actions or getattr(item, 'prompt', None) or (nested and not inline_close))
        if bool(navigation.isNavigationBarHidden()) != hidden:
            navigation.setNavigationBarHidden(hidden, animated=False)
        if destination == 'settings' and nested and body is not None and body.children:
            from .settings.titles import sync_route_title
            sync_route_title(body.children[-1], navigation, controller)

    def uninstall(self):
        self._pending_destination_bar = None
        columns = getattr(self, 'file_columns', None)
        if columns is not None:
            columns.close()
            self.file_columns = None
        for frame in list(self.frames):
            frame.restore()
        self.last_layout = None

    def width(self):
        window = getattr(self.app, '_main_window', None)
        return window.size.width if window is not None else 0

    def content_width(self, destination, *, margin=24, full=False):
        """Measure the native allocation or its visible Settings detail pane."""
        available = self.width()
        adapter = self.app.native_host.adapter
        if adapter is not None and hasattr(adapter, 'navigation'):
            index = self.app.native_host.destinations.index(destination)
            columns = getattr(self, 'file_columns', None)
            native = (columns.controller.view if destination == 'files' and columns is not None
                      else adapter.navigation[index].view)
            bounds, insets = native.bounds.size, native.safeAreaInsets
            if bounds.width > 0:
                available = float(bounds.width - insets.left - insets.right)
        elif (adapter is not None and getattr(adapter, 'mode', None) == 'rail'
              and adapter.impl.native_navigationview.getVisibility() != 8):
            density = self.app._impl.native.getResources().getDisplayMetrics().density
            available -= float(adapter.impl.native_navigationview.getWidth()) / density
        if not full and destination == 'settings':
            settings = getattr(self.app, 'settings_navigation', None)
            if settings is not None and self.app.routes.screens['settings']:
                available = min(available, settings.detail_width)
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
            if root:
                from .destination_actions import prepare
                view = prepare(self.app, view, destination)
            return view
        if root and (isinstance(view, toga.ScrollContainer) or getattr(view, '_hub_sections', False)):
            original = view
            view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
            # Keep the overview's content available to its existing callers.
            view.content = original.content
        # Focused prompts and reader controls retain their own layout. Main
        # workspaces and each editor get a permanent top-left drawer control.
        eligible = (isinstance(view, toga.Box) and not getattr(view, '_reading_frame', False)
                    and not getattr(view, '_hub_sections', False)
                    and not getattr(view, '_standalone_markdown', False) and
                    not getattr(view, '_documents_overview', False) and
                    (root or route in ('editor', 'browser', 'remote-browser', 'folder-options', 'workspace-browser')
                     or (route or '').startswith('private:')))
        if eligible and not hasattr(view, '_workspace_frame'):
            view._workspace_frame = WorkspaceFrame(self, view, destination)
            view._workspace_frame.folder_options = route == 'folder-options'
            self.frames.add(view._workspace_frame)
        if eligible and destination == 'files':
            view._workspace_frame.folder_root = root
            view._workspace_frame.folder_detail = not root and route in ('browser', 'remote-browser', 'folder-options', 'workspace-browser')
        menu = getattr(view, '_workspace_menu_button', None)
        if (menu is not None and self.app.routes.apple
                and menu not in getattr(view, '_document_title_controls', ())):
            detach(menu)
        if root:
            from .destination_actions import prepare
            view = prepare(self.app, view, destination)
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
            target = destination or self.app.native_host.state.destination
            body = self.app.routes.body(target)
            # Settings child routes keep the original page after the category pane.
            view = body.children[-1 if target == 'settings' else 0] if body.children else None
            frame = getattr(view, '_workspace_frame', None)
            from .fold_layout import division, has_fold
            fold = division(self.app, frame.row) if frame is not None else None
            foldable = has_fold(self.app, frame.row) if frame is not None else False
            self.wide = self.wide or fold is not None
            if frame is not None and frame.destination == 'files':
                minimum = 516 if self.app.preferences.values.get('android_eink') == 'true' else 640
                from .pane_layout import browser_columns
                self.wide = browser_columns(self.content_width('files', margin=0),
                    self.app.main_window.size.height, minimum=minimum, fold=fold,
                    allow_portrait=minimum == 516)
            from .ios_workspace_columns import sync
            sync(self)
            from .folder_hub_ui import reflow_folder_notice
            reflow_folder_notice(self.app)
            # Only stacked panes allocate explicit heights. Keyboard/search
            # height changes must not unmount a side-by-side browser: UIKit
            # resigns its search field's first responder when it is detached.
            split_height = frame.row.layout.content_height if fold is not None and not fold.vertical else None
            layout = (id(frame), self.wide, self.layout_width, self.pinned,
                      tuple(self.menu_open.items()), frame.row.layout.content_width if frame else 0,
                      fold, foldable, split_height, self.content_width(frame.destination) if frame else 0,
                      self.app.preferences.values.get('android_eink'))
            if layout != self.last_layout:
                if frame is None or not frame.reflow_split():
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
                if menu is not None and not hasattr(view, '_native_reader_buttons'):
                    mount_native_menu(self.app, menu, destination or self.app.native_host.state.destination)
            from .reader_chrome import sync_comic_chrome
            sync_comic_chrome(self.app, body, destination=destination)
            if view is not None:
                # Fullscreen restoration can restore the old ActionBar visibility.
                # The incoming route owns the final document-bar state.
                sync_reader_toolbar(self.app, view, destination or self.app.native_host.state.destination)
                from .destination_actions import refresh as refresh_root_actions
                refresh_root_actions(self.app, view)
                from .destination_actions import sync_native_host
                sync_native_host(self.app, view, destination or self.app.native_host.state.destination)
                from .ios_toolbar import sync_screen
                sync_screen(self.app, view, destination or self.app.native_host.state.destination)
            if hasattr(self.app, 'render_chat_workspace'):
                self.app.render_chat_workspace()
            self.update_destination_bar(destination or self.app.native_host.state.destination)
            from .appearance import reserve_navigation
            reserve_navigation(self.app)
            if hasattr(self.app, 'home_sections'):
                self.app.reflow_home()
            if hasattr(self.app, 'documents_sections'):
                self.app.reflow_documents_hub()
            from .transfer_status import refresh as refresh_sync_status
            refresh_sync_status(self.app, destination)
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
        columns = getattr(self.navigation, 'file_columns', None)
        if columns is not None and columns.master is self:
            return
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
        controller = adapter.content_controller(self.destination)
        if self.header in self.view().children:
            self.view().remove(self.header)
            self.header.remove(self.menu)
            if hasattr(self, 'pair') and self.pair in self.header.children:
                self.header.remove(self.pair)
        if self.compact_toolbar is not None:
            detach(self.menu)
            if hasattr(self, 'pair'):
                detach(self.pair)
        if hasattr(self.view(), '_native_reader_buttons'):
            # Reader projection owns Close and Browse as one leading group.
            # Assigning a standalone leftBarButtonItem here removes Close;
            # its unchanged projection cache cannot then restore it.
            from .appearance import accessible_name
            accessible_name(self.menu, 'Close file browser' if
                self.navigation.menu_open[self.destination] else 'Browse files')
            return
        self.menu.app, self.menu.window = app, app.main_window
        item = controller.navigationItem
        if self.destination == 'files':
            # This destination has no root drawer button. Do not insert and
            # immediately remove one on every native resize/rotation callback.
            if item.leftBarButtonItem is not None:
                item.leftBarButtonItem = None
            return
        item.leftItemsSupplementBackButton = True
        self.native_menu = mount_native_menu(app, self.menu, self.destination)
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
        columns = getattr(navigation, 'file_columns', None)
        if columns is not None and destination == 'files':
            if getattr(self, 'folder_root', False):
                if not hasattr(self, 'folder_placeholder'):
                    self.folder_placeholder = toga.Box(children=[toga.Label('Choose a workspace',
                        style=Pack(margin=16))], style=Pack(direction=COLUMN, flex=1))
                if self.folder_placeholder not in self.row.children:
                    self.row.add(self.folder_placeholder)
            return
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

    def reflow_split(self):
        """Resize an existing pair without detaching focused/scrolling controls."""
        if not self.navigation.wide or (self.destination == 'files' and
                getattr(self.navigation, 'file_columns', None) is not None):
            return False
        left = self._leading_pane(self.navigation.menu_open[self.destination])
        if left is None:
            return False
        right = self.folder_placeholder if left is self.main else self.main
        if list(self.row.children) != [left, right]:
            return False
        before = self.split_frames()
        self._render_split(left, self.navigation.menu_open[self.destination])
        self.animate_split(before)
        return True

    def split_frames(self):
        """Toga flattens Box descendants into the native container's siblings."""
        if not type(self.row._impl).__module__.startswith('toga_iOS.'):
            return ()
        from ctypes import CDLL, c_bool
        reduced = CDLL(None).UIAccessibilityIsReduceMotionEnabled
        reduced.restype = c_bool
        if reduced():
            return ()

        def frames(widget):
            native = widget._impl.native
            layer = native.layer.presentationLayer()
            rect = layer.frame if layer is not None else native.frame
            yield native, (float(rect.origin.x), float(rect.origin.y),
                           float(rect.size.width), float(rect.size.height))
            for child in widget.children:
                yield from frames(child)
        return tuple(frames(self.row))

    def animate_split(self, before):
        if not before:
            return
        from rubicon.objc import ObjCClass, Block, CGRect
        # Pack updates Auto Layout constraints; flush them before reading target
        # frames, otherwise the animation sees the unchanged, pre-layout views.
        self.row._impl.container.native.layoutIfNeeded()
        # Interpolate the actual native
        # controls, including flattened descendants, rather than a Box snapshot.
        changes = []
        for native, previous in before:
            rect = native.frame
            target = (float(rect.origin.x), float(rect.origin.y),
                      float(rect.size.width), float(rect.size.height))
            if target != previous:
                changes.append((native, previous, target))
        if not changes:
            return
        for native, previous, target in changes:
            native.frame = CGRect(previous[:2], previous[2:])

        def animate():
            for native, previous, target in changes:
                native.frame = CGRect(target[:2], target[2:])
        self.split_animation = Block(animate, None)
        # BeginFromCurrentState + AllowUserInteraction: a reversal continues
        # from the visible geometry and never disables the source tabs.
        ObjCClass('UIView').animateWithDuration(.28, delay=0, options=(1 << 2) | (1 << 1),
            animations=self.split_animation, completion=None)

    def _render_split(self, left, opened):
        """Apply the fold-aware allocation to the two retained panes."""
        navigation, destination = self.navigation, self.destination
        view = self.view()
        margin = view.style.margin_left + view.style.margin_right if destination == 'files' else 24
        available = navigation.content_width(destination, margin=margin)
        from .fold_layout import division, has_fold
        from .pane_layout import panes
        fold = division(navigation.app, self.row)
        foldable = has_fold(navigation.app, self.row)
        priority = (destination == 'files' or opened) and (
            foldable or
            navigation.app.preferences.values.get('android_eink') == 'true')
        allocation = panes(available, self.row.layout.content_height or 1,
                           fold=fold, browser_priority=priority,
                           leading_fraction=.4 if priority and foldable else None)
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
            if right not in self.row.children:
                self.row.add(right)
            return
        if left not in self.row.children:
            self.row.insert(0, left)
