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


def menu_button(callback, label='Browse files'):
    button = toga.Button('☰', on_press=callback, style=Pack(width=44, height=44))
    if type(button._impl).__module__.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        button.text = ''
        button._impl.native.setImage(ObjCClass('UIImage').systemImageNamed('line.3.horizontal'), forState=0)
        button._impl.native.accessibilityLabel = label
    elif type(button._impl).__module__.startswith('toga_android.'):
        button._impl.native.setContentDescription(label)
    return button


def detach(widget):
    if widget.parent is not None:
        widget.parent.remove(widget)


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
        self.render()

    def uninstall(self):
        for frame in list(self.frames):
            frame.restore()
        self.last_layout = None

    def width(self):
        window = getattr(self.app, '_main_window', None)
        return window.size.width if window is not None else 0

    def content_width(self, destination):
        """Measure the native allocation, never a child-driven minimum width."""
        available = self.width()
        adapter = self.app.native_host.adapter
        if adapter is not None and hasattr(adapter, 'navigation'):
            index = self.app.native_host.destinations.index(destination)
            native = adapter.navigation[index].view
            bounds, insets = native.bounds.size, native.safeAreaInsets
            if bounds.width > 0:
                available = float(bounds.width - insets.left - insets.right)
        elif adapter is not None and getattr(adapter, 'mode', None) == 'rail':
            density = self.app._impl.native.getResources().getDisplayMetrics().density
            available -= float(adapter.impl.native_navigationview.getWidth()) / density
        return max(1, int(available) - 24)

    def prepare(self, view, destination, route=None, root=False):
        if destination not in self.menu_open:
            return view
        # Focused prompts and reader controls retain their own layout. Main
        # workspaces and each editor get a permanent top-left drawer control.
        eligible = (isinstance(view, toga.Box) and not getattr(view, '_reading_frame', False) and
                    (root or route in ('editor', 'browser', 'remote-browser')
                     or (route or '').startswith('private:')))
        if eligible and not hasattr(view, '_workspace_frame'):
            view._workspace_frame = WorkspaceFrame(self, view, destination)
            self.frames.add(view._workspace_frame)
        if root and isinstance(view, toga.ScrollContainer):
            content = view.content
            if not getattr(content, '_workspace_menu', False):
                content.insert(0, menu_button(lambda widget, **kw: self.show_browser(destination)))
                content._workspace_menu = True
        if route == 'preview' and isinstance(view, toga.Box) and not getattr(view, '_workspace_menu', False):
            view.insert(0, menu_button(lambda widget, **kw: self.show_browser(destination)))
            view._workspace_menu = True
        # Returning to a previously borrowed editor restores its single parent
        # before Routes attaches its native screen.
        for frame in list(self.frames):
            frame.restore()
        return view

    def browser(self, destination):
        if destination not in self.browsers:
            self.browsers[destination] = FileDrawer(self, destination)
        return self.browsers[destination]

    def toggle(self, destination):
        if not self.app.checkpoint():
            return
        self.app.mark_navigation()
        self.menu_open[destination] = not self.menu_open[destination]
        if self.menu_open[destination]:
            self.browser(destination).schedule_refresh()
        self.render()

    def show_browser(self, destination):
        if destination == 'documents' and self.session_view(self.app.workspace.active) is not None:
            self.app.session_opener(self.app.workspace.active)()
            body = self.app.routes.body('documents')
            view = body.children[0] if body.children else None
            if getattr(view, '_workspace_frame', None) is not None:
                self.menu_open[destination] = True
                self.browser(destination).schedule_refresh()
                self.render()
                return
        # The Documents overview is a scroll view rather than an editor pane.
        # Its drawer is an ordinary full-height route, never a modal sheet.
        drawer = self.browser(destination)
        detach(drawer.widget)
        box = toga.Box(children=[toga.Button('Close file browser', on_press=lambda widget, **kw:
            self.app.routes.back(), style=Pack(height=44)), drawer.widget],
            style=Pack(direction=COLUMN, flex=1, margin=12))
        self.app.show_view(box, destination=destination, route='workspace-browser', title='Browse files')
        drawer.schedule_refresh()

    def session_view(self, key):
        if key not in self.app.workspace.sessions:
            return None
        owner = self.app.text_views.get(key)
        if owner is not None:
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
            self.show_browser('documents')
        box.add(toga.Button('Browse for another file…', on_press=browse, style=Pack(height=48)))
        box.add(toga.Button('Use one document', on_press=self.unpin, style=Pack(height=44)))
        self.app.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)),
                           destination='documents', route='pair-document', title='Two documents')

    def unpin(self, widget=None, **kwargs):
        self.pinned = None
        self.app.routes.back()
        self.render()

    def render(self):
        if self.rendering:
            return
        self.rendering = True
        try:
            self.layout_width = self.width()
            self.wide = self.layout_width >= 640
            if self.pinned is not None and self.session_view(self.pinned) is None:
                self.pinned = None
            body = self.app.routes.body()
            view = body.children[0] if body.children else None
            frame = getattr(view, '_workspace_frame', None)
            layout = (id(frame), self.wide, self.layout_width, self.pinned,
                      tuple(self.menu_open.items()), frame.row.layout.content_width if frame else 0)
            if layout != self.last_layout:
                for item in list(self.frames):
                    item.restore()
                if frame is not None:
                    frame.render()
                self.last_layout = layout
            if hasattr(self.app, 'render_chat_workspace'):
                self.app.render_chat_workspace()
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
        self.menu = menu_button(lambda widget, **kw: navigation.toggle(destination))
        self.caption = toga.Label(destination.title(), style=Pack(flex=1, margin_top=10))
        self.header = toga.Box(children=[self.menu, self.caption], style=Pack(direction=ROW, margin_bottom=4))
        if destination == 'documents':
            self.pair = toga.Button('Split', on_press=navigation.show_pair_picker, style=Pack(height=44))
            self.header.add(self.pair)
        self.row = toga.Box(children=[self.main], style=Pack(direction=ROW, flex=1))
        view.add(self.header, self.row)

    def restore(self):
        self.main.style.flex = 1
        del self.main.style.width
        if list(self.row.children) == [self.main]:
            return
        for child in list(self.row.children):
            self.row.remove(child)
        detach(self.main)
        self.row.add(self.main)

    def render(self):
        navigation, destination = self.navigation, self.destination
        opened = navigation.menu_open[destination]
        self.caption.text = 'Browse files' if opened else destination.title()
        if hasattr(self, 'pair'):
            self.pair.enabled = navigation.wide and navigation.session_view(navigation.app.workspace.active) is not None
        left = None
        if opened:
            left = navigation.browser(destination).widget
        elif navigation.wide and destination == 'documents':
            view = navigation.session_view(navigation.pinned)
            if view is not None and view is not self.view():
                frame = getattr(view, '_workspace_frame', None)
                left = frame.main if frame else view
        if left is None:
            return
        detach(left)
        if not navigation.wide:
            self.row.remove(self.main)
            self.row.add(left)
        else:
            available = navigation.content_width(destination)
            half = max(1, int(available / 2))
            left.style.width, left.style.flex = half, 0
            self.main.style.width, self.main.style.flex = max(1, int(available) - half), 0
            self.row.insert(0, left)


class FileDrawer:
    """Independent browser state; opening never rewrites the Files tab's selection."""
    def __init__(self, navigation, destination):
        from .browser_ui import FileBrowser
        self.navigation, self.app, self.destination = navigation, navigation.app, destination
        self.roots = {'Local files': None}
        self.provider = None
        self.folder = ''
        self.generation = 0
        self.task = None
        self.refresh_requested = False
        self.storage = toga.Selection(items=['Local files'], style=Pack(height=44))
        self.status = toga.Label('', style=Pack(font_size=12, margin_bottom=4))
        self.browser = FileBrowser(selected=lambda row: None, open_folder=self.open_folder,
                                   navigate=self.navigate, open_file=self.open_file, preview=False)
        self.widget = toga.Box(children=[self.storage,
            toga.Button('Up', on_press=self.up, style=Pack(height=44)), self.status,
            toga.ScrollContainer(horizontal=False, content=scroll_content(self.browser.widget), style=Pack(flex=1)),
            toga.Button('Connections & folders', on_press=self.app.show_locations, style=Pack(height=44))],
            style=Pack(direction=COLUMN, flex=1))
        self.storage.on_change = self.change_storage

    def schedule_refresh(self):
        self.generation += 1
        self.refresh_requested = True
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
        self.schedule_refresh()

    async def refresh(self):
        self.generation += 1
        generation = self.generation
        roots = {'Local files': None}
        if not getattr(self.app, 'cloud_busy', False):
            roots.update(self.app.existing_crypt_locations())
            roots.update(self.app.linked_crypt_locations())
        selected = self.storage.value if self.storage.value in roots else 'Local files'
        self.changing_storage = True
        try:
            self.roots = roots
            self.storage.items = list(roots)
            self.storage.value = selected
        finally:
            self.changing_storage = False
        try:
            if selected != 'Local files' and self.app.cloud_busy:
                raise ValueError('This connection is busy. Local files remain available.')
            provider = self.app.storage_provider(selected, roots)
            model = ResourceSelection(provider)
            folder = self.folder
            rows = await asyncio.to_thread(model.list, folder)
            if (not self.app.active_host or generation != self.generation
                    or (selected, folder) != (self.storage.value, self.folder)):
                return False
            self.provider = provider
            self.browser.set_entries(model, folder, rows, location=(selected, folder))
            self.status.text = folder or selected
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
        from .file_resources import LocalTextCopies, ManagedCopies
        provider = self.provider
        if provider is None or not self.app.checkpoint():
            return
        path = row['path']
        try:
            if not provider.private and Path(path).suffix.lower() not in {'.txt', '.md', '.markdown'}:
                await self.app.open_download(path=provider._locate(path), destination=self.destination)
            else:
                self.app.show_cloud(present=False)
                opened = await self.app.open_crypt(copies=ManagedCopies(provider) if provider.private else LocalTextCopies(provider),
                                                  key=path, destination=self.destination)
                if not opened:
                    return False
            if self.app.native_host.state.destination == self.destination:
                if not self.navigation.wide:
                    self.navigation.menu_open[self.destination] = False
                self.navigation.render()
            return True
        except (OSError, ValueError) as error:
            self.status.text = str(error)[:160]
            return False
