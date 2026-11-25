"""Retained destination browser, independent from pane layout and native chrome.

Navigation owns routes, open state and widget placement. Each drawer retains its
provider, listing request and captured credentials even while its widget is
unmounted or moved between compact and split layouts. FolderListing admits late
results; restoring a frame does not recreate or cancel the drawer.
"""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW
from commonUtils.runtime.resources.selection import ResourceSelection

from .ui_metrics import TOUCH_TARGET
from .appearance import list_button
from .browser_location import browser_command
from .files_ui import FileSelectionUI, local_read_available


def detach(widget):
    if widget.parent is not None:
        widget.parent.remove(widget)



class FileDrawer(FileSelectionUI):
    """Independent browser state; opening never rewrites the Workspaces tab's selection."""
    def __init__(self, navigation, destination):
        from .browser_ui import FileBrowser
        from .file_browser_view import LocalFileBrowser
        self.navigation, self.app, self.destination = navigation, navigation.app, destination
        self.roots = {'Local files': None}
        self.provider = None
        self.extensions = None
        self.folder = ''
        self.library_root = None
        self.generation = 0
        self.task = None
        self.refresh_requested = False
        from .folder_listing import FolderListing
        self.listing = FolderListing(active=lambda: self.app.active_host,
            context=lambda: (self.generation, id(self.browser)),
            location=lambda: (self.storage.value, self.folder),
            credentials=lambda: (getattr(self.app, 'cloud_client', None),
                getattr(getattr(self.app, 'cloud_client', None), 'generation', None)))
        self.storage = toga.Selection(items=['Local files'], style=Pack(height=TOUCH_TARGET))
        browser_type = LocalFileBrowser if destination == 'documents' else FileBrowser
        self.browser = browser_type(folder_visible=self.app.folder_path_visible, selected=lambda row: None,
                                    open_folder=self.open_folder, navigate=self.navigate,
                                    open_file=self.open_file, preview=False)
        self.browser.install_item_commands(lambda row: self.app.file_item_actions(self.provider, row))
        self.status = self.browser.status_label('')
        self.parent_button = browser_command(toga.Button('Parent folder', on_press=self.up,
                                                       enabled=False, style=Pack(height=TOUCH_TARGET)))
        header = self.browser.attach_location_header(self.status, self.parent_button)
        self.breadcrumb = header.folder_name
        self.workspaces_button = toga.Button('Workspaces', on_press=self.app.show_locations, style=Pack(height=TOUCH_TARGET))
        self.widget = toga.Box(children=[self.storage, header,
            self.browser.scroll_container(), self.workspaces_button],
            style=Pack(direction=COLUMN, flex=1))
        self.browser_widget = self.widget
        self.browser_widget._refresh_file_listing = lambda: self.refresh(preserve_listing=True)
        if destination == 'documents':
            self.menu_content = toga.Box(style=Pack(direction=COLUMN, margin=12))
            self.widget = toga.ScrollContainer(horizontal=False, content=self.menu_content, style=Pack(flex=1))
        self.storage.on_change = self.change_storage

    async def show_main_browser(self, storage, *, folder='', extensions=None, title='Browse files',
                                provider=None, library_key=None):
        from services.documents.mobile_locations import COPIES_ALIAS, enabled, storage_reference
        from .local_sources import device_files_label
        library = library_key is not None
        if not self.app.checkpoint():
            return False
        if (self.destination == 'home' or library or self.library_root is not None) and hasattr(self, 'page'):
            # A second picker can be opened from a reader above the first one.
            # Each owns its controls and return edge rather than moving the
            # older picker's widget out from under its retained reader.
            drawer = FileDrawer(self.navigation, self.destination)
            self.navigation.browsers[self.destination] = drawer
            return await drawer.show_main_browser(storage, folder=folder, extensions=extensions,
                title=title, provider=provider, library_key=library_key)
        if storage == 'Local files' and enabled(self.app.private_root):
            storage = device_files_label(self.app)
            if provider is not None and storage_reference(self.app.private_root, provider.root / folder).startswith(COPIES_ALIAS):
                storage = Path(folder).name or provider.root.name
        self.extensions = extensions
        self.library_root = provider.relative(folder) if library else None
        client = getattr(self.app, 'cloud_client', None)
        self.scoped_provider = (storage, provider, client, getattr(client, 'generation', None)) if provider else None
        self.folder = self.library_root if library else folder
        if library:
            self.library_key = library_key
            self.library_title = title
            self._library_split = False
            self._library_release = provider.acquire() if hasattr(provider, 'acquire') else None
            detach(self.storage)
            self.breadcrumb.value = title
            self.parent_button.enabled = True
            self.build_file_selection()
            self.browser_widget.insert(1, self.file_select_bar)
            from .control_icons import apply_icon, icon_button
            apply_icon(self.parent_button, 'back', 'Back to Libraries')
            self.folder_select_button = browser_command(icon_button(
                'selected_item', 'Select items', on_press=self.begin_file_selection, enabled=False))
            from .file_items import native_menu
            self.library_refresh = browser_command(native_menu(self.app, icon_button('overflow', 'Folder actions'),
                lambda: [('Refresh folder', self.refresh)]))
            self.browser.location_bar.add(self.browser.view_switch, self.folder_select_button, self.library_refresh)
            if self.app.routes.apple:
                self.folder_close_button = icon_button('close', 'Exit selection', on_press=self.end_file_selection)
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
            if not library:
                self.cancel_button = toga.Button('Cancel', on_press=self.cancel_browser,
                                                style=Pack(height=TOUCH_TARGET, width=72))
                self.browser.location_bar.add(self.cancel_button)
        route = ('workspace-browser:' + page._folder_scope if self.destination == 'home' else 'workspace-browser')
        if library:
            route = 'document-library-folder'
            page._documents_browser = True
            page._document_library_drawer = self
            from .destination_actions import HEADINGS, HEADER_HEIGHT
            heading = toga.Label(HEADINGS['documents'], style=Pack(height=HEADER_HEIGHT,
                text_align=CENTER, font_size=24, font_weight='bold'))
            self.library_sidebar = toga.Box(children=[heading], style=Pack(direction=COLUMN))
            from .scroll_edges import fill_bottom
            fill_bottom(page, self.browser.native_list, self.browser._tile_scroll)
        if self.destination == 'documents' and self.app.routes.apple:
            page._documents_browser = True
            if library:
                page._ios_toolbar_buttons = self.library_toolbar_buttons
                page._ios_toolbar_leading = self.library_toolbar_leading
            else:
                back, *actions = self.folder_toolbar_actions()
                page._ios_toolbar_buttons = actions
                page._ios_toolbar_leading = [back]
            page._ios_toolbar_replaces_back = True
            page._ios_toolbar_overflow = False
            if not library:
                page._ios_toolbar_title = ''
            page._ios_toolbar_hidden = [self.cancel_button] if not library else []
        if not self.app.show_view(page, destination=self.destination, route=route, title=title, checkpoint=False):
            if library:
                self.retire_library()
            return False
        return await self.refresh()

    def layout_library(self, nav, leading, gap, *, split):
        self._library_split = split
        if split:
            self.library_sidebar.style.width = leading
            if self.library_sidebar.parent is None:
                self.page.insert(0, self.library_sidebar)
        else:
            detach(self.library_sidebar)
        self.page.style.direction = ROW if split else COLUMN
        self.browser_widget.style.margin_left = gap if split else 0
        scrolls = (self.browser.native_list, self.browser._tile_scroll)
        if split:
            scrolls += (nav,)
        self.page._bottom_scrolls = scrolls

    def retire_library(self):
        self.listing.invalidate()
        self.refresh_requested = False
        self.end_file_selection()
        self.library_refresh.document_actions.dispose()
        self.browser.stop()
        self.provider = None
        release, self._library_release = self._library_release, None
        if release is not None:
            release()

    def back_action(self):
        """Retrace browser state before leaving this retained picker."""
        if self.browser.on_check_entry is not None:
            return self.end_file_selection
        if self.library_root is not None and not (self.browser.search_open or self.browser.search.value):
            return self.up
        action = self.browser.back_action()
        if action is not None:
            return action
        if self.folder:
            return self.up
        if self.main_browser_visible():
            return self.cancel_browser
        return None

    def main_browser_visible(self):
        from .routes import contains
        owner = getattr(self, 'page', None)
        return self.destination != 'files' and owner is not None and contains(owner, self.browser_widget)

    def folder_toolbar_actions(self):
        """Project the current folder controls into the native bubbles."""
        from .control_icons import icon_button
        if self.library_root is not None:
            return [*self.library_toolbar_leading(), *self.library_toolbar_buttons()]
        if not hasattr(self, 'folder_actions_button'):
            from .file_items import native_menu
            self.folder_actions_button = icon_button('more', 'Folder actions')
            self.folder_back_button = icon_button('back', 'Back to Libraries', on_press=self.up)
            self.folder_search_button = icon_button('find', 'Search this folder', on_press=self.browser.open_search)
            native_menu(self.app, self.folder_actions_button, lambda: [
                ('Refresh folder', self.refresh), ('List', self.browser.show_list),
                ('Tiles', self.browser.show_tiles)])
        if self.app.routes.apple:
            for button in (self.parent_button, self.browser.search_button):
                if button.parent is self.browser.location_bar:
                    button.parent.remove(button)
        self.folder_back_button.enabled = self.parent_button.enabled
        return [self.folder_back_button, self.folder_search_button, self.folder_actions_button]

    def library_toolbar_leading(self):
        if self.app.routes.apple and self.browser.on_check_entry is not None:
            return [self.folder_close_button]
        return [self.parent_button]

    def library_toolbar_buttons(self):
        if self.browser.on_check_entry is not None:
            return []
        return [self.browser.search_button, self.browser.view_switch, self.folder_select_button, self.library_refresh]

    @property
    def file_browser(self):
        return self.browser

    @property
    def file_provider(self):
        return self.provider

    @property
    def file_path(self):
        return self.folder

    @property
    def file_status(self):
        return self.status

    def file_operations(self):
        from .composition.presentation import file_operations
        if not hasattr(self, '_file_operations'):
            self._file_operations = file_operations(self.app, drawer=self)
        return self._file_operations

    async def selection_destination_finished(self, message):
        from .routes import contains
        if contains(self.app.body, self.page) and await self.refresh():
            self.status.value = message

    def update_file_selection_controls(self, visible):
        if self.app.routes.apple:
            self.navigation.render()
            return
        from .control_icons import apply_icon
        label = 'Back to Libraries' if self.folder == self.library_root else 'Parent folder'
        apply_icon(self.parent_button, 'close' if visible else 'back', 'Exit selection' if visible else label)
        for button in (self.browser.search_button, self.browser.view_switch, self.folder_select_button, self.library_refresh):
            button.style.update(display='none' if visible else 'pack',
                                visibility='hidden' if visible else 'visible')
        header = self.browser.location_bar
        if getattr(header, '_android_title', False):
            header.balance_android_title()

    def cancel_browser(self, widget=None, **kwargs):
        if not self.app.checkpoint():
            return False
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
        return True

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
            button = list_button(toga.Button(record['name'], on_press=browse_library, style=Pack(height=TOUCH_TARGET)))
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
        roots = self.ordinary_roots()
        if local_read_available(self.app):
            roots.update(self.app.existing_crypt_locations())
            roots.update(self.app.linked_crypt_locations())
        return roots

    def ordinary_roots(self):
        from services.documents.mobile_locations import enabled
        from .local_sources import device_files_label
        if enabled(self.app.private_root):
            roots = self.app.ordinary_file_roots(include_collections=False)
            return {device_files_label(self.app): roots['Shared files']}
        return {'Local files': None}

    async def refresh(self, *, preserve_listing=False):
        with self.browser.population_paused():
            self.generation += 1
            generation = self.generation
            work = self.listing.begin()
            scope = getattr(self, 'scoped_provider', None)
            try:
                roots = ({scope[0]: scope[1]} if self.library_root is not None
                         else await asyncio.to_thread(self.available_roots))
            except (OSError, ValueError) as error:
                # A failed credential query must not strand the menu refresh task.
                # Keep Local files usable and report the connection error in-place.
                if not self.listing.accepts(work, private=True):
                    return False
                self.status.value = str(error)[:160]
                return False
            if not self.listing.accepts(work, private=True):
                return False
            if scope is not None:
                roots.setdefault(scope[0], None)
            selected = self.storage.value if self.storage.value in roots else next(iter(roots))
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
                if scope is not None and scope[0] == selected:
                    provider = scope[1]
                    if provider.private and (self.app.cloud_client is not scope[2]
                            or self.app.cloud_client.generation != scope[3]):
                        raise ValueError('Unlock the library connection again.')
                else:
                    provider = self.app.storage_provider(selected, roots)
                if provider.private and not local_read_available(self.app):
                    raise ValueError('This connection is busy. Local files remain available.')
                model = ResourceSelection(provider, extensions=self.extensions or ())
                folder = self.folder
                request = self.listing.capture(work, provider, folder, (selected, folder), source=model)
                rows = await self.listing.read(request)
                if rows is None:
                    return False
                preserve = (preserve_listing and self.provider is provider and self.browser.location == (selected, folder)
                            and self.browser.folder_tree is not None)
                self.provider = provider
                self.provider_client = getattr(self.app, 'cloud_client', None)
                self.provider_generation = getattr(self.provider_client, 'generation', None)
                if self.library_root is not None:
                    can_select = self.can_select_file_entries(provider)
                    self.folder_select_button.enabled = can_select
                    if self.browser.on_check_entry is not None and (
                            self.browser.location != (selected, folder) or not can_select):
                        self.end_file_selection()
                if self.destination == 'documents':
                    from .browser_preview import LocalThumbnails, dark_notebook_thumbnails
                    self.browser.configure_previews(LocalThumbnails(
                        provider, self.provider_client, '', dark_notebooks=dark_notebook_thumbnails(self.app)))
                if preserve:
                    self.browser.refresh_entries(rows)
                else:
                    self.browser.set_entries(model, folder, rows, location=(selected, folder))
                self.browser.location_bar.update_provider(folder, provider, name=(
                    self.library_title if folder == self.library_root else selected if not folder else None))
                main_browser = self.main_browser_visible()
                self.parent_button.enabled = bool(folder) or main_browser
                if hasattr(self, 'folder_back_button'):
                    self.folder_back_button.enabled = self.parent_button.enabled
                if self.library_root is not None:
                    from .control_icons import apply_icon
                    back_label = 'Back to Libraries' if folder == self.library_root else 'Parent folder'
                    if self.browser.on_check_entry is None:
                        apply_icon(self.parent_button, 'back', back_label)
                elif main_browser and not folder:
                    from .control_icons import apply_icon
                    apply_icon(self.parent_button, 'back', 'Back')
                if hasattr(self, 'page'):
                    from .folder_navigation import record
                    record(self.app, self.page, self.browser, 'workspace-browser', selected, folder, self.navigate)
                self.status.value = ''
                if self.library_root is not None:
                    self.navigation.render()
                    from .browser_ui import sync_browser_population
                    sync_browser_population(self.app)
                if self.destination == 'documents' and self.library_root is None:
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
                if self.library_root is not None:
                    self.end_file_selection()
                    self.folder_select_button.enabled = False
                self.browser.stop()
                self.status.value = str(error)[:160]
                return False

    browse_files = refresh

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
        if self.browser.on_check_entry is not None:
            self.end_file_selection()
            return True
        if (not self.folder or self.folder == self.library_root) and self.main_browser_visible():
            self.cancel_browser()
            return True
        self.folder = self.folder.rpartition('/')[0]
        return await self.refresh()

    async def open_file(self, row):
        from services.documents.mobile_storage import open_provider_document
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
            opened = await open_provider_document(self.app, provider, path, destination=self.destination)
            if not opened:
                self.status.value = str(self.app.cloud_status.value or 'Could not open this file. Try opening it again.')[:300]
                return False
            if self.app.native_host.state.destination == self.destination:
                if not self.navigation.wide:
                    self.navigation.menu_open[self.destination] = False
                self.navigation.render()
            return True
        except (OSError, ValueError) as error:
            self.status.value = str(error)[:160]
            return False

