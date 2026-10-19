"""Compact Logistics presentation over the shared native browser."""
import inspect
from functools import partial
import weakref
from pathlib import PurePosixPath
import toga
from .control_icons import apply_icon, icon_button
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

    def __init__(self, *, open_file=None, folder_visible=None, bounded_pages=True,
                 **kwargs):
        self.bounded_pages = bounded_pages
        self._list_slots = []
        self.folder_visible = folder_visible
        self.on_open_file = open_file
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
        self.widget.add(self.items)

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
        if self.search_panel not in self.widget.children:
            self.widget.insert(0, self.search_panel)
        self.search.focus()

    def close_search(self, widget=None, **kwargs):
        self.search.value = ''
        if self.search_panel in self.widget.children:
            self.widget.remove(self.search_panel)

    def render(self):
        if not self.bounded_pages or self.closed:
            return self._render()
        # Build the folder offscreen. Mutating a live UIKit stack for every
        # button and menu repeatedly relays out the entire screen.
        previous = self.items
        if self.mode == 'List' and self.thumbnail is None and not self.icons:
            # Detach the page once; update its retained rows offscreen without
            # moving every native child or laying out the mounted screen.
            self.widget.remove(previous)
            try:
                self._render()
            finally:
                self.widget.add(previous)
            return
        self.items = toga.Box(style=Pack(direction=COLUMN))
        try:
            self._render()
        except Exception:
            self.items = previous
            raise
        index = self.widget.children.index(previous)
        self.widget.remove(previous)
        self.widget.insert(index, self.items)

    def _render_list(self):
        """Reuse app-styled rows for the full folder, retaining no old entries."""
        self._cancel()
        self.page = 0
        self.previous.enabled = self.next.enabled = False
        visible = self.entries
        self.buttons.clear()
        self.entry_rows = {}
        retained = {slot[0] for slot in self._list_slots}
        for child in list(self.items.children):
            if child not in retained:
                self.items.remove(child)
        for index, entry in enumerate(visible):
            if index == len(self._list_slots):
                button = toga.Button('', style=Pack(height=ROW_HEIGHT, flex=1))
                list_button(button)
                folder_name(button)
                middle_filename(button)
                glyph = entry_icon(entry.container)
                chevron = toga.Label('›', style=Pack(width=18, font_size=18))
                controls = toga.Box(children=[glyph, button], style=Pack(direction=ROW, align_items=CENTER))
                row = toga.Box(children=[controls], style=Pack(direction=COLUMN))
                folder_row(row)
                self._list_slots.append((row, controls, glyph, button, chevron))
            row, controls, glyph, button, chevron = self._list_slots[index]
            kind = 'folder' if entry.container else 'file'
            if glyph.browser_entry_kind != kind:
                glyph.image = icon('files' if entry.container else 'documents')
                if type(glyph._impl).__module__.startswith('toga_iOS.'):
                    template_icon(glyph)
                    glyph._impl.native.tintColor = apple_color('accent')
                glyph.browser_entry_kind = kind
            if entry.container and chevron.parent is None:
                controls.add(chevron)
            elif not entry.container and chevron.parent is not None:
                controls.remove(chevron)
            caption = entry.payload.get('display_name') or PurePosixPath(entry.label).name
            if button.text != caption:
                button.text = caption
                middle_filename(button)
            button.on_press = partial(self._select_pressed, entry)
            self.buttons[entry.identity] = button
            self.entry_rows[entry.identity] = row
            if row.parent is not self.items:
                if row.parent is not None:
                    row.parent.remove(row)
                self.items.add(row)
        # Unused slots contain no decrypted names, entry closures or payloads.
        for row, _, _, button, _ in self._list_slots[len(visible):]:
            if row.parent is not None:
                row.parent.remove(row)
            button.text = ''
            accessible_name(button, '')
            button.on_press = None
        del self._list_slots[len(visible):]
        if not visible:
            self.items.add(toga.Label('No matching items.' if self.search.value else 'This folder is empty.'))

    def stop(self):
        super().stop()
        for _, _, _, button, _ in self._list_slots:
            button.text = ''
            accessible_name(button, '')
            button.on_press = None
        self._list_slots.clear()
        self.entry_rows = {}

    def _render(self):
        plain_list = self.mode == 'List' and self.thumbnail is None and not self.icons
        if plain_list and not self.closed:
            self._render_list()
        else:
            # Rich previews and tiles retain the shared browser renderer.
            for _, _, _, button, _ in self._list_slots:
                button.text = ''
                accessible_name(button, '')
                button.on_press = None
            self._list_slots.clear()
            super().render()
        if self.closed:
            return
        entries = self.entries
        for entry in (() if plain_list else entries):
            button = self.buttons[entry.identity]
            # Recursive results retain their full path as identity/payload.
            # Only the visible caption uses the final path component.
            button.text = entry.payload.get('display_name') or PurePosixPath(entry.label).name
            list_button(button)
            if self.mode == 'List':
                folder_name(button)
            middle_filename(button)
        if not plain_list:
            self.entry_rows = {}
        for row in (() if plain_list else self.items.children):
            if not isinstance(row, toga.Box):
                continue
            row.style.margin_bottom = ROW_GAP
            if self.mode == 'List':
                for child in list(row.children):
                    if isinstance(child, toga.ImageView) and self.thumbnail is None:
                        row.remove(child)
                    elif isinstance(child, toga.Button):
                        child.style.height = ROW_HEIGHT

        if self.mode == 'List' and not plain_list:
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
                folder_row(row)
                self.entry_rows[entry.identity] = row

        elif self.mode != 'List':
            for entry in entries:
                tile = self.buttons[entry.identity].parent
                if not any(isinstance(child, toga.ImageView) for child in tile.children):
                    tile.insert(0, entry_icon(entry.container))
                self.entry_rows[entry.identity] = tile
        self.highlight_selection()

        from .keyboard import bind_browser
        bind_browser(self)

        if self.paging in self.widget.children:
            self.widget.remove(self.paging)
        self.page_label.text = ''

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
                        or entry.identity not in tree.entries or entry not in self.entries):
                    return
                result = self.on_open_file(entry.payload)
                if inspect.isawaitable(result):
                    await result
            finally:
                self.navigation_busy = False
            return
        await super()._select_pressed(entry, widget, **kwargs)

    def highlight_selection(self):
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
