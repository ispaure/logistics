"""Compact Logistics presentation over the shared, bounded native browser."""
import inspect
import toga
from .control_icons import apply_icon, icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.ui.native_browser import NativeBrowser
from commonUtils.filesystem import format_size
from commonUtils.ui.native.presentation import list_button
from .appearance import surface


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


class FileBrowser(NativeBrowser):
    @property
    def page_size(self):
        if self.bounded_pages:
            return super().page_size
        # Ordinary folders scroll continuously; bound native widget creation
        # only for very large directories, in either presentation mode.
        return 500

    def __init__(self, *, open_file=None, item_actions=None, folder_visible=None, bounded_pages=False, **kwargs):
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
        # button, menu and size label repeatedly relays out the entire screen.
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
        for button in self.buttons.values():
            button.text = button.text.removeprefix('✓ ')
            list_button(button)
            middle_filename(button)
        entries = self.entries[self.page * self.page_size:(self.page + 1) * self.page_size]
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
                size = entry.properties.get('size')
                if entry.container:
                    detail = ''
                elif isinstance(size, (int, float)):
                    detail = format_size(size, binary_units=True)
                else:
                    detail = entry.suffix.lstrip('.').upper() or 'File'
                controls = toga.Box(style=Pack(direction=ROW))
                for child in list(row.children):
                    row.remove(child)
                    controls.add(child)
                row.style.direction = COLUMN
                # A single row per entry: folder icon/name, or file name/size.
                # Containers do not need a second 'Folder' line.
                if entry.container:
                    for child in list(controls.children):
                        if isinstance(child, toga.ImageView):
                            controls.remove(child)
                    controls.add(toga.Label('›', style=Pack(width=18, font_size=18, margin_top=12)))
                elif detail:
                    controls.insert(len(controls.children) - (1 if self.on_item_actions else 0),
                        toga.Label(detail, style=Pack(width=64, font_size=11, margin_top=17)))
                row.add(controls)
                surface(row)

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

    async def select(self, entry):
        try:
            await super().select(entry)
        finally:
            # Selection is for contextual actions, never a multi-select checkbox.
            for button in self.buttons.values():
                button.text = button.text.removeprefix('✓ ')
