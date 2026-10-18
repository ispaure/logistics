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
from commonUtils.ui.native.presentation import list_button, scroll_content
from .adaptive_workspace import AdaptiveWorkspace
from .files_ui import local_read_available
from .navigation import DESTINATION_ITEMS

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
        configuration = ObjCClass('UIButtonConfiguration')
        if configuration.respondsToSelector(SEL('glassButtonConfiguration')):
            config = configuration.glassButtonConfiguration()
        else:
            config = configuration.grayButtonConfiguration()
        config.cornerStyle = 4  # capsule
        native.configuration = config
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


class WorkspaceNavigation(AdaptiveWorkspace):
    def __init__(self, app):
        super().__init__(app)
        self.frames = weakref.WeakSet()
        self.browsers = {}
        self.menu_open = dict(files=False, documents=False)
        self.pinned = None
        self.rendering = False
        self.last_layout = None

    def install(self):
        # Both Apple and Android use the same measured content split, inside
        # their existing native navigation controller, including compact Back.
        adapter = self.app.native_host.adapter
        if adapter is not None and hasattr(adapter, 'navigation'):
            # Brand the page title while preserving Home as the tab label.
            home = adapter.navigation[self.app.native_host.destinations.index('home')]
            home.topViewController.navigationItem.title = 'Logistics'
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
        if destination not in self.menu_open:
            return view
        if root and isinstance(view, toga.ScrollContainer):
            original = view
            view = toga.Box(children=[original], style=Pack(direction=COLUMN, flex=1))
            # Keep the overview's content available to its existing callers.
            view.content = original.content
        # Focused prompts and reader controls retain their own layout. Main
        # workspaces and each editor get a permanent top-left drawer control.
        eligible = (isinstance(view, toga.Box) and not getattr(view, '_reading_frame', False) and
                    (root or route in ('editor', 'browser', 'remote-browser', 'folder-options', 'workspace-browser')
                     or (route or '').startswith('private:')))
        if eligible and not hasattr(view, '_workspace_frame'):
            view._workspace_frame = WorkspaceFrame(self, view, destination)
            view._workspace_frame.folder_options = route == 'folder-options'
            self.frames.add(view._workspace_frame)
        if route == 'preview' and isinstance(view, toga.Box) and not getattr(view, '_workspace_menu', False):
            menu = menu_button(lambda widget, **kw: self.show_browser(destination))
            view.insert(0, menu)
            view._workspace_menu_button = menu
            view._workspace_menu = True
        menu = getattr(view, '_workspace_menu_button', None)
        if menu is not None and self.app.routes.apple:
            detach(menu)
        # Returning to a previously borrowed editor restores its single parent
        # before Routes attaches its native screen.
        for frame in list(self.frames):
            frame.restore()
        # Reparenting invalidates even an otherwise identical layout tuple.
        self.last_layout = None
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
        self.render()
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
        detach(drawer.widget)
        box = toga.Box(children=[toga.Button('Close file browser', on_press=lambda widget, **kw:
            self.app.routes.back(), style=Pack(height=48)), drawer.widget],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        self.app.show_view(box, destination=destination, route='workspace-browser', title='Browse files')
        drawer.schedule_refresh()

    def session_view(self, key):
        if key not in self.app.workspace.sessions:
            return None
        owner = self.app.text_views.get(key)
        if owner is not None:
            if owner.session.view.get('markdown_mode') == 'preview' and owner.preview_box is not None:
                return owner.preview_box
            return owner.document_view
        private = getattr(self.app, 'private_sessions', None)
        owner = private.controllers.get(key) if private else None
        if owner is not None and owner.crypt_reader is not None and owner.crypt_reader.editable:
            return owner.crypt_view
        return None

    def focus_session(self, key):
        current = self.app.workspace.active
        if self.pinned == key and current != key and self.session_view(current) is not None:
            self.pinned = current

    def show_pair_picker(self, widget=None, **kwargs):
        current = self.app.workspace.active
        if self.session_view(current) is None or not self.app.checkpoint():
            return
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Open beside this document', style=Pack(font_size=20, margin_bottom=12)))
        for key, session in self.app.workspace.sessions.items():
            if key == current or (session.provider != 'managed-text' and self.session_view(key) is None):
                continue
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

    def render(self, destination=None):
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
            if self.pinned is not None and self.session_view(self.pinned) is None:
                self.pinned = None
            body = self.app.routes.body(destination)
            view = body.children[0] if body.children else None
            frame = getattr(view, '_workspace_frame', None)
            layout = (id(frame), self.wide, self.layout_width, self.pinned,
                      tuple(self.menu_open.items()), frame.row.layout.content_width if frame else 0)
            if layout != self.last_layout:
                transition = frame.begin_transition() if frame is not None else None
                for item in list(self.frames):
                    item.restore()
                if frame is not None:
                    frame.render()
                    frame.finish_transition(transition)
                self.last_layout = layout
            if frame is not None:
                frame.sync_native_header()
            elif view is not None and self.app.routes.apple:
                menu = getattr(view, '_workspace_menu_button', None)
                if menu is not None:
                    mount_native_menu(self.app, menu, destination or self.app.native_host.state.destination)
            if hasattr(self.app, 'render_chat_workspace'):
                self.app.render_chat_workspace()
            from .appearance import reserve_navigation
            reserve_navigation(self.app)
            if hasattr(self.app, 'home_content'):
                self.app.reflow_home()
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
        self.header = toga.Box(children=[self.menu, self.caption], style=Pack(direction=ROW, margin_bottom=4))
        if destination == 'documents':
            self.pair = toga.Button('Split', on_press=navigation.show_pair_picker, style=Pack(height=48))
            self.header.add(self.pair)
        self.row = toga.Box(children=[self.main], style=Pack(direction=ROW, flex=1))
        if destination != 'files':
            view.add(self.header)
        view.add(self.row)

    def restore(self):
        self.compact_open = False
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
        self.menu.app, self.menu.window = app, app.main_window
        item = controller.navigationItem
        item.leftItemsSupplementBackButton = True
        self.native_menu = mount_native_menu(app, self.menu, self.destination)
        # Folder Hub enters browsers through its folder actions. Keep the drawer
        # implementation available without mounting a menu in this destination.
        item.leftBarButtonItem = self.native_menu if self.destination != 'files' else None
        if hasattr(self, 'pair'):
            self.pair.app, self.pair.window = app, app.main_window
            if not hasattr(self, 'native_pair'):
                self.native_pair = ObjCClass('UIBarButtonItem').alloc().initWithTitle(
                    'Split', style=0, target=self.pair._impl.native, action=SEL('onPress:'))
            self.native_pair.enabled = self.pair.enabled
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
        elif navigation.wide and destination == 'files' and getattr(self, 'folder_options', False):
            if not hasattr(self, 'folder_master'):
                self.folder_master = navigation.app.build_folder_picker(
                    choices=navigation.app.folder_picker_choices)
                # The action page already supplies the outer twelve-point inset.
                self.folder_master.style.margin = 0
            left = self.folder_master
        elif navigation.wide and destination == 'documents':
            view = navigation.session_view(navigation.pinned)
            if view is not None and view is not self.view():
                frame = getattr(view, '_workspace_frame', None)
                left = frame.main if frame else view
        if left is None:
            return
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
            available = navigation.content_width(destination)
            half = max(1, int(available / 2))
            left.style.width, left.style.flex = half, 0
            self.main.style.width, self.main.style.flex = max(1, int(available) - half), 0
            self.row.insert(0, left)


class FileDrawer:
    """Independent browser state; opening never rewrites the Folder Hub tab's selection."""
    def __init__(self, navigation, destination):
        from .browser_ui import FileBrowser
        self.navigation, self.app, self.destination = navigation, navigation.app, destination
        self.roots = {'Local files': None}
        self.provider = None
        self.extensions = None
        self.folder = ''
        self.generation = 0
        self.task = None
        self.refresh_requested = False
        self.storage = toga.Selection(items=['Local files'], style=Pack(height=48))
        self.status = toga.Label('', style=Pack(font_size=12, margin_bottom=4))
        self.browser = FileBrowser(folder_visible=self.app.folder_path_visible, selected=lambda row: None, open_folder=self.open_folder,
                                   navigate=self.navigate, open_file=self.open_file, preview=False)
        self.browser.navigation_controls.remove(self.browser.back_button)
        self.parent_button = toga.Button('Parent folder', on_press=self.up, enabled=False, style=Pack(height=48))
        self.breadcrumb = toga.Label('Local', style=Pack(font_size=13, flex=1))
        self.widget = toga.Box(children=[self.storage,
            toga.Box(children=[self.parent_button, self.breadcrumb], style=Pack(direction=ROW)), self.status,
            toga.ScrollContainer(horizontal=False, content=scroll_content(self.browser.widget), style=Pack(flex=1)),
            toga.Button('Folder Hub', on_press=self.app.show_locations, style=Pack(height=48))],
            style=Pack(direction=COLUMN, flex=1))
        self.browser_widget = self.widget
        if destination == 'documents':
            self.menu_content = toga.Box(style=Pack(direction=COLUMN, margin=12))
            self.widget = toga.ScrollContainer(horizontal=False, content=self.menu_content, style=Pack(flex=1))
        self.storage.on_change = self.change_storage

    async def show_main_browser(self, storage, *, folder='', extensions=None, title='Browse files', provider=None):
        if not self.app.checkpoint():
            return False
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
        self.app.show_view(page, destination=self.destination, route='workspace-browser', title=title)
        return await self.refresh()

    def refresh_menu(self):
        from .hub_ui import heading
        for child in list(self.menu_content.children):
            self.menu_content.remove(child)
        # The tap path only renders cached results. Native rclone calls run
        # in refresh() on a worker after the drawer is already visible.
        roots = self.roots
        for storage in roots:
            remote = getattr(roots[storage], 'remote', '') or storage.removeprefix('LocalCrypt: ')
            if not self.app.folder_path_visible(remote):
                continue
            async def browse(widget=None, selected=storage, **kwargs):
                await self.show_main_browser(selected)
            label = 'LocalCrypt: ' + roots[storage].remote if getattr(roots[storage], 'remote', '') else storage
            title = 'Browse Local Files' if storage == 'Local files' else 'Browse ' + label
            self.menu_content.add(list_button(toga.Button(title, on_press=browse, style=Pack(height=48))))
        self.menu_content.add(heading('Recent'))
        self.recent_buttons = []
        for session in self.app.recent_documents.sessions():
            title, kind, details = self.app.session_summary(session)
            if 'Unavailable; retry to reopen' in details:
                continue
            async def reopen(widget=None, selected=session, **kwargs):
                if not self.app.checkpoint():
                    return
                self.navigation.menu_open['documents'] = False
                if selected.provider == 'library':
                    await self.app.open_book(selected.resource)
                elif self.app.open_document(selected.resource):
                    self.app.show_documents(resume=True)
            button = list_button(toga.Button(title, on_press=reopen, style=Pack(height=48)))
            self.recent_buttons.append(button)
            self.menu_content.add(button)
        if not self.recent_buttons:
            self.menu_content.add(toga.Label('No recent documents yet.'))
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
        self.menu_content.add(heading('Shortcuts'))
        for title, extension in (('New text document', 'txt'), ('New Markdown document', 'md')):
            def create(widget=None, selected=extension, **kwargs):
                self.navigation.menu_open['documents'] = False
                self.app.create_chosen_document(selected)
            self.menu_content.add(toga.Button(title, on_press=create, style=Pack(height=48)))
        self.menu_content.add(toga.Button('Folder Hub', on_press=self.app.show_locations, style=Pack(height=48)))


    def schedule_refresh(self):
        self.generation += 1
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
        self.generation += 1
        generation = self.generation
        try:
            roots = await asyncio.to_thread(self.available_roots)
        except (OSError, ValueError) as error:
            # A failed credential query must not strand the menu refresh task.
            # Keep Local files usable and report the connection error in-place.
            if generation != self.generation or not self.app.active_host:
                return False
            self.status.text = str(error)[:160]
            return False
        if generation != self.generation or not self.app.active_host:
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
            client = getattr(self.app, 'cloud_client', None)
            credential_generation = getattr(client, 'generation', None)
            model = ResourceSelection(provider, extensions=self.extensions or ())
            folder = self.folder
            rows = await asyncio.to_thread(model.list, folder)
            if (not self.app.active_host or generation != self.generation
                    or (selected, folder) != (self.storage.value, self.folder)):
                return False
            if provider.private and (client is not self.app.cloud_client
                    or credential_generation != getattr(client, 'generation', None)):
                raise ValueError('Unlock the library connection again.')
            self.provider = provider
            self.provider_client = getattr(self.app, 'cloud_client', None)
            self.provider_generation = getattr(self.provider_client, 'generation', None)
            self.browser.set_entries(model, folder, rows, location=(selected, folder))
            from textwrap import fill
            self.breadcrumb.text = fill(folder.replace('/', ' / ') or 'Root', width=28)
            self.parent_button.enabled = bool(folder)
            self.status.text = ''
            if self.destination == 'documents':
                self.refresh_menu()
                catalog = self.app.reader_manager().catalog
                await catalog.refresh_library_folders()
                if generation == self.generation and self.app.active_host:
                    self.refresh_menu()
            return True
        except (OSError, ValueError) as error:
            self.provider = None
            self.browser.stop()
            self.status.text = str(error)[:160]
            return False

    async def open_folder(self, row):
        self.folder = row['path']
        return await self.refresh()

    async def navigate(self, location):
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
                await self.app.open_download(path=provider._locate(path), destination=self.destination)
            else:
                self.app.show_cloud(present=False)
                source = encrypted_document(provider, path)
                copies, key = source if source is not None else (LocalTextCopies(provider), path)
                opened = await self.app.open_crypt(copies=copies, key=key, destination=self.destination)
                if not opened:
                    self.status.text = str(self.app.cloud_status.value or 'Could not open this private file. Unlock its connection and try again.')[:300]
                    return False
            if self.app.native_host.state.destination == self.destination:
                if not self.navigation.wide:
                    self.navigation.menu_open[self.destination] = False
                self.navigation.render()
            return True
        except (OSError, ValueError) as error:
            self.status.text = str(error)[:160]
            return False
