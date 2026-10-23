"""Retained destination browser, independent from pane layout and native chrome.

Navigation owns routes, open state and widget placement. Each drawer retains its
provider, listing request and captured credentials even while its widget is
unmounted or moved between compact and split layouts. FolderListing admits late
results; restoring a frame does not recreate or cancel the drawer.
"""
import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.resources.selection import ResourceSelection

from .appearance import list_button
from .files_ui import local_read_available


def detach(widget):
    if widget.parent is not None:
        widget.parent.remove(widget)



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

    def main_browser_visible(self):
        from .routes import contains
        return (self.destination != 'files' and hasattr(self, 'page')
                and contains(self.page, self.browser_widget))

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
                main_browser = self.main_browser_visible()
                self.parent_button.enabled = bool(folder) or main_browser
                if main_browser and not folder:
                    from .control_icons import apply_icon
                    apply_icon(self.parent_button, 'back', 'Back')
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
        if not self.folder and self.main_browser_visible():
            self.cancel_browser()
            return True
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

