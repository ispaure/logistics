"""Compact Logistics presentation over the shared native browser."""
import inspect
from contextlib import contextmanager
from collections import OrderedDict
import weakref
from threading import Event
from pathlib import PurePosixPath
import toga
from .control_icons import apply_icon
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from commonUtils.ui.native_browser import NativeBrowser
from .appearance import list_button
from .appearance import accessible_name, apple_color, surface, template_icon
from .hub_icons import icon
from .folder_hub_style import (
    folder_row, folder_name, ROW_HEIGHT, ROW_GAP, ENTRY_ICON_SIZE, ENTRY_ICON_MARGIN,
)


def browser_command(button):
    """Use normal accent navigation, retaining outlines for Android E Ink."""
    return surface(button, radius=8, background='transparent', foreground='accent',
                   outlined=False, eink_outlined=True)


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
    surface(image, radius=0, background='transparent', foreground='accent',
            outlined=False, eink_outlined=False)
    return image


def highlight_entry(widget, selected):
    surface(widget, radius=8, background='hover' if selected else 'surface',
            foreground='text' if isinstance(widget, toga.Button) else None,
            outlined=False, eink_outlined=selected, eink_selected=selected)


def sync_browser_population(app, body=None):
    """Compatibility hook for retained route/privacy lifecycle callers."""
    # Native lists own their viewport; there is no Python population timer.
    return


class BrowserStatusLabel(toga.Label):
    """Plain browser text with the value interface used by workflow status."""
    def __init__(self, value='', **kwargs):
        super().__init__(value, **kwargs)
        self.style.flex = 1
        self.style.margin_left = 6
        self.style.margin_right = 8
        backend = type(self._impl).__module__
        if backend.startswith('toga_iOS.'):
            self._impl.native.lineBreakMode = 5  # Middle ellipsis for long folder names.
        elif backend.startswith('toga_android.'):
            from android.text import TextUtils
            self._impl.native.setSingleLine(True)
            self._impl.native.setEllipsize(TextUtils.TruncateAt.MIDDLE)
        surface(self, radius=0, background='transparent', foreground='text',
                outlined=False, eink_outlined=False)
        # Native labels measure the whole single-line string. Let Pack shrink
        # that text so the adjacent parent/search controls stay on screen.
        from travertino.size import at_least
        self.intrinsic.width = at_least(0)
        native_rehint = getattr(type(self._impl), 'rehint', None)
        if native_rehint is not None:
            reference = weakref.ref(self)
            def rehint():
                target = reference()
                if target is not None:
                    native_rehint(target._impl)
                    target.intrinsic.width = at_least(0)
            self._impl.rehint = rehint

    @property
    def value(self):
        return self.text

    @value.setter
    def value(self, value):
        self.text = value
        changed = getattr(self, 'status_changed', None)
        if changed is not None:
            changed()


class FolderLocationHeader(toga.Box):
    """Current storage identity and a parent/root navigation control."""
    def __init__(self, status, parent_button, *, actions=()):
        self.parent_button = parent_button
        self.folder_name = BrowserStatusLabel('Root', style=Pack(font_size=20, font_weight='bold'))
        self.status = status
        self.folder_name.style.flex = self.status.style.flex = 0
        self.folder_name.style.margin_left = self.status.style.margin_left = 0
        self.status.style.font_size = 12
        self.status.style.height = 18
        self.status.style.margin = 0
        surface(self.status, radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        self.storage_icons = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=18))
        self.storage_identity = toga.Box(style=Pack(direction=ROW, align_items=CENTER, height=18))
        self.caption = toga.Box(children=[self.folder_name],
                                style=Pack(direction=COLUMN, flex=1, margin_left=6))
        self.status.status_changed = self.refresh_status
        self.refresh_status()
        super().__init__(children=[parent_button, self.caption, *actions],
                         style=Pack(direction=ROW, align_items=CENTER, margin_top=4))
        self.update('')

    def use_native_title(self):
        """UIKit owns the folder title; this row retains storage and actions."""
        if self.folder_name in self.caption.children:
            self.caption.remove(self.folder_name)

    def refresh_status(self):
        """Use one secondary line for operation text or passive storage identity."""
        visible = self.status if self.status.text else self.storage_identity
        for child in (self.status, self.storage_identity):
            if child is not visible and child in self.caption.children:
                self.caption.remove(child)
        if visible not in self.caption.children:
            self.caption.add(visible)

    def update(self, path, *, remote=False, encrypted=False, unlocked=False, name=None):
        self.folder_name.value = name if name is not None else PurePosixPath(path).name if path else 'Root'
        apply_icon(self.parent_button, 'up' if path else 'back',
                   'Parent folder' if path else 'Back to Workspaces')
        browser_command(self.parent_button)
        kinds = [('storage_remote', 'Online folder')] if remote else [('storage_local', 'On-device folder')]
        if encrypted:
            state = 'unlocked' if unlocked else 'locked'
            kinds.append(('folder_' + state, 'Encrypted folder, ' + state))
        if kinds == getattr(self, '_storage_kinds', None):
            return
        for child in list(self.storage_icons.children):
            self.storage_icons.remove(child)
        for child in list(self.storage_identity.children):
            self.storage_identity.remove(child)
        self.storage_identity.add(self.storage_icons)
        for name, label in kinds:
            indicator = template_icon(toga.ImageView(icon(name), style=Pack(width=18, height=18, margin_right=4)))
            indicator.control_icon = name
            accessible_name(indicator, label)
            surface(indicator, radius=0, background='transparent',
                    foreground=name if name.startswith('folder_') else 'accent',
                    outlined=False, eink_outlined=False)
            self.storage_icons.add(indicator)
        identity = ('Cloud' if remote else 'On-device') + ((' · Unlocked' if unlocked else ' · Locked') if encrypted else '')
        self.storage_identity.add(BrowserStatusLabel(identity, style=Pack(font_size=12, height=18, margin=0)))
        surface(self.storage_identity.children[-1], radius=0, background='transparent', foreground='muted',
                outlined=False, eink_outlined=False)
        self._storage_kinds = kinds


class FileBrowser(NativeBrowser):
    location_header = FolderLocationHeader
    status_label = BrowserStatusLabel
    @property
    def page_size(self):
        # The shared renderer also uses this for Tiles and rich previews.
        # Mobile folders and search results form one scrolling list.
        return max(1, len(self.entries))

    def __init__(self, *, open_file=None, item_actions=None, folder_visible=None, bounded_pages=True,
                 **kwargs):
        self._app = toga.App.app
        self._loop = self._app.loop
        self.bounded_pages = bounded_pages
        self._render_entries = None
        self._rendering = False
        self._list_entries = ()
        self._list_rows = {}
        self._list_indices = {}
        self._list_query = None
        self._list_thumbnail_rows = OrderedDict()
        self._decoded_thumbnails = OrderedDict()
        self._tile_cards = {}
        self._tile_row_views = {}
        self._tile_range = None
        self._population_epoch = 0
        self._thumbnail_requested = set()
        self._thumbnail_pending = set()
        self._scroll = None
        self.folder_visible = folder_visible
        self.on_open_file = open_file
        self.on_item_actions = item_actions
        super().__init__(**kwargs)
        # Keep the listing unobstructed until search is requested.
        for child in list(self.widget.children):
            self.widget.remove(child)
        self.search.placeholder = 'Search files and folders'
        for control in (self.search, self.sort, self.list_button, self.tile_button, self.previous, self.next):
            control.style.height = 48
        apply_icon(self.back_button, 'back', 'Go back')
        apply_icon(self.previous, 'back', 'Previous results')
        apply_icon(self.next, 'forward', 'Next results')
        apply_icon(self.search_button, 'find', 'Search this folder')
        apply_icon(self.close_search_button, 'close', 'Close search')
        for control in (self.back_button, self.previous, self.next,
                        self.search_button, self.close_search_button):
            browser_command(control)
        self.paging = toga.Box(children=[self.previous, self.page_label, self.next], style=Pack(direction=ROW))
        self.widget.add(toga.Box(children=[self.back_button, toga.Box(style=Pack(flex=1)),
                                          self.search_button],
                                 style=Pack(direction=ROW, margin_top=4, margin_bottom=8)))
        self.navigation_controls = self.widget.children[-1]
        self.page_label.style.flex = 1
        self.page_label.style.font_size = 12
        from .recycled_file_list import RecycledFileList
        self.native_list = RecycledFileList(on_select=self._list_selected,
            on_primary_action=self._list_context, on_visible=self._row_visible,
            style=Pack(flex=1))
        self.empty_label = toga.Label('', style=Pack(margin=12))
        self._tile_scroll = toga.ScrollContainer(horizontal=False, content=self.items,
                                                style=Pack(flex=1))
        self._tile_scroll.on_scroll = self._tile_scrolled
        self.widget.style.flex = 1
        self.widget.add(self.native_list)

    def _spawn(self, coroutine):
        # Native synchronous text callbacks can arrive between cooperative loop
        # dispatches. Queue search on the owning loop even without a running-loop
        # context, as Toga does for its asynchronous event handlers.
        task = self._loop.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def attach_location_header(self, status, parent_button):
        for action in (self.search_button,):
            if action.parent is not None:
                action.parent.remove(action)
        self.location_bar = self.location_header(status, parent_button,
            actions=(self.search_button,))
        # The explicit parent control replaces the generic browser history row.
        if self.navigation_controls in self.widget.children:
            self.widget.remove(self.navigation_controls)
        return self.location_bar

    def set_entries(self, provider, directory, rows, *, location=None):
        rows = tuple(rows)
        super().set_entries(provider, directory, rows, location=location)

    def set_tree(self, tree):
        self._population_epoch += 1
        self._decoded_thumbnails.clear()
        return super().set_tree(tree)

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

    def open_search(self, widget=None, **kwargs):
        if self.search_panel not in self.widget.children:
            self.widget.insert(0, self.search_panel)
        self.search.focus()

    def close_search(self, widget=None, **kwargs):
        self.search.value = ''
        if self.search_panel in self.widget.children:
            self.widget.remove(self.search_panel)

    def render(self):
        # Resolve sorting/filtering once; list rows are lightweight source data.
        self._render_entries = self.entries
        self._rendering = True
        try:
            if self.mode == 'List':
                self._render_list()
            else:
                self.native_list.clear()
                self._mount_listing(self._tile_scroll)
                self._render_tiles()
        finally:
            self._render_entries = None
            self._rendering = False

    def scroll_container(self):
        """Return a bounded viewport; never put a native list in a ScrollContainer."""
        self._scroll = self.widget
        return self.widget

    @contextmanager
    def population_paused(self):
        # Provider/navigation callers retain this scope; native lists have no
        # background population work to pause while an async listing runs.
        yield

    def _mount_listing(self, view):
        for child in (self.native_list, self._tile_scroll, self.empty_label):
            if child is not view and child in self.widget.children:
                self.widget.remove(child)
        if view not in self.widget.children:
            self.widget.add(view)

    def _render_list(self):
        self._clear_tiles()
        from .recycled_file_list import file_list_icon
        self._cancel()
        self.page = 0
        self.previous.enabled = self.next.enabled = False
        self.page_label.text = ''
        self.buttons.clear()
        self.entry_rows = {}
        self._list_entries = tuple(self.entries) if not self.closed else ()
        self._list_query = (self.search.value, self.sort.value)
        self._list_thumbnail_rows.clear()
        self._thumbnail_requested.clear()
        self._thumbnail_pending.clear()
        self.native_list.observe_rows = bool(self.thumbnail)
        self.native_list.updating = True
        try:
            # Each row carries the entry object, not an index into mutable state.
            # Delayed native callbacks cannot activate a replaced folder/query.
            records = []
            for index, entry in enumerate(self._list_entries):
                records.append(dict(
                    title=entry.payload.get('display_name') or PurePosixPath(entry.label).name,
                    subtitle='', icon=file_list_icon(entry.container), folder=entry.container, entry=entry,
                    epoch=self.epoch, thumbnail=False, index=index))
            # Publish lightweight rows once. Only visible cells decode images.
            self.native_list.data = records
            self._list_rows = {row.entry.identity: row for row in self.native_list.data}
            self._list_indices = {row.entry.identity: row.index for row in self.native_list.data}
            self._list_thumbnail_rows.update((row.entry.identity, row)
                for row in self.native_list.data if row.thumbnail)
            self.highlight_selection()
        finally:
            self.native_list.updating = False
        if self._list_entries:
            self._mount_listing(self.native_list)
        else:
            self.empty_label.text = ('No matching items.' if self.search.value else 'This folder is empty.')
            self._mount_listing(self.empty_label)
        from .keyboard import bind_browser
        bind_browser(self)

    def _list_selected(self, widget, **kwargs):
        if self._rendering or widget.updating:
            return
        row = widget.selection
        if row is not None and row.epoch == self.epoch:
            # Capture synchronously: an async Toga handler would read selection
            # only after another tap/source replacement could have changed it.
            self._spawn(self._activate_row(row))

    def _list_context(self, widget, row, **kwargs):
        if not self._rendering and row.epoch == self.epoch:
            self._spawn(self._select_row(row))

    async def _select_row(self, row):
        if (not self.closed and not self.navigation_busy and row.epoch == self.epoch
                and self._list_rows.get(row.entry.identity) is row and self._entry_current(row.entry)):
            await self.select(row.entry)
            if (self.on_item_actions is not None and row.epoch == self.epoch
                    and self._entry_current(row.entry) and self.selected == row.entry.identity):
                result = self.on_item_actions(row.entry.payload)
                if inspect.isawaitable(result):
                    await result

    async def _activate_row(self, row):
        if row.epoch == self.epoch and self._list_rows.get(row.entry.identity) is row:
            await self._select_pressed(row.entry, self.native_list)

    async def activate_entry(self, entry):
        """Activate a current entry through the same guarded path as a native tap."""
        await self._select_pressed(entry, self.native_list)

    def _entry_current(self, entry):
        if self.tree is None or self.tree.entries.get(entry.identity) is not entry:
            return False
        if self.mode == 'List':
            return (self._list_query == (self.search.value, self.sort.value)
                    and entry.identity in self._list_rows)
        return entry.identity in self.buttons

    def _set_row_thumbnail(self, row, image):
        from .recycled_file_list import thumbnail_image, file_list_icon
        key = row.entry.identity, row.entry.revision
        decoded = self._decoded_thumbnails.get(key)
        if decoded is None:
            decoded = thumbnail_image(image)
            self._decoded_thumbnails[key] = decoded
        self._decoded_thumbnails.move_to_end(key)
        while len(self._decoded_thumbnails) > 64:
            self._decoded_thumbnails.popitem(last=False)
        row.thumbnail = True
        row.icon = decoded
        self._list_thumbnail_rows[row.entry.identity] = row
        self._list_thumbnail_rows.move_to_end(row.entry.identity)
        while len(self._list_thumbnail_rows) > 64:
            identity, previous = self._list_thumbnail_rows.popitem(last=False)
            previous.thumbnail = False
            previous.icon = file_list_icon(previous.folder)
            self._thumbnail_requested.discard(identity)

    def _row_visible(self, row):
        if (self.closed or self.mode != 'List' or row.epoch != self.epoch
                or row.folder or not self.thumbnail or row.thumbnail
                or row.entry.identity in self._thumbnail_requested
                or len(self._thumbnail_pending) >= 24):
            return
        self._thumbnail_requested.add(row.entry.identity)
        decoded = self._decoded_thumbnails.get((row.entry.identity, row.entry.revision))
        if decoded is not None:
            self._set_row_thumbnail(row, decoded)
            return
        cached = self.icons.get((row.entry.identity, row.entry.revision))
        if cached:
            self._set_row_thumbnail(row, toga.Image(src=cached))
            return
        token = (row.epoch, row.entry.identity)
        self._thumbnail_pending.add(token)
        self._spawn(self._load_list_thumbnail(row, token))

    async def _load_list_thumbnail(self, row, token):
        browser = self
        class Target:
            @property
            def image(self):
                return row.icon
            @image.setter
            def image(self, image):
                if not browser.closed and row.epoch == browser.epoch and browser.mode == 'List':
                    browser._set_row_thumbnail(row, image)
        try:
            await self._load_thumbnail(row.entry, Target(), row.epoch, self.cancelled)
        finally:
            self._thumbnail_pending.discard(token)

    def stop(self):
        self._clear_tiles()
        self._decoded_thumbnails.clear()
        self.native_list.clear()
        self._list_entries = ()
        self._list_rows.clear()
        self._list_indices.clear()
        self._list_thumbnail_rows.clear()
        self._thumbnail_requested.clear()
        self._thumbnail_pending.clear()
        super().stop()
        self.entry_rows = {}

    TILE_ROW_HEIGHT = 164

    def _clear_tiles(self):
        restore = getattr(self, '_tile_restore', None)
        if restore is not None:
            restore.cancel()
        self._tile_entries = ()
        for identity in tuple(self._tile_cards):
            self._retire_tile(identity)
        self._tile_row_views.clear()
        rows = getattr(self, '_tile_rows', None)
        if rows is not None:
            for child in list(rows.children):
                rows.remove(child)
        self._tile_rows = None
        self._tile_range = None
        if hasattr(self, 'items'):
            for child in list(self.items.children):
                self.items.remove(child)

    def _render_tiles(self):
        if self.closed:
            return
        self._cancel()
        self._clear_tiles()
        self.buttons.clear()
        self.entry_rows = {}
        self._tile_entries = tuple(self.entries)
        self._tile_top = toga.Box(style=Pack(height=0))
        self._tile_rows = toga.Box(style=Pack(direction=COLUMN))
        self._tile_bottom = toga.Box(style=Pack(height=0))
        self.items.add(self._tile_top, self._tile_rows, self._tile_bottom)
        if not self._tile_entries:
            self._tile_rows.add(toga.Label('No matching items.' if self.search.value else 'This folder is empty.'))
        else:
            self._update_tile_window(0)
        self.page_label.text = ''

    def _tile_scrolled(self, widget, **kwargs):
        if not self.closed and self.mode == 'Tiles' and not getattr(self, '_tile_updating', False):
            self._tile_scroll_serial = getattr(self, '_tile_scroll_serial', 0) + 1
            self._update_tile_window(widget.vertical_position)

    def _update_tile_window(self, position):
        entries = self._tile_entries
        total = (len(entries) + 1) // 2
        if not total:
            return
        height = self._tile_scroll.layout.content_height or self._app.main_window.size.height or 640
        count = min(40, max(6, int(height / self.TILE_ROW_HEIGHT) + 5))
        start = min(max(0, total - count), max(0, int(position / self.TILE_ROW_HEIGHT) - 2))
        end = min(total, start + count)
        if self._tile_range == (start, end):
            return
        self._tile_range = start, end
        self._tile_updating = True
        try:
            for row_index in set(self._tile_row_views) - set(range(start, end)):
                self._tile_rows.remove(self._tile_row_views.pop(row_index))
                for entry in entries[row_index * 2:row_index * 2 + 2]:
                    self._retire_tile(entry.identity)
            self._tile_top.style.height = start * self.TILE_ROW_HEIGHT
            self._tile_bottom.style.height = (total - end) * self.TILE_ROW_HEIGHT
            for offset, row_index in enumerate(range(start, end)):
                if row_index in self._tile_row_views:
                    continue
                row = toga.Box(style=Pack(direction=ROW, height=self.TILE_ROW_HEIGHT))
                for entry in entries[row_index * 2:row_index * 2 + 2]:
                    row.add(self._tile_card(entry))
                if len(row.children) == 1:
                    row.add(toga.Box(style=Pack(flex=1)))
                self._tile_row_views[row_index] = row
                self._tile_rows.insert(offset, row)
            self.highlight_selection()
            from .keyboard import bind_browser
            bind_browser(self)
        finally:
            self._tile_updating = False
        epoch, serial = self.epoch, getattr(self, '_tile_scroll_serial', 0)
        def restore():
            if (not self.closed and self.mode == 'Tiles' and self.epoch == epoch
                    and self._tile_range == (start, end)
                    and getattr(self, '_tile_scroll_serial', 0) == serial):
                # The total extent is unchanged. Avoid clamping to a stale
                # native maximum while the recycled rows are being laid out.
                self._tile_scroll._impl.set_position(0, int(position))
        self._tile_restore = self._loop.call_soon(restore)

    def _retire_tile(self, identity):
        _, card, button, cancelled, task = self._tile_cards.pop(identity)
        cancelled.set()
        if task is not None:
            task.cancel()
        button.text = ''
        for view in card.children[0].children:
            if isinstance(view, toga.ImageView):
                view.image = None
        self.buttons.pop(identity, None)
        self.entry_rows.pop(identity, None)

    def _tile_card(self, entry):
        preview = toga.ImageView(style=Pack(width=96, height=96)) if self.thumbnail and not entry.container else entry_icon(entry.container)
        image_box = toga.Box(children=[preview], style=Pack(height=96, align_items='center', justify_content='center'))
        button = toga.Button(entry.payload.get('display_name') or PurePosixPath(entry.label).name,
            on_press=partial(self._select_pressed, entry), style=Pack(height=44))
        list_button(button)
        middle_filename(button)
        card = toga.Box(children=[image_box, button], style=Pack(direction=COLUMN, flex=1, margin=4))
        cancelled = Event()
        task = None
        cached = self.icons.get((entry.identity, entry.revision))
        if cached and self.thumbnail and not entry.container:
            preview.image = toga.Image(src=cached)
        elif self.thumbnail and not entry.container:
            browser, epoch = self, self.epoch
            class Target:
                @property
                def image(self):
                    return preview.image
                @image.setter
                def image(self, image):
                    if (not cancelled.is_set() and not browser.closed and browser.epoch == epoch
                            and entry.identity in browser._tile_cards):
                        preview.image = image
            task = self._loop.create_task(self._load_thumbnail(entry, Target(), epoch, cancelled))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
        self._tile_cards[entry.identity] = entry, card, button, cancelled, task
        self.buttons[entry.identity] = button
        self.entry_rows[entry.identity] = card
        return card

    async def _select_pressed(self, entry, widget, **kwargs):
        with self.population_paused():
            if self.closed or self.navigation_busy or not self._entry_current(entry):
                return
            if entry.container and self.on_open_folder:
                self.navigation_busy = True
                try:
                    result = self.on_open_folder(entry.payload)
                    if inspect.isawaitable(result):
                        await result
                finally:
                    self.navigation_busy = False
                return
            if not entry.container and self.on_open_file and not self.closed:
                tree = self.tree
                self.navigation_busy = True
                try:
                    # A file tap opens the document. Do not first read its archive
                    # metadata (or queue behind thumbnail workers) for the browser's
                    # information panel, which is about to leave the screen.
                    self.selected = entry.identity
                    for child in list(self.info.children):
                        self.info.remove(child)
                    self.highlight_selection()
                    if self.on_selected:
                        selected = self.on_selected(entry.payload)
                        if inspect.isawaitable(selected):
                            await selected
                    if (self.closed or self.tree is not tree or self.selected != entry.identity
                            or not self._entry_current(entry)):
                        return
                    result = self.on_open_file(entry.payload)
                    if inspect.isawaitable(result):
                        await result
                finally:
                    self.navigation_busy = False
                return
            await super()._select_pressed(entry, widget, **kwargs)

    def highlight_selection(self):
        if self.mode == 'List':
            index = self._list_indices.get(self.selected)
            self.native_list.select_index(index)
            return
        for identity, row in getattr(self, 'entry_rows', {}).items():
            selected = identity == self.selected
            button = self.buttons[identity]
            if getattr(row, '_browser_selected', None) != selected:
                highlight_entry(row, selected)
                highlight_entry(button, selected)
                row._browser_selected = selected
            # The shared selection handler marks only the current button.
            # Avoid native text reads and restyling every other visible row.
            if selected:
                text = button.text
                if text.startswith('✓ '):
                    button.text = text.removeprefix('✓ ')

    async def select(self, entry):
        try:
            await super().select(entry)
        finally:
            # Selection is for contextual actions, never a multi-select checkbox.
            self.highlight_selection()
