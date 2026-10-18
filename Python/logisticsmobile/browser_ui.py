"""Compact Logistics presentation over the shared, bounded native browser."""
import inspect
from pathlib import PurePosixPath
import toga
from .control_icons import apply_icon, icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from commonUtils.ui.native_browser import NativeBrowser
from commonUtils.ui.native.presentation import list_button
from .appearance import surface, template_icon
from .hub_icons import icon


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
        style=Pack(width=24, height=24, margin_left=8, margin_right=8)))
    image.browser_entry_kind = 'folder_document' if directory and landing_page else 'folder' if directory else 'file'
    return image


def highlight_entry(widget, selected):
    surface(widget, radius=8, background='hover' if selected else 'surface',
            foreground='text' if isinstance(widget, toga.Button) else None,
            outlined=False, eink_outlined=selected, eink_selected=selected)


class FolderLocationHeader(toga.Box):
    """Current storage identity and a parent/root navigation control."""
    def __init__(self, status, parent_button):
        self.parent_button = parent_button
        self.storage_icons = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        super().__init__(children=[parent_button, self.storage_icons, status],
                         style=Pack(direction=ROW, align_items=CENTER, margin_top=4))
        self.update('')

    def update(self, path, *, remote=False, encrypted=False):
        apply_icon(self.parent_button, 'up' if path else 'back',
                   'Parent folder' if path else 'Back to Folder Hub')
        for child in list(self.storage_icons.children):
            self.storage_icons.remove(child)
        from .folder_hub_style import compact_icon
        kinds = [('storage_remote', 'Online folder')] if remote else [('storage_local', 'On-device folder')]
        if encrypted:
            kinds.append(('storage_crypt', 'Encrypted folder'))
        for name, label in kinds:
            indicator = icon_button(name, label, enabled=False)
            compact_icon(indicator, width=28, height=48, size=20)
            self.storage_icons.add(indicator)


class FileBrowser(NativeBrowser):
    location_header = FolderLocationHeader
    @property
    def page_size(self):
        # Local and remote folders share the same widget bound in both layouts.
        return 40

    def __init__(self, *, open_file=None, item_actions=None, folder_visible=None, bounded_pages=True,
                 **kwargs):
        self.bounded_pages = bounded_pages
        self.folder_visible = folder_visible
        self.on_open_file, self.on_item_actions = open_file, item_actions
        super().__init__(**kwargs)
        # Keep search visible. Sorting and layout are secondary controls.
        for child in list(self.widget.children):
            self.widget.remove(child)
        self.search.placeholder = 'Search files and folders'
        for control in (self.search, self.sort, self.list_button, self.tile_button, self.previous, self.next):
            control.style.height = 48
        apply_icon(self.back_button, 'back', 'Go back')
        apply_icon(self.previous, 'back', 'Previous results')
        apply_icon(self.next, 'forward', 'Next results')
        self.options_button = toga.Button('Sort', on_press=self.toggle_options, style=Pack(height=48))
        self.options = toga.Box(children=[self.sort, self.list_button, self.tile_button],
                                style=Pack(direction=ROW, margin_bottom=8))
        self.paging = toga.Box(children=[self.previous, self.next], style=Pack(direction=ROW))
        self.search_panel.remove(self.close_search_button)
        self.widget.add(self.search_panel)
        self.widget.add(toga.Box(children=[self.back_button, self.page_label, self.options_button],
                                 style=Pack(direction=ROW, margin_top=4, margin_bottom=8)))
        self.navigation_controls = self.widget.children[-1]
        self.page_label.style.flex = 1
        self.page_label.style.font_size = 12
        self.widget.add(self.items)

    def set_entries(self, provider, directory, rows, *, location=None):
        rows = tuple(rows)
        super().set_entries(provider, directory, rows, location=location)
    def stop(self):
        self.entry_rows = {}
        return super().stop()

    @property
    def entries(self):
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
        self.search.focus()

    def close_search(self, widget=None, **kwargs):
        self.search.value = ''

    def toggle_options(self, widget=None, **kwargs):
        if self.options in self.widget.children:
            self.widget.remove(self.options)
        else:
            self.widget.insert(2, self.options)

    def render(self):
        if not self.bounded_pages or self.closed:
            return self._render()
        # Build a bounded page offscreen. Mutating a live UIKit stack for every
        # button and menu repeatedly relays out the entire screen.
        previous = self.items
        self.items = toga.Box(style=Pack(direction=COLUMN))
        try:
            self._render()
        except Exception:
            self.items = previous
            raise
        index = self.widget.children.index(previous)
        self.widget.remove(previous)
        self.widget.insert(index, self.items)

    def _render(self):
        super().render()
        if self.closed:
            return
        entries = self.entries[self.page * self.page_size:(self.page + 1) * self.page_size]
        for entry in entries:
            button = self.buttons[entry.identity]
            # Recursive results retain their full path as identity/payload.
            # Only the visible caption uses the final path component.
            button.text = PurePosixPath(entry.label).name
            list_button(button)
            middle_filename(button)
        self.entry_rows = {}
        entries_by_button = {self.buttons[entry.identity]: entry for entry in entries}
        for row in self.items.children:
            if not isinstance(row, toga.Box):
                continue
            row.style.margin_bottom = 4
            if self.mode == 'List':
                for child in list(row.children):
                    if isinstance(child, toga.ImageView) and self.thumbnail is None:
                        row.remove(child)
                    elif isinstance(child, toga.Button):
                        child.style.height = 52
                if self.on_item_actions and row.children:
                    entry = next((entries_by_button[child] for child in row.children if child in entries_by_button), None)
                    if entry is not None:
                        async def commands(widget=None, selected=entry, **kw):
                            if not self.closed and not self.navigation_busy:
                                await self.select(selected)
                                result = self.on_item_actions()
                                if inspect.isawaitable(result):
                                    await result
                        row.add(icon_button('more', 'Actions for ' + entry.label, on_press=commands))

        if self.mode == 'List':
            for row, entry in zip(self.items.children, entries):
                if not isinstance(row, toga.Box):
                    continue
                controls = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
                for child in list(row.children):
                    row.remove(child)
                    controls.add(child)
                row.style.direction = COLUMN
                # Keep metadata in the selected item's information panel.
                if entry.container:
                    for child in list(controls.children):
                        if isinstance(child, toga.ImageView):
                            controls.remove(child)
                    controls.add(toga.Label('›', style=Pack(width=18, font_size=18)))
                controls.insert(0, entry_icon(entry.container))
                row.add(controls)
                self.entry_rows[entry.identity] = row

        else:
            for entry in entries:
                tile = self.buttons[entry.identity].parent
                if not any(isinstance(child, toga.ImageView) for child in tile.children):
                    tile.insert(0, entry_icon(entry.container))
                self.entry_rows[entry.identity] = tile
        self.highlight_selection()

        from .keyboard import bind_browser
        bind_browser(self)

        if self.previous.enabled or self.next.enabled:
            if self.paging not in self.widget.children:
                self.widget.insert(self.widget.children.index(self.navigation_controls) + 1, self.paging)
        elif self.paging in self.widget.children:
            self.widget.remove(self.paging)
        if not self.previous.enabled and not self.next.enabled:
            count = len(self.entries)
            self.page_label.text = f'{count} item' + ('' if count == 1 else 's')

    async def _select_pressed(self, entry, widget, **kwargs):
        if self.closed or self.navigation_busy or not self.tree or entry.identity not in self.tree.entries or entry not in self.entries:
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
        await super()._select_pressed(entry, widget, **kwargs)
        if not entry.container and self.on_open_file and not self.closed:
            self.navigation_busy = True
            try:
                result = self.on_open_file(entry.payload)
                if inspect.isawaitable(result):
                    await result
            finally:
                self.navigation_busy = False

    def highlight_selection(self):
        for identity, row in getattr(self, 'entry_rows', {}).items():
            selected = identity == self.selected
            highlight_entry(row, selected)
            button = self.buttons[identity]
            button.text = button.text.removeprefix('✓ ')
            highlight_entry(button, selected)

    async def select(self, entry):
        try:
            await super().select(entry)
        finally:
            # Selection is for contextual actions, never a multi-select checkbox.
            self.highlight_selection()
