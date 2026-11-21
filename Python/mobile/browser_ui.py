"""Compact Logistics presentation over the shared native browser."""
import asyncio
from pathlib import PurePosixPath
from threading import Event
import toga
from .control_icons import apply_icon
from toga.style import Pack
from commonUtils.ui.native_browser.recycled import RecycledBrowser, BrowserPresentation
from .appearance import list_button
from .appearance import surface, template_icon, selection_row
from .browser_location import (
    BrowserStatusLabel as BrowserStatusLabel,
    FolderLocationHeader as FolderLocationHeader,
    FolderNameLabel as FolderNameLabel,
    browser_command as browser_command,
    provider_session_only as provider_session_only,
)
from .hub_icons import icon
from .folder_hub_style import (
    ENTRY_ICON_SIZE, ENTRY_ICON_MARGIN,
)


def middle_filename(button):
    """Let the native label fit the middle ellipsis without changing identity."""
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        button._impl.native.titleLabel.lineBreakMode = 5  # NSLineBreakByTruncatingMiddle
        button._impl.native.accessibilityLabel = button.text
    elif backend.startswith('toga_android.'):
        from android.text import TextUtils
        button._impl.native.setSingleLine(True)
        button._impl.native.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        button._impl.native.setContentDescription(button.text)


def entry_icon(directory, *, landing_page=False):
    """A consistent folder/file glyph for ordinary and Notes Library rows."""
    kind = 'folder_document' if directory and landing_page else 'files' if directory else 'documents'
    image = template_icon(toga.ImageView(icon(kind),
        style=Pack(width=ENTRY_ICON_SIZE, height=ENTRY_ICON_SIZE,
                   margin_left=ENTRY_ICON_MARGIN, margin_right=ENTRY_ICON_MARGIN)))
    image.browser_entry_kind = 'folder_document' if directory and landing_page else 'folder' if directory else 'file'
    surface(image, radius=0, background='transparent', foreground='file_icon',
            outlined=False, eink_outlined=False)
    return image


def breadcrumb_separator():
    """A passive, theme-tinted File Browser chevron."""
    image = template_icon(toga.ImageView(icon('breadcrumb_chevron'), style=Pack(width=14, height=14)))
    surface(image, radius=0, background='transparent', foreground='muted',
            outlined=False, eink_outlined=False)
    backend = type(image._impl).__module__
    if backend.startswith('toga_iOS.'):
        image._impl.native.isAccessibilityElement = False
    elif backend.startswith('toga_android.'):
        from android.view import View
        image._impl.native.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO)
    return image


def highlight_entry(widget, selected):
    if not isinstance(widget, toga.Button):
        selection_row(widget, selected)
        return
    surface(widget, radius=8, background='hover' if selected else 'surface',
            foreground='muted' if getattr(widget, 'browser_hidden', False) else 'text',
            outlined=False, eink_outlined=selected, eink_selected=selected)


def sync_browser_population(app, body=None):
    """Resume retained search only when its owning view is visible again."""
    privacy = getattr(app, 'screen_privacy', None)
    if (privacy is None or privacy.disposed or getattr(privacy, '_folder_work_paused', False)
            or getattr(app, 'scene_active', True) is False or not app.active_host):
        return
    body = body if body is not None else getattr(app, 'body', None)
    if body is None:
        return
    from .routes import contains
    paused = getattr(privacy, '_paused_file_browsers', ())
    for browser in tuple(paused):
        if browser.closed or contains(body, browser.widget):
            paused.discard(browser)
            browser.resume_search_work()
    notes = getattr(app, 'vault_browser', None)
    if notes is not None and notes._index_work_suspended and contains(body, notes.view):
        notes.resume_index_work()


def mounted_file_browsers(widget):
    browser = getattr(widget, '_file_browser_owner', None)
    if browser is not None:
        yield browser
        return
    if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
        yield from mounted_file_browsers(widget.content)
    else:
        for child in widget.children:
            yield from mounted_file_browsers(child)


def pause_file_browser_searches(app):
    """Fence workers of mounted browsers and retained source/picker views."""
    body = getattr(app, 'body', None)
    browsers = set(mounted_file_browsers(body)) if body is not None else set()
    browsers.update(getattr(app, name, None) for name in ('file_browser', 'remote_browser'))
    picker = getattr(app, '_editor_picker', None)
    browsers.add(getattr(picker, 'editor_browser', None))
    adaptive = getattr(app, 'adaptive', None)
    browsers.update(drawer.browser for drawer in getattr(adaptive, 'browsers', {}).values())
    paused = {browser for browser in browsers if isinstance(browser, FileBrowser) and not browser.closed}
    for browser in paused:
        browser.pause_search_work()
    return paused


def schedule_visible_file_browser_refresh(app):
    """Refresh the mounted browser through its existing listing workflow."""
    def refresh_action(widget):
        action = getattr(widget, '_refresh_file_listing', None)
        if action is not None:
            return action
        if isinstance(widget, toga.ScrollContainer) and widget.content is not None:
            return refresh_action(widget.content)
        for child in widget.children:
            if (action := refresh_action(child)) is not None:
                return action
        return None

    body = getattr(app, 'body', None)
    action = refresh_action(body) if body is not None else None
    if action is not None:
        async def refresh():
            privacy = app.screen_privacy
            if (app.active_host and app.body is body and not privacy.disposed
                    and not privacy.inactive and not privacy.interrupted and not privacy.resume_locked
                    and getattr(app, 'scene_active', True) is not False
                    and not getattr(app, '_storage_changing', False)
                    and refresh_action(body) == action):
                await action()

        app.loop.create_task(refresh())


async def refresh_download_directory(app, destination, target):
    """Refresh retained listings of the published parent, including storage aliases."""
    from .document_mutations import path_relative_to_mutation

    parent = target.rpartition('/')[0]
    drawers = tuple(getattr(app.adaptive, 'browsers', {}).values())
    listings = (getattr(app, '_folder_listing', None), *(drawer.listing for drawer in drawers))

    def matches(provider, folder):
        try:
            return path_relative_to_mutation(provider, folder, destination, parent) == ''
        except (OSError, ValueError):
            return False

    await asyncio.gather(*(listing.settle_matching_read(matches) for listing in listings if listing is not None))
    files = getattr(app, 'file_browser', None)

    async def refresh(browser, provider, folder, current, publish):
        if browser is None or browser.closed or browser.folder_tree is None or not matches(provider, folder):
            return
        tree, location = browser.folder_tree, browser.location
        try:
            rows = await asyncio.to_thread(browser.search_provider.list, folder)
        except (OSError, ValueError):
            # A concurrent lock or storage change owns any error presentation.
            return
        if (app.active_host and current() and not browser.closed
                and browser.folder_tree is tree and browser.location == location):
            publish(rows)

    tasks = []
    provider = getattr(app, 'file_provider', None)
    if files is not None and provider is not None:
        file_location = app.file_storage.value, app.file_location.value
        if file_location == getattr(app, 'file_loaded_location', None):
            def current():
                return (app.file_browser is files and app.file_provider is provider
                        and (app.file_storage.value, app.file_location.value) == file_location)

            def publish(rows):
                from .files_ui import FilesUI
                app.file_rows = FilesUI.file_browser_rows(rows)
                app.set_file_items(list(app.file_rows))
                files.refresh_entries(rows)

            tasks.append(refresh(files, provider, file_location[1], current, publish))
    for drawer in drawers:
        location = drawer.storage.value, drawer.folder
        if drawer.browser.location != location:
            continue
        def current_drawer(drawer=drawer, location=location, generation=drawer.generation):
            return (drawer.generation == generation and (drawer.storage.value, drawer.folder) == location)
        tasks.append(refresh(drawer.browser, drawer.provider, drawer.folder,
                             current_drawer, drawer.browser.refresh_entries))
    await asyncio.gather(*tasks)


class LogisticsBrowserPresentation(BrowserPresentation):
    command = staticmethod(apply_icon)
    command_style = staticmethod(browser_command)
    entry_icon = staticmethod(entry_icon)
    style_button = staticmethod(list_button)
    middle_filename = staticmethod(middle_filename)
    highlight = staticmethod(highlight_entry)

    def file_icon(self, folder):
        from .recycled_file_list import file_list_icon
        return file_list_icon(folder)

class FileBrowser(RecycledBrowser):
    def refresh_entries(self, rows):
        """Replace a directory snapshot while retaining its location and viewport."""
        from commonUtils.runtime.browsing import BrowseEntry, BrowseTree, provider_entries

        root = self.folder_tree.root
        entries = list(provider_entries(self.search_provider, rows))
        folder = BrowseTree(BrowseEntry(root, root.name, True), max_entries=len(entries) + 1)
        folder.set_children(root, entries)
        if self.tree is not self.folder_tree:
            # A search may display descendants as well as current-folder rows.
            # Keep those descendants while reconciling the changed parent.
            entries.extend(entry for entry in self.tree.entries.values()
                           if entry.identity != root and entry.identity.parent != root)
            tree = BrowseTree(BrowseEntry(root, root.name, True), max_entries=len(entries) + 1)
            tree.set_children(root, entries)
        else:
            tree = folder
        self.folder_tree = folder
        self.set_tree(tree, preserve=True)

    def __init__(self, *, folder_visible=None, local_search=None, **kwargs):
        self.on_check_entry = None
        self.checked_entries = set()
        self._displayed_checks = set()
        self._resource_provider = None
        self._release_resource = lambda: None
        from functools import partial
        from .recycled_file_list import RecycledFileList
        self.folder_visible = folder_visible
        if local_search is None and getattr(toga.App.app, 'private_root', None) is not None:
            from .local_search import LocalSearch
            local_search = LocalSearch(toga.App.app.private_root / 'Cache' / 'directory-index.sqlite3')
        self.local_search = local_search
        self._index_cancel = Event()
        self._index_error = None
        self._index_started = False
        self._submitted_search_epoch = -1
        self._search_suspended = False
        self._index_hint = object()
        if local_search is not None:
            kwargs['resource_search'] = local_search.search
        super().__init__(presentation=LogisticsBrowserPresentation(),
                         list_factory=partial(RecycledFileList, title_lines=2), inline_details=False, **kwargs)
        self.widget._clear_return_selection = self.clear_selection
        self.widget._file_browser_owner = self

    async def _select_pressed(self, entry, widget, **kwargs):
        if self.on_check_entry is None:
            return await super()._select_pressed(entry, widget, **kwargs)
        if self.closed or self.navigation_busy or not self._entry_current(entry):
            return
        entry = await self.validate_cached_entry(entry)
        if entry is not None and self._entry_current(entry) and self.on_check_entry is not None:
            self.on_check_entry(entry)

    def highlight_selection(self):
        super().highlight_selection()
        changed = self.checked_entries | self._displayed_checks
        self._displayed_checks = set(self.checked_entries)
        if self.mode == 'List':
            active = self.on_check_entry is not None
            self.native_list.show_checked_rows(active, (self._list_indices[identity]
                for identity in self.checked_entries & self._list_indices.keys()))
            for identity in changed & self._list_rows.keys():
                row = self._list_rows[identity]
                name = row.entry.payload.get('display_name') or PurePosixPath(row.entry.label).name
                title = '✓ ' + name if identity in self.checked_entries else name
                if row.title != title:
                    self.native_list.update_checked_title(row, title)
        else:
            for identity in changed & self.buttons.keys():
                button = self.buttons[identity]
                entry = self.tree.entries[identity]
                name = entry.payload.get('display_name') or PurePosixPath(entry.label).name
                title = '✓ ' + name if identity in self.checked_entries else name
                if button.text != title:
                    button.text = title

    def clear_selection(self):
        """Retire contextual selection without rebuilding the retained listing."""
        self.selected = None
        for child in list(self.info.children):
            self.info.remove(child)
        self.highlight_selection()
        if self.on_selected is not None:
            result = self.on_selected(None)
            if asyncio.iscoroutine(result):
                self._spawn(result)

    def back_action(self):
        """Choose one browser-local Back step; the route owns invoking it."""
        if self.search.value:
            return lambda: setattr(self.search, 'value', '')
        if self.search_open:
            return self.close_search
        if self.history.previous() is not None:
            return self.go_back
        return None

    def set_entries(self, provider, directory, rows, *, location=None):
        changed = provider is not self._resource_provider
        release = (provider.acquire() if hasattr(provider, 'acquire') else lambda: None) if changed else None
        self._index_cancel.set()
        self._index_cancel = Event()
        self._index_error = None
        self._index_started = False
        try:
            super().set_entries(provider, directory, rows, location=location)
        except BaseException:
            if release is not None:
                release()
            raise
        if changed:
            previous = self._release_resource
            self._resource_provider, self._release_resource = provider, release
            previous()
        self._foreground_folder(not self._search_suspended)
        if self.search_open and not self._search_suspended:
            self._start_local_index()
            if self.search.value:
                self.query_changed()

    async def _search_subfolders(self, epoch, cancelled):
        # Online search filters the loaded listing; recursive I/O is explicit.
        if self._search_suspended or getattr(self.search_provider, 'remote_storage', False):
            return
        if self.closed or epoch != self.search_epoch or cancelled.is_set():
            return
        self._submitted_search_epoch = epoch
        await super()._search_subfolders(epoch, cancelled)

    def _start_local_index(self):
        provider = self.search_provider
        if (not self._search_suspended and not self._index_started and provider is not None and self.local_search is not None
                and self.local_search.supports(provider)):
            self._index_started = True
            self._index_cancel = Event()
            self._spawn(self._prepare_local_search(provider, self.search_directory, self._index_cancel))

    def query_changed(self, widget=None, **kwargs):
        if not self._search_suspended or widget is self.sort:
            super().query_changed(widget, **kwargs)

    async def _prepare_local_search(self, provider, directory, cancelled):
        from commonUtils.runtime.operations import OperationCancelled
        try:
            await asyncio.to_thread(self.local_search.prepare, provider, directory,
                                    cancelled=cancelled.is_set)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except OperationCancelled:
            return
        except Exception as error:
            if not cancelled.is_set():
                self._index_error = str(error)
                self.page_label.text = 'Search index update failed: ' + self._index_error[:80]
            return
        if (not self.closed and not cancelled.is_set() and self.search.value
                and self._submitted_search_epoch == self.search_epoch):
            # A waiting typeahead will read the reconciled index. Replay only
            # if this text was already submitted, without a second typing delay.
            self._queue_query(delay=0)

    def stop(self):
        header = getattr(self, 'location_bar', None)
        if header is not None:
            header.clear_location()
        self.stop_local_search()
        super().stop()
        self._search_suspended = False
        self._release_resource()
        self._resource_provider = None
        self._release_resource = lambda: None

    def stop_local_search(self):
        self._index_cancel.set()
        self.search_cancelled.set()
        self._foreground_folder(False)

    def _foreground_folder(self, active):
        cache = getattr(self.local_search, 'cache', None)
        if cache is None:
            return
        from services.directory_index import focus
        provider = self.search_provider
        paths = ((provider.root / provider.relative(self.search_directory),)
                 if active and provider is not None and self.local_search.supports(provider) else ())
        focus(cache.database, self._index_hint, paths)

    def pause_search_work(self):
        if self._search_suspended or self.closed:
            return
        self._search_suspended = True
        self.stop_local_search()
        self.search_epoch += 1
        self.searching = False
        self._index_started = False

    def resume_search_work(self):
        if not self._search_suspended or self.closed:
            return
        self._search_suspended = False
        self._foreground_folder(True)
        if self.search_open:
            self._start_local_index()
            if self.search.value:
                self.query_changed()

    location_header = FolderLocationHeader

    status_label = BrowserStatusLabel

    def attach_location_header(self, status, parent_button):
        for action in (self.search_button,):
            if action.parent is not None:
                action.parent.remove(action)
        self.location_bar = self.location_header(status, parent_button,
            actions=(self.search_button,))
        # The visible control follows the same state history as Android Back.
        fallback = parent_button.on_press
        def back(widget=None, **kwargs):
            routes = getattr(parent_button.app or toga.App.app, 'routes', None)
            if routes is not None and not routes.apple:
                return routes.system_back()
            # Toga's retained handler already binds this button as its first
            # argument; forwarding it again breaks native Apple callbacks.
            return fallback(**kwargs)
        parent_button.on_press = back
        # The explicit Back control replaces the generic browser history row.
        if self.navigation_controls in self.widget.children:
            self.widget.remove(self.navigation_controls)
        return self.location_bar

    @property
    def entries(self):
        if self._render_entries is not None:
            return self._render_entries
        rows = super().entries
        if self.folder_visible is None:
            return rows
        provider = getattr(self, 'search_provider', None)
        remote = getattr(getattr(provider, 'provider', provider), 'remote', '')
        if not self.folder_visible(remote):
            return []
        return [entry for entry in rows if self.folder_visible(
            entry.payload.get('path', entry.label), directory=entry.container)]

    @property
    def search_open(self):
        return self.search_panel.parent is not None

    def toggle_search(self, widget=None, **kwargs):
        if self.search_open:
            self.close_search()
        else:
            self.open_search()

    def open_search(self, widget=None, **kwargs):
        if not self.search_open:
            header = getattr(self, 'location_bar', None)
            if header is None or getattr(header, 'native_actions', None) is None:
                # Inline folder titles/status remain above the expanding search.
                # The browser body is mounted immediately beneath that header.
                self.widget.insert(0, self.search_panel)
            else:
                toolbar = getattr(header, 'native_actions', header)
                if toolbar is not header and toolbar.parent is None:
                    header.add(toolbar)
                self.search_panel.style.flex = 1
                self._search_toolbar = toolbar
                self._search_toolbar_children = list(toolbar.children)
                for child in self._search_toolbar_children:
                    toolbar.remove(child)
                # UIKit keeps the folder title and actions in its native bar.
                toolbar.add(self.search_panel)
                for child in self._search_toolbar_children:
                    if child not in (header.parent_button, header.caption, self.search_button) and not (
                            type(child) is toga.Box and not child.children):
                        toolbar.add(child)
        if self.page_label not in self.widget.children:
            self.widget.insert(0 if hasattr(self, '_search_toolbar') else 1, self.page_label)
        self.search.focus()
        self._start_local_index()

    def close_search(self, widget=None, **kwargs):
        if type(self.search._impl).__module__.startswith('toga_iOS.'):
            # Release keyboard ownership before detaching the focused field.
            self.search._impl.native.resignFirstResponder()
        self._index_cancel.set()
        self._index_started = False
        self.search.value = ''
        if self.search_open:
            self.search_panel.parent.remove(self.search_panel)
        toolbar = getattr(self, '_search_toolbar', None)
        if toolbar is not None:
            for child in list(toolbar.children):
                toolbar.remove(child)
            toolbar.add(*self._search_toolbar_children)
            if not toolbar.children and toolbar.parent is not None:
                toolbar.parent.remove(toolbar)
            self.search_panel.style.flex = 0
            del self._search_toolbar, self._search_toolbar_children
        if self.page_label in self.widget.children:
            self.widget.remove(self.page_label)

    def show_item_menu(self, actions):
        from .action_menu import show_browser_actions
        return show_browser_actions(self, actions)

    def install_item_commands(self, commands):
        self.on_item_actions = lambda row: self.show_item_menu(commands(row))
        if self.native_list.factory.DetailedList.__module__.startswith('toga_iOS.'):
            async def provide(row):
                if self.closed or self.navigation_busy or row.epoch != self.epoch or not self._entry_current(row.entry):
                    return []
                entry = await self.validate_cached_entry(row.entry)
                if entry is None or not self._entry_current(entry):
                    return []
                await self.select(entry)
                if self.selected != entry.identity or not self._entry_current(entry):
                    return []
                from .action_menu import BrowserActions, ios_menu_actions
                self.dismiss_item_menu()
                menu = self._item_menu = BrowserActions(self, commands(entry.payload))
                return ios_menu_actions(menu.actions, menu.invoke, menu.blocks)
            self.native_list.menu_provider = provide
