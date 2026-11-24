"""Retained search routes and folder visits above their populated results."""

__author__ = 'Marc-André Voyer'
__license__ = 'MIT License'

import asyncio
from pathlib import PurePosixPath

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .control_icons import icon_button


class SearchRoute:
    """One close target; descendants pop back to this same result owner."""
    def __init__(self, app, content, *, destination=None, title='Search', retire=None):
        self.app = app
        self.destination = destination or app.native_host.state.destination
        self.base = len(app.routes.screens[self.destination])
        self.route = f'search:{id(self)}'
        self.active = True
        self.retire = retire
        self.close_button = icon_button('close', 'Exit search', on_press=self.close)
        header = toga.Box(children=[toga.Box(style=Pack(flex=1)), self.close_button],
                          style=Pack(direction=ROW))
        self.view = toga.Box(children=[header, content], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.view._search_route = self
        self.view._retire_search_route = self.dispose
        self.view._ios_toolbar_buttons = []
        self.view._ios_toolbar_leading = [self.close_button]
        self.view._ios_toolbar_replaces_back = True
        self.view._ios_toolbar_hidden = [header]
        self.view._ios_toolbar_overflow = False
        self.view._ios_toolbar_title = title

    def show(self):
        if self.app.show_view(self.view, destination=self.destination, route=self.route, title='Search') is False:
            self.dispose()
            return False
        return True

    def close(self, widget=None, **kwargs):
        if not self.active or not self.app.checkpoint():
            return
        self.app.routes.trim(self.destination, self.base)
        self.app.routes.render(self.destination)

    def dispose(self):
        if self.active:
            self.active = False
            if self.retire is not None:
                self.retire()


class FileSearchRoute(SearchRoute):
    def __init__(self, browser):
        self.browser = browser
        app = toga.App.app
        self.parent = browser.widget.parent
        self.index = list(self.parent.children).index(browser.widget) if self.parent is not None else 0
        self.scroll = browser.vertical_position
        self.open_folder = browser.on_open_folder
        self.actions, self.menu_provider = browser.on_item_actions, browser.native_list.menu_provider
        handler = browser.native_list.on_primary_action
        self.primary_action = getattr(handler, '_raw', handler)
        self.mode = browser.mode
        if self.parent is not None:
            self.parent.remove(browser.widget)
        browser.on_item_actions = None
        browser.native_list.menu_provider = None
        browser.native_list.on_primary_action = None
        browser.on_open_folder = self.visit_folder
        super().__init__(app, browser.widget, retire=self.restore)
        from .scroll_edges import fill_bottom
        fill_bottom(self.view, browser.native_list, browser._tile_scroll)
        browser._search_navigation = self
        browser._open_inline_search(standalone=True)
        # The route owns the sole X; remove the former inline close control.
        if browser.close_search_button.parent is not None:
            browser.close_search_button.parent.remove(browser.close_search_button)
        browser.search_panel.style.flex = 0
        browser.render()

    def show(self):
        if super().show():
            self.browser.search.focus()

    async def visit_folder(self, row):
        return await visit_folder(self.app, self.browser.search_provider, row['path'],
                                  self.browser.on_open_file, self.destination)

    def restore(self):
        browser = self.browser
        browser._search_navigation = None
        browser._close_inline_search()
        if browser.close_search_button.parent is None:
            browser.search_panel.add(browser.close_search_button)
        browser.on_open_folder = self.open_folder
        browser.on_item_actions = self.actions
        browser.native_list.menu_provider = self.menu_provider
        browser.native_list.on_primary_action = self.primary_action
        browser.mode = self.mode
        if browser.widget.parent is not None:
            browser.widget.parent.remove(browser.widget)
        if self.parent is not None:
            self.parent.insert(self.index, browser.widget)
        browser.render()
        browser.vertical_position = self.scroll


async def visit_folder(app, provider, path, open_file, destination):
    """Push a new folder owner; the search tree and query are never rewritten."""
    from .browser_ui import FileBrowser

    if not app.checkpoint():
        return False
    browser = FileBrowser(folder_visible=app.folder_path_visible, preview=False, open_file=open_file,
                          contextual_selection=False)
    browser.on_open_folder = lambda row: visit_folder(app, provider, row['path'], open_file, destination)
    # Search descendants use normal Back to their retained parent, not another
    # recursive search or a contextual-actions intermediary.
    generation = getattr(app, 'navigation_generation', None)
    try:
        rows = await asyncio.to_thread(provider.list, path)
    except (OSError, ValueError) as error:
        await browser.close()
        await app.main_window.dialog(toga.InfoDialog('Could not open folder', str(error)))
        return False
    if not app.active_host or generation != getattr(app, 'navigation_generation', None):
        await browser.close()
        return False
    browser.set_entries(provider, path, rows, location=('', path))
    base = len(app.routes.screens[destination])
    back = icon_button('back', 'Back to search' if base and app.routes.screens[destination][-1][0].startswith('search:')
                       else 'Parent folder', on_press=lambda widget: app.routes.back())
    title = toga.Label(PurePosixPath(path).name or 'Files', style=Pack(font_size=20, flex=1))
    header = toga.Box(children=[back, title], style=Pack(direction=ROW))
    if browser.navigation_controls.parent is not None:
        browser.navigation_controls.parent.remove(browser.navigation_controls)
    view = toga.Box(children=[header, browser.widget], style=Pack(direction=COLUMN, flex=1, margin=12))
    from .scroll_edges import fill_bottom
    fill_bottom(view, browser.native_list, browser._tile_scroll)
    view._search_folder = browser
    def retire():
        if not browser.closed:
            browser.stop()
            app.loop.create_task(browser.close())
    view._retire_search_route = retire
    view._ios_toolbar_buttons = []
    view._ios_toolbar_hidden = [header]
    view._ios_toolbar_title = title.text
    app.show_view(view, destination=destination, route=f'search-folder:{id(view)}', title=title.text)
    return True


async def visit_document_folder(app, hit):
    from .file_items import _resolve_reference
    from services.documents.mobile_storage import open_provider_document

    item, release = await asyncio.to_thread(_resolve_reference, app, hit['source'])
    provider = item.provider
    destination = app.native_host.state.destination
    async def open_file(row):
        return await open_provider_document(app, provider, row['path'], destination=destination)
    try:
        return await visit_folder(app, provider, item.path, open_file, destination)
    finally:
        release()
