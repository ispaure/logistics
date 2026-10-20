"""Folder ancestry in UIKit's destination-local navigation stacks."""
import asyncio
from dataclasses import dataclass
from pathlib import PurePosixPath

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.routes import Routes


@dataclass
class FolderScreen:
    view: object
    browser: object
    navigate: object
    source: str
    path: str
    kind: str
    query: str = ''
    selected: object = None
    scroll: int = 0
    preview: object = None
    snapshot: object = None
    base: int = 0
    scope: str = ''
    root_title: str = ''

    def __post_init__(self):
        provider = getattr(self.browser, 'search_provider', None)
        provider = getattr(provider, 'provider', provider)
        if getattr(provider, 'private', False) and not getattr(provider, 'remote_storage', False):
            self.root_title = getattr(provider, 'remote', self.source)
        else:
            self.root_title = self.source

    @property
    def title(self):
        return PurePosixPath(self.path).name if self.path else self.root_title

    @property
    def route(self):
        return f'folder:{self.kind}:{self.scope}:{self.source!r}:{self.path!r}'


class FolderPreview:
    """Read-only parent contents, ready before UIKit begins an interactive pop."""
    def __init__(self, app, entry, *, captured=False):
        from .browser_ui import FileBrowser
        self.app, self.entry = app, entry
        self.provider = entry.browser.search_provider
        owner = getattr(self.provider, 'provider', self.provider)
        self.private = entry.kind == 'remote-browser' or getattr(owner, 'private', False)
        self.client = getattr(app, 'cloud_client', None)
        self.generation = getattr(self.client, 'generation', None)
        self.browser = FileBrowser(folder_visible=app.folder_path_visible, preview=False)
        self.status = self.browser.status_label('Opening folder…')
        parent = toga.Button('')
        header = self.browser.attach_location_header(self.status, parent)
        header.remove(parent)
        header.use_native_title()
        self.browser.search_button.enabled = False
        header.update_provider(entry.path, owner, name=entry.title)
        if entry.kind == 'remote-browser':
            source_header = entry.browser.location_bar
            remote, encrypted, unlocked, session_only = source_header._identity_key
            header.update(entry.path, remote=remote, encrypted=encrypted, unlocked=unlocked,
                          session_only=session_only, name=entry.title)
        self.view = toga.Box(children=[header, self.browser.scroll_container()],
                             style=Pack(direction=COLUMN, flex=1, margin=12))
        self.sidebar_snapshot = None
        frame = getattr(entry.view, '_workspace_frame', None)
        sidebar = getattr(frame, 'folder_master', None)
        if sidebar is not None and app.adaptive.wide:
            from toga.style.pack import ROW
            content = self.view
            content.style.margin = 0
            content.style.margin_left = 16
            left = toga.Box(style=Pack(width=sidebar.style.width, flex=0))
            self.view = toga.Box(children=[left, content], style=Pack(direction=ROW, flex=1, margin=12))
            self.sidebar_snapshot = native_snapshot(sidebar)
            if self.sidebar_snapshot is not None:
                left._impl.native.addSubview(self.sidebar_snapshot)
                self.sidebar_snapshot.frame = left._impl.native.bounds
        self.task = None
        if captured:
            # Keep an actual list in the parent controller before the live
            # browser moves into its child. No disk/network refresh is needed.
            self.browser.mode = entry.browser.mode
            self.browser.search.on_change = None
            self.browser.search.value = entry.query
            self.browser.sort.value = entry.browser.sort.value
            self.browser.set_tree(entry.browser.tree)
            self.browser.selected = entry.selected
            self.browser.highlight_selection()
            self.status.value = ''
        else:
            self.task = app.loop.create_task(self.prepare())

    async def prepare(self):
        try:
            if hasattr(self.provider, 'list'):
                rows = await asyncio.to_thread(self.provider.list, self.entry.path)
            elif self.entry.kind == 'remote-browser':
                rows = await asyncio.to_thread(self.client.entries, self.entry.source, self.entry.path)
                rows = [dict(row, name=PurePosixPath(row['path']).name, modified='') for row in rows]
            else:
                return
            if (not self.app.active_host or (self.private and (
                    self.client is not getattr(self.app, 'cloud_client', None)
                    or self.generation != getattr(self.client, 'generation', None)))):
                return
            self.browser.set_entries(self.provider, self.entry.path, rows)
            self.status.value = ''
        except (OSError, ValueError, AttributeError):
            self.status.value = 'Return to this folder to refresh.'

    def close(self):
        if self.task is not None:
            self.task.cancel()
        if self.sidebar_snapshot is not None:
            self.sidebar_snapshot.removeFromSuperview()
            self.sidebar_snapshot = None
        self.browser.stop()
        self.app.loop.create_task(self.browser.close())


def native_snapshot(panel):
    if not type(panel._impl).__module__.startswith('toga_iOS.'):
        return None
    native = panel._impl.native
    if native.bounds.size.width <= 0 or native.bounds.size.height <= 0:
        return None
    native.layoutIfNeeded()
    snapshot = native.snapshotViewAfterScreenUpdates(False)
    if snapshot is not None:
        snapshot.frame = native.bounds
        snapshot.autoresizingMask = 18  # flexible width and height
        snapshot.userInteractionEnabled = False
    return snapshot


def clear_snapshot(entry):
    if entry.snapshot is not None:
        entry.snapshot.removeFromSuperview()
        entry.snapshot = None


def record(app, view, browser, kind, source, path, navigate):
    """Publish only successfully loaded locations; failed listings keep the stack."""
    view._folder_screen = FolderScreen(view, browser, navigate, source, path, kind,
                                      base=getattr(view, '_folder_return_count', 0),
                                      scope=getattr(view, '_folder_scope', ''))
    routes = getattr(app, 'routes', None)
    if routes is None or not routes.apple or routes.folders.restoring:
        return
    destination = app.native_host.state.destination
    if destination in ('files', 'home') and view in routes.body(destination).children:
        routes.show(view, destination=destination, route=kind)


class FolderNavigation:
    def __init__(self, routes):
        self.routes = routes
        self.screens = {}
        self.restoring = 0
        self.task = None

    def capture_viewport(self, destination=None):
        destination = destination or self.routes.host.state.destination
        screens = self.routes.screens[destination]
        entry = self.screens.get((destination, screens[-1][0])) if screens else None
        if entry is None or entry.view not in screens[-1][1].children:
            return
        entry.query = entry.browser.search.value
        entry.selected = entry.browser.selected
        scroll = getattr(entry.browser, '_scroll', None)
        entry.scroll = scroll.vertical_position if scroll is not None else 0

    def restore_viewport(self, destination, expected=None):
        screens = self.routes.screens[destination]
        if not screens or (expected is not None and screens[-1][0] != expected):
            return
        entry = self.screens.get((destination, screens[-1][0]))
        if entry is None or entry.view not in screens[-1][1].children:
            return
        scroll = getattr(entry.browser, '_scroll', None)
        if scroll is not None:
            scroll.vertical_position = min(entry.scroll, scroll.max_vertical_position)

    def capture(self):
        routes = self.routes
        destination = routes.host.state.destination
        screens = routes.screens[destination]
        entry = self.screens.get((destination, screens[-1][0])) if screens else None
        if entry is not None:
            clear_snapshot(entry)
            entry.snapshot = native_snapshot(screens[-1][1])
            entry.query = entry.browser.search.value
            entry.selected = entry.browser.selected
            scroll = getattr(entry.browser, '_scroll', None)
            entry.scroll = scroll.vertical_position if scroll is not None else 0
            if getattr(entry.browser, 'tree', None) is not None:
                if entry.preview is not None:
                    entry.preview.close()
                entry.preview = FolderPreview(routes.app, entry, captured=True)

    def forget(self, destination, route):
        entry = self.screens.pop((destination, route), None)
        if entry is not None:
            clear_snapshot(entry)
            if entry.preview is not None:
                entry.preview.close()

    def invalidate_private(self):
        for entry in self.screens.values():
            provider = getattr(entry.browser, 'search_provider', None)
            owner = getattr(provider, 'provider', provider)
            if entry.kind != 'remote-browser' and not getattr(owner, 'private', False):
                continue
            clear_snapshot(entry)
            if entry.preview is not None:
                entry.preview.close()
                entry.preview.status.value = 'Connection locked. Reopen this folder.'

    def present(self, info, destination):
        routes = self.routes
        if self.restoring and self.task is not None:
            self.task.cancel()
        # The browser has one native widget owner. Ancestor controllers retain
        # locations and receive that view when Back or an interactive pop lands.
        if info.view.parent is not None:
            info.view.parent.remove(info.view)
        paths = ['']
        for part in PurePosixPath(info.path).parts:
            paths.append('/'.join(filter(None, (paths[-1], part))))
        entry_source, entry_path = getattr(info.view, '_folder_entry_location', (None, None))
        if entry_source == info.source and entry_path in paths:
            paths = paths[paths.index(entry_path):]
        desired = [FolderScreen(info.view, info.browser, info.navigate, info.source, path, info.kind,
                               base=info.base, scope=info.scope)
                   for path in paths]
        screens = routes.screens[destination]
        # A workspace shortcut returns directly to the overview. Only folders
        # below its entry point belong in this navigation stack.
        keep = info.base
        for entry, screen in zip(desired, screens[info.base:]):
            if entry.route != screen[0]:
                break
            keep += 1
        if keep < len(screens):
            routes.trim(destination, keep)
        for entry in desired:
            if entry.path == info.path:
                self.forget(destination, entry.route)
            if (destination, entry.route) not in self.screens:
                self.screens[destination, entry.route] = entry
            else:
                retained = self.screens[destination, entry.route]
                retained.view, retained.browser, retained.navigate = info.view, info.browser, info.navigate
            title = entry.title
            retained = self.screens[destination, entry.route]
            if entry.path == info.path:
                view = info.view
            elif entry.route not in [screen[0] for screen in routes.screens[destination]]:
                if hasattr(info.browser, 'search_provider'):
                    retained.preview = FolderPreview(routes.app, retained)
                    view = retained.preview.view
                else:
                    view = toga.Box(children=[toga.Label('Opening folder…')], style=Pack(flex=1))
            else:
                view = None
            if entry.route in [screen[0] for screen in routes.screens[destination]]:
                if entry.path == info.path:
                    Routes.show(routes, view, destination=destination, route=entry.route, title=title)
                elif retained.preview is not None:
                    panel = next(panel for route, panel, _ in routes.screens[destination]
                                 if route == entry.route)
                    if not panel.children:
                        panel.add(retained.preview.view)
                        panel.refresh()
                        retained.preview.browser.vertical_position = retained.scroll
                continue
            Routes.show(routes, view, destination=destination, route=entry.route, title=title)
        for route, panel, _ in routes.screens[destination]:
            retained = self.screens.get((destination, route))
            if retained is not None and retained.snapshot is not None:
                if retained.path != info.path:
                    panel._impl.native.addSubview(retained.snapshot)
                else:
                    clear_snapshot(retained)
        from .folder_title import mount
        for route, _, container in routes.screens[destination]:
            retained = self.screens.get((destination, route))
            if retained is None or container is None:
                continue
            browser = (retained.preview.browser if retained.preview is not None
                       and retained.path != info.path else retained.browser)
            header = getattr(browser, 'location_bar', None)
            if header is not None:
                title = retained.title
                mount(header, container.controller, title)
        header = getattr(info.browser, 'location_bar', None)
        if header is not None:
            if header.parent_button in header.children:
                header.remove(header.parent_button)
            native_title = getattr(header, 'use_native_title', None)
            if native_title is not None:
                native_title()

    def restore(self, destination):
        routes = self.routes
        screens = routes.screens[destination]
        if not screens:
            return
        entry = self.screens.get((destination, screens[-1][0]))
        if entry is None:
            return
        def mount_live_header():
            header = getattr(entry.browser, 'location_bar', None)
            container = screens[-1][2]
            if header is not None and container is not None:
                from .folder_title import mount
                mount(header, container.controller, entry.title)
        if entry.view in screens[-1][1].children:
            mount_live_header()
            self.restore_viewport(destination)
            return
        if self.task is not None and not self.task.done():
            self.task.cancel()
        panel = screens[-1][1]
        # Keep the retained parent preview visible throughout the transition
        # and the fresh listing; never replace it with an empty controller.
        loading = toga.Label('Opening folder…')
        expected = screens[-1][0]

        async def load():
            self.restoring += 1
            try:
                entry.browser.search.value = ''
                opened = await entry.navigate((entry.source, entry.path))
                if (not routes.app.active_host or not screens or screens[-1][0] != expected):
                    return
                if opened is False:
                    clear_snapshot(entry)
                    for child in list(panel.children):
                        panel.remove(child)
                    loading.text = 'Could not open folder. Go Back and try again.'
                    panel.add(loading)
                    return
                if entry.view.parent is not None:
                    entry.view.parent.remove(entry.view)
                entry.browser.search.value = entry.query
                selected = next((item for item in entry.browser.entries if item.identity == entry.selected), None)
                if selected is not None:
                    await entry.browser.select(selected)
                for child in list(panel.children):
                    panel.remove(child)
                panel.add(entry.view)
                clear_snapshot(entry)
                if routes.host.state.destination == destination:
                    routes.render(destination)
                mount_live_header()
                self.restore_viewport(destination, expected)
            except (OSError, ValueError, KeyError):
                clear_snapshot(entry)
                for child in list(panel.children):
                    panel.remove(child)
                panel.add(loading)
                loading.text = 'Could not open folder. Go Back and try again.'
            finally:
                self.restoring -= 1
        self.task = routes.app.loop.create_task(load())
