"""Folder ancestry in UIKit's destination-local navigation stacks."""
from dataclasses import dataclass
from pathlib import PurePosixPath

import toga
from toga.style import Pack
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

    @property
    def route(self):
        return f'folder:{self.kind}:{self.source!r}:{self.path!r}'


def record(app, view, browser, kind, source, path, navigate):
    """Publish only successfully loaded locations; failed listings keep the stack."""
    view._folder_screen = FolderScreen(view, browser, navigate, source, path, kind)
    routes = getattr(app, 'routes', None)
    if routes is None or not routes.apple or routes.folders.restoring:
        return
    destination = app.native_host.state.destination
    if destination == 'files' and view in routes.body(destination).children:
        routes.show(view, destination=destination, route=kind)


class FolderNavigation:
    def __init__(self, routes):
        self.routes = routes
        self.screens = {}
        self.restoring = 0
        self.task = None

    def capture(self):
        routes = self.routes
        destination = routes.host.state.destination
        screens = routes.screens[destination]
        entry = self.screens.get((destination, screens[-1][0])) if screens else None
        if entry is not None:
            entry.query = entry.browser.search.value
            entry.selected = entry.browser.selected
            scroll = getattr(entry.browser, '_scroll', None)
            entry.scroll = scroll.vertical_position if scroll is not None else 0

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
        desired = [FolderScreen(info.view, info.browser, info.navigate, info.source, path, info.kind)
                   for path in paths]
        screens = routes.screens[destination]
        # Storage root returns directly to the Workspaces overview, including
        # entry through a pinned folder's options screen.
        keep = 0
        for entry, screen in zip(desired, screens):
            if entry.route != screen[0]:
                break
            keep += 1
        if keep < len(screens):
            routes.trim(destination, keep)
        for entry in desired:
            if (destination, entry.route) not in self.screens or entry.path == info.path:
                self.screens[destination, entry.route] = entry
            title = PurePosixPath(entry.path).name if entry.path else entry.source
            view = info.view if entry.path == info.path else toga.Box(style=Pack(flex=1))
            if entry.route in [screen[0] for screen in routes.screens[destination]]:
                if entry.path == info.path:
                    Routes.show(routes, view, destination=destination, route=entry.route, title=title)
                continue
            Routes.show(routes, view, destination=destination, route=entry.route, title=title)
        header = getattr(info.browser, 'location_bar', None)
        if header is not None and header.parent_button in header.children:
            header.remove(header.parent_button)

    def restore(self, destination):
        routes = self.routes
        screens = routes.screens[destination]
        if not screens:
            return
        entry = self.screens.get((destination, screens[-1][0]))
        if entry is None or entry.view in screens[-1][1].children:
            return
        if self.task is not None and not self.task.done():
            self.task.cancel()
        panel = screens[-1][1]
        for child in list(panel.children):
            panel.remove(child)
        # Avoid showing the child folder under its parent's title while loading.
        loading = toga.Label('Opening folder…')
        panel.add(loading)
        expected = screens[-1][0]

        async def load():
            self.restoring += 1
            try:
                entry.browser.search.value = ''
                opened = await entry.navigate((entry.source, entry.path))
                if (not routes.app.active_host or not screens or screens[-1][0] != expected):
                    return
                if opened is False:
                    loading.text = 'Could not open folder. Go Back and try again.'
                    return
                if entry.view.parent is not None:
                    entry.view.parent.remove(entry.view)
                entry.browser.search.value = entry.query
                selected = next((item for item in entry.browser.entries if item.identity == entry.selected), None)
                if selected is not None:
                    await entry.browser.select(selected)
                panel.remove(loading)
                panel.add(entry.view)
                scroll = getattr(entry.browser, '_scroll', None)
                if scroll is not None:
                    scroll.vertical_position = min(entry.scroll, scroll.max_vertical_position)
                if routes.host.state.destination == destination:
                    routes.render(destination)
            except (OSError, ValueError, KeyError):
                loading.text = 'Could not open folder. Go Back and try again.'
            finally:
                self.restoring -= 1
        self.task = routes.app.loop.create_task(load())
