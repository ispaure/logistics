"""Retained search routes and folder visits above their populated results."""

__author__ = 'Marc-André Voyer'
__license__ = 'MIT License'

import asyncio
from pathlib import PurePosixPath

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .control_icons import icon_button
from .files_ui import FileSelectionUI


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
        self.mode = browser.mode
        if self.parent is not None:
            self.parent.remove(browser.widget)
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
        browser.mode = self.mode
        if browser.widget.parent is not None:
            browser.widget.parent.remove(browser.widget)
        if self.parent is not None:
            self.parent.insert(self.index, browser.widget)
        browser.render()
        browser.vertical_position = self.scroll


class SearchFolder(FileSelectionUI):
    """A file-browser visit above a retained search or parent folder."""
    def __init__(self, app, provider, path, open_file, destination, release):
        from .browser_preview import LocalThumbnails, dark_notebook_thumbnails
        from .file_browser_view import LocalFileBrowser
        from .file_items import native_menu
        from .folder_listing import FolderListing
        from .scroll_edges import fill_bottom

        self.app, self.file_provider, self.file_path = app, provider, path
        self.destination, self.open_file, self.release = destination, open_file, release
        self.retired = False
        self.listing = FolderListing(active=lambda: app.active_host and not self.retired,
            context=lambda: self.file_path, location=lambda: ('', self.file_path),
            credentials=lambda: (app.cloud_client, getattr(app.cloud_client, 'generation', None)))
        self.browser = self.file_browser = LocalFileBrowser(folder_visible=app.folder_path_visible,
            preview=False, open_file=open_file, open_folder=self.open_folder)
        self.browser.install_item_commands(self.item_actions)
        source = LocalThumbnails(provider, app.cloud_client, '', dark_notebooks=dark_notebook_thumbnails(app))
        self.browser.configure_previews(source)
        self.browser.details = source.details
        title = PurePosixPath(path).name or 'Files'
        back = icon_button('back', 'Back', on_press=lambda widget: app.routes.back())
        self.file_status = self.browser.status_label('')
        header = self.browser.attach_location_header(self.file_status, back)
        self.folder_select_button = icon_button('selected_item', 'Select items', on_press=self.begin_file_selection,
                                               enabled=self.can_select_file_entries(provider))
        self.overflow = native_menu(app, icon_button('overflow', 'Folder actions'), self.folder_actions)
        self.controls = [self.browser.view_switch, self.folder_select_button, self.overflow]
        self.close_selection = icon_button('close', 'Exit selection', on_press=self.end_file_selection)
        self.close_selection.style.update(display='none', visibility='hidden')
        header.add(*self.controls, self.close_selection)
        self.build_file_selection()
        self.page = toga.Box(children=[header, self.file_select_bar, self.browser.widget],
                            style=Pack(direction=COLUMN, flex=1, margin=12))
        fill_bottom(self.page, self.browser.native_list, self.browser._tile_scroll)
        self.page._search_folder = self.browser
        self.page._private_search_folder = bool(provider.private)
        self.page._retire_search_route = self.retire
        if app.routes.apple:
            header.use_native_title()
            self.page._ios_toolbar_buttons = lambda: [] if self.browser.on_check_entry else [
                self.browser.search_button, *self.controls]
            self.page._ios_toolbar_leading = lambda: [self.close_selection] if self.browser.on_check_entry else [back]
            self.page._ios_toolbar_replaces_back = True
            self.page._ios_toolbar_overflow = False
            self.page._ios_toolbar_title = title

    def update_file_selection_controls(self, visible):
        for control in (self.browser.search_button, *self.controls, self.close_selection):
            shown = visible if control is self.close_selection else not visible
            control.style.update(display='pack' if shown else 'none', visibility='visible' if shown else 'hidden')
        if self.app.routes.apple:
            self.app.adaptive.render()

    async def reload(self):
        provider, path = self.file_provider, self.file_path
        request = self.listing.capture(self.listing.begin(), provider, path, ('', path))
        try:
            rows = await self.listing.read(request)
        except (OSError, ValueError) as error:
            self.file_status.value = str(error)
            return False
        if rows is None or self.browser.closed:
            return False
        if self.browser.folder_tree is None:
            self.browser.set_entries(provider, path, rows, location=('', path))
        else:
            self.browser.refresh_entries(rows)
        self.browser.location_bar.update_provider(path, provider)
        return True

    async def open_folder(self, row):
        return await visit_folder(self.app, self.file_provider, row['path'], self.open_file, self.destination)

    async def selection_destination_finished(self, message):
        if await self.reload():
            self.file_status.value = message

    def file_operations(self):
        from .composition.presentation import file_operations
        if not hasattr(self, '_operations'):
            self._operations = file_operations(self.app, drawer=self)
        return self._operations

    def folder_actions(self):
        from commonUtils.runtime.resources.provider import capabilities
        actions = [('Refresh folder', self.reload), ('List', self.browser.show_list), ('Tiles', self.browser.show_tiles)]
        if capabilities(self.file_provider).create and not getattr(self.file_provider, 'read_only', False):
            actions.append(('New folder…', lambda: self.name_form('new')))
        return actions

    def item_actions(self, row):
        from .archive_ui import archive_commands
        from .file_operations import FileSelectionMove
        from commonUtils.runtime.resources.provider import capabilities
        app, provider = self.app, self.file_provider
        access = capabilities(provider)
        writable = not getattr(provider, 'read_only', False)
        opener = self.open_folder if row['directory'] else self.open_file
        actions = [('Open', lambda: opener(row)), ('Details', lambda: self.browser.show_details_panel(self.page))]
        if writable and access.rename:
            actions.append(('Rename…', lambda: self.name_form('rename', row)))
        if writable and access.delete:
            action = FileSelectionMove(provider, ((row['path'], row['revision']),),
                                       on_complete=self.selection_destination_finished)
            actions.append(('Move…', lambda: app.editor_picker().show_destination('', action, start_folder=self.file_path)))
            actions.append(('Delete…', lambda: self.delete_item(row)))
        if not row['directory'] and writable and access.create and access.rename:
            actions.append(('Duplicate', lambda: self.mutate('copy', row)))
        return [*actions, *app.file_item_actions(provider, row), *archive_commands(app, provider, row)]

    async def delete_item(self, row):
        if await self.app.main_window.dialog(toga.ConfirmDialog('Delete ' + row['name'], 'Delete this item permanently?')):
            return await self.mutate('delete', row)
        return False

    async def mutate(self, kind, row=None, name='', *, reload=True):
        from .file_operations import FileOperationRequest
        row = row or {}
        request = FileOperationRequest(kind, self.file_provider, row.get('path', self.file_path),
                                       name, expected_revision=row.get('revision'))
        if self.browser.closed or not await self.file_operations().run(lambda: request):
            return False
        return await self.reload() if reload else True

    def name_form(self, kind, row=None):
        from .filename_input import FilenameInput
        app = self.app
        title = 'New folder' if kind == 'new' else 'Rename'
        field = FilenameInput(placeholder='Folder name' if kind == 'new' else 'New name', style=Pack(height=48))
        if row is not None:
            field.set_filename(row['name'], directory=row['directory'])
        status = toga.Label('', style=Pack(margin_top=8))

        async def save(widget=None, **kwargs):
            if await self.mutate(kind, row, field.value, reload=False):
                app.routes.back()
                await self.reload()
            else:
                status.text = self.file_status.value

        view = toga.Box(children=[field, toga.Button(title, on_press=save, style=Pack(height=48)),
                                 toga.Button('Cancel', on_press=lambda widget: app.routes.back(), style=Pack(height=48)),
                                 status], style=Pack(direction=COLUMN, flex=1, margin=12))
        return app.show_view(view, destination=self.destination, route=f'search-folder-name:{id(view)}', title=title)

    def retire(self):
        if self.retired:
            return
        self.retired = True
        self.listing.invalidate()
        self.overflow.document_actions.dispose()
        self.browser.stop()

        async def close():
            try:
                await self.browser.close()
            finally:
                self.release()
        self.app.loop.create_task(close())


async def visit_folder(app, provider, path, open_file, destination, *, release=lambda: None):
    """Push a folder browser and keep the underlying query running."""
    from commonUtils.runtime.resources.selection import ResourceSelection

    if not app.checkpoint():
        release()
        return False
    if isinstance(provider, ResourceSelection):
        provider = provider.provider
    folder = SearchFolder(app, provider, path, open_file, destination, release)
    generation = app.navigation_generation
    try:
        loaded = await folder.reload()
    except BaseException:
        folder.retire()
        raise
    if not loaded and generation == app.navigation_generation and app.active_host:
        await app.main_window.dialog(toga.InfoDialog('Could not open folder', folder.file_status.value))
    if (not loaded or generation != app.navigation_generation or not app.show_view(folder.page,
            destination=destination, route=f'search-folder:{id(folder)}', title=PurePosixPath(path).name or 'Files')):
        folder.retire()
        return False
    return True


async def visit_document_folder(app, hit, *, parent=False):
    from .file_items import _resolve_reference
    from services.documents.mobile_storage import open_provider_document

    destination = app.native_host.state.destination
    generation = app.navigation_generation
    try:
        item, release = await asyncio.to_thread(_resolve_reference, app, hit['source'])
    except (OSError, ValueError) as error:
        await app.main_window.dialog(toga.InfoDialog('Could not open folder', str(error)))
        return False
    if generation != app.navigation_generation or not app.active_host:
        release()
        return False
    provider = item.provider

    async def open_file(row):
        return await open_provider_document(app, provider, row['path'], destination=destination)

    path = item.path.rpartition('/')[0] if parent else item.path
    return await visit_folder(app, provider, path, open_file, destination, release=release)


class SearchThumbnails:
    """One cancellable loader for a retained Documents result list."""
    def __init__(self, app):
        from threading import Event
        self.app = app
        self.rows = []
        self.visible = self.closed = False
        self.cancelled = Event()
        self.task = None

    def add(self, hit, artwork):
        from .browser_preview import PREVIEW_SUFFIXES
        source = hit['source']
        if (not hit.get('directory') and source['type'] in {'local', 'crypt'}
                and PurePosixPath(hit['name']).suffix.lower() in PREVIEW_SUFFIXES):
            self.rows.append((source, artwork, artwork.children[0]))
            self.start()

    def set_visible(self, visible):
        from threading import Event
        if self.closed or self.visible == visible:
            return
        self.visible = visible
        if visible:
            self.cancelled = Event()
            self.start()
        else:
            self.cancelled.set()
            for source, artwork, fallback in self.rows:
                if source['type'] == 'crypt':
                    artwork.clear()
                    artwork.add(fallback)
                    artwork._search_preview_complete = False

    def close(self):
        self.set_visible(False)
        self.closed = True
        self.rows.clear()

    def start(self):
        if self.visible and self.task is None and any(
                not getattr(image, '_search_preview_complete', False) for _, image, _ in self.rows):
            self.task = self.app.loop.create_task(self.load(self.cancelled))

    async def load(self, cancelled):
        from commonUtils.runtime.operations import OperationCancelled
        from .browser_preview import LocalThumbnails, dark_notebook_thumbnails
        from .file_items import _resolve_reference

        def render(source, client, dark):
            item, release = _resolve_reference(self.app, source)
            try:
                loader = LocalThumbnails(item.provider, client, '', dark_notebooks=dark)
                return loader.load(item.validate(), (96, 96), cancelled.is_set)
            finally:
                release()

        try:
            for source, artwork, _ in self.rows:
                if cancelled.is_set() or self.closed:
                    break
                if getattr(artwork, '_search_preview_complete', False):
                    continue
                client = self.app.cloud_client
                generation = getattr(client, 'generation', None)
                try:
                    data = await asyncio.to_thread(render, source, client, dark_notebook_thumbnails(self.app))
                except (OSError, ValueError, AttributeError, RuntimeError, OperationCancelled):
                    data = None
                if cancelled.is_set() or self.closed:
                    break
                if source['type'] == 'crypt' and (client is not self.app.cloud_client
                        or generation != getattr(client, 'generation', None)):
                    data = None
                if data:
                    try:
                        image = toga.Image(src=data)
                        scale = min(44 / image.width, 44 / image.height)
                        preview = toga.ImageView(image, style=Pack(
                            width=max(1, round(image.width * scale)), height=max(1, round(image.height * scale))))
                    except (OSError, ValueError, RuntimeError, ZeroDivisionError):
                        pass
                    else:
                        artwork.clear()
                        artwork.add(preview)
                artwork._search_preview_complete = True
        finally:
            self.task = None
            self.start()
