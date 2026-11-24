"""Project Notes Library rows and publish them to the active Files or Search panel."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
import posixpath

import toga
from toga.style import Pack
from toga.style.pack import CENTER, ROW

from commonUtils.search.names import search_terms
from ..notes import document_kind
from .library_panels import ENTRY_ICON_SIZE, FILENAME_SIZE


@dataclass(frozen=True)
class TreeRow:
    path: str
    directory: bool
    page: str | None
    depth: int
    label: str
    expanded: bool
    searching: bool

    @property
    def cache_key(self):
        return (self.searching, self.path, self.directory, self.page, self.depth,
                self.label, self.expanded)

    def native_record(self):
        return dict(title=self.label, subtitle='', folder=self.directory, icon=None,
                    path=self.path, page=self.page, searching=self.searching, tree_depth=self.depth,
                    tree_expanded=self.expanded if self.directory and not self.searching else None,
                    tree_landing=self.page is not None and not self.searching)


def _visible_folder_entries(folder, folders, expanded, visible, depth=0):
    for entry in folders.get(folder, ()):
        path, directory = entry['path'], entry['directory']
        if not visible(path, directory=directory):
            continue
        yield entry, depth
        if directory and path in expanded:
            yield from _visible_folder_entries(path, folders, expanded, visible, depth + 1)


class TreeProjection:
    def __init__(self, root, folders, expanded, visible, *, search_rows=None):
        self.root = root
        self.searching = search_rows is not None
        if self.searching:
            self.entries = [(entry, 0) for entry in search_rows
                            if visible(entry['path'], directory=entry['directory'])]
            self.name_counts = Counter(PurePosixPath(entry['path']).name.casefold()
                                       for entry, _ in self.entries)
        else:
            self.entries = list(_visible_folder_entries(root, folders, expanded, visible))

    def index_of(self, path):
        if path is not None:
            return next((index for index, (entry, _) in enumerate(self.entries)
                         if entry['path'] == path), None)
        return None

    def row(self, entry, depth, *, expanded, folder_pages):
        path, directory = entry['path'], entry['directory']
        page = None
        if directory:
            page = entry.get('page') if self.searching else folder_pages.get(path)
        if self.searching:
            label = PurePosixPath(path).name
            if self.name_counts[label.casefold()] > 1:
                parent = posixpath.dirname(posixpath.relpath(path, self.root or '.'))
                label += ' · ' + (parent or 'Library root')
        else:
            label = entry['name']
        return TreeRow(path, directory, page, depth, label, path in expanded, self.searching)


def batched_tree_updates(updates, batch_rows):
    try:
        while True:
            # Controls acquire provisional styles during construction. Paint
            # each control's final style once before returning to the event loop.
            with batch_rows():
                try:
                    next(updates)
                except StopIteration:
                    return
            yield
    finally:
        updates.close()


async def run_tree_updates(updates, *, valid, clock):
    deadline, count = clock() + .008, 0
    try:
        for _ in updates:
            if not valid():
                break
            count += 1
            # Cached rows and cleanup share the same time slice as new rows.
            if count >= 8 or clock() >= deadline:
                await asyncio.sleep(.001)
                deadline, count = clock() + .008, 0
    finally:
        updates.close()


def _tree_message(owner, projection):
    if projection.searching:
        if not search_terms(owner.search.value or ''):
            return 'Search file names or document contents.'
        if owner.search_status:
            return owner.search_status
        return '' if projection.entries else 'No matching notes or folders.'
    return '' if projection.entries else 'No documents in this folder.'


def update_tree_rows(owner, *, reveal, preserve_viewport):
    old_rows = dict(getattr(owner, '_row_cache', {}))
    owner._row_cache = dict(old_rows)
    searching = getattr(owner, 'panel_tab', 'Files') == 'Search'
    projection = TreeProjection(owner.root, owner.folders, owner.expanded, owner.host.folder_visible,
                                search_rows=owner.search_rows if searching else None)
    reveal_index = projection.index_of(reveal)
    message = _tree_message(owner, projection)
    if getattr(owner.rows, 'recycled', False):
        _publish_native_rows(owner, projection, message, reveal_index, preserve_viewport)
        yield
    else:
        yield from _widget_tree_updates(owner, projection, old_rows, message, reveal_index, preserve_viewport)


def _publish_native_rows(owner, projection, message, reveal_index, preserve_viewport):
    records = [projection.row(entry, depth, expanded=owner.expanded,
                               folder_pages=owner.folder_pages).native_record()
               for entry, depth in projection.entries]
    owner.rows.message(message)
    position = owner.search_position() if preserve_viewport else None
    owner.rows.add(*records)
    if reveal_index is not None:
        owner.rows.native_list.scroll_to_row(reveal_index)
    elif position is not None:
        owner.restore_search_position(position)
    owner.sidebar.refresh_gestures()


def _widget_tree_updates(owner, projection, old_rows, message, reveal_index, preserve_viewport):
    new_rows, desired = {}, []
    if reveal_index is not None:
        owner.shown = max(owner.shown, reveal_index + 1)
    for entry, depth in projection.entries[:owner.shown]:
        row = projection.row(entry, depth, expanded=owner.expanded, folder_pages=owner.folder_pages)
        key = row.cache_key
        widget = old_rows.get(key)
        if widget is None:
            widget = _make_widget_row(owner, row)
        new_rows[key] = owner._row_cache[key] = widget
        button = next(child for child in widget.children if hasattr(child, 'vault_path'))
        selected = row.path == owner.selected_path
        if getattr(widget, '_notes_selected', None) != selected:
            owner.style_tree_selection(widget, button, selected)
        if row.page is not None and not row.searching:
            underline_folder_link(button)
        desired.append(widget)
        yield

    desired.extend(_widget_row_footer(owner, len(projection.entries), message))
    changed = _publish_widget_rows(owner, desired, reveal_index, preserve_viewport)
    for key, widget in list(owner._row_cache.items()):
        if key not in new_rows:
            # Put the cache in a reusable state before yielding cleanup work.
            owner._row_cache.pop(key, None)
            for button in widget.children:
                if hasattr(button, 'vault_path'):
                    owner.release_file_hold(button)
            yield
    owner._row_cache = new_rows
    if changed:
        owner.sidebar.refresh_gestures()


def _widget_row_footer(owner, total, message):
    if total > owner.shown:
        if not hasattr(owner, '_more_rows'):
            panel = owner._row_panel

            def more(widget=None, **kwargs):
                if owner._row_panel != panel:
                    return
                owner.shown += 50
                owner.render_tree()

            owner._more_rows = toga.Button('Show more notes', on_press=more, style=Pack(height=48))
        yield owner._more_rows
    if message:
        if not hasattr(owner, '_rows_message'):
            owner._rows_message = toga.Label(message)
        elif owner._rows_message.text != message:
            owner._rows_message.text = message
        yield owner._rows_message


def _publish_widget_rows(owner, desired, reveal_index, preserve_viewport):
    changed = list(owner.rows.children) != desired
    if changed:
        # Mount the complete batch once the offscreen row work has finished.
        position = owner.search_position() if preserve_viewport else None
        owner.rows.clear()
        owner.rows.add(*desired)
        if position is not None:
            owner.restore_search_position(position)
    if reveal_index is not None:
        owner.rows_scroll.vertical_position = min(
            reveal_index * 48, owner.rows_scroll.max_vertical_position)
    return changed


def _make_widget_row(owner, row):
    host = owner.host

    async def choose(widget=None, **kwargs):
        if row.page is not None:
            await owner.open_selected_note(row.page, row_path=row.path)
        elif row.searching and row.directory:
            await owner.reveal_folder(row.path)
        elif row.directory:
            await owner.toggle_folder(row.path)
        else:
            await owner.open_selected_note(row.path)

    button = host.list_button(toga.Button(row.label, on_press=choose,
        style=Pack(height=48, flex=1, font_size=host.style_font(FILENAME_SIZE))))
    host.middle_filename(button)
    compact_file_row_padding(button)
    button.vault_path = row.path
    owner.bind_file_hold(button, row.path, directory=row.directory)

    expandable = row.directory and not row.searching
    if expandable:
        async def expand(widget=None, **kwargs):
            await owner.toggle_folder(row.path)

        toggle_label = ('Collapse ' if row.expanded else 'Expand ') + row.label
        icon_name = 'folder_document' if row.page is not None else 'folder_hub'
        entry_icon = _folder_control(host.presentation, icon_name, toggle_label, expand,
                                    size=ENTRY_ICON_SIZE, width=32, foreground='file_icon')
        entry_icon.browser_entry_kind = 'folder_document' if row.page is not None else 'folder'
    else:
        entry_icon = host.entry_icon(row.directory, landing_page=row.page is not None)
        entry_icon.style.width = entry_icon.style.height = ENTRY_ICON_SIZE
        entry_icon.style.margin_left = entry_icon.style.margin_right = 2
    if hasattr(owner, 'file_drag') and owner.library.supports('rename'):
        owner.file_drag.bind(entry_icon, row.path, target=row.directory)
        button._notes_drag_icon = entry_icon

    widget = toga.Box(children=[toga.Box(style=Pack(width=row.depth * 12)), entry_icon, button],
                      style=Pack(direction=ROW, align_items=CENTER))
    if expandable:
        disclosure = _folder_control(host.presentation, 'down' if row.expanded else 'forward',
                                     toggle_label, expand, size=16, width=44, foreground='muted')
        widget.insert(2, disclosure)
    if (not row.directory and document_kind(row.path) == 'markdown'
            or any(owner.library.supports(action) for action in ('rename', 'delete'))):
        widget.add(_file_actions_button(owner, row.path))
    return widget


def _folder_control(presentation, icon, label, on_press, *, size, width, foreground):
    button = presentation.icon_button(icon, label, on_press=on_press)
    presentation.apply_icon(button, icon, label, size=size)
    button.style.width = width
    button.style.height = 48
    compact_file_row_padding(button)
    presentation.surface(button, radius=0, background='transparent', foreground=foreground, outlined=False)
    return button


def _file_actions_button(owner, path):
    async def show_actions(widget=None, **kwargs):
        await owner.file_actions(path)

    presentation = owner.host.presentation
    button = presentation.icon_button('more', 'Actions for ' + PurePosixPath(path).name, on_press=show_actions)
    button.style.width = 48
    compact_file_row_padding(button)
    presentation.surface(button, radius=0, background='transparent', foreground='muted', outlined=False)
    return button


def underline_folder_link(button):
    """Underline the native title without changing its filename or hit target."""
    button.notes_folder_link = True
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        native = button._impl.native
        title = ObjCClass('NSAttributedString').alloc().initWithString(button.text,
            attributes={'NSUnderline': 1, 'NSFont': native.titleLabel.font,
                        'NSColor': native.titleColorForState(0)})
        native.setAttributedTitle(title, forState=0)
    elif backend.startswith('toga_android.'):
        native = button._impl.native
        native.setPaintFlags(native.getPaintFlags() | 8)  # UNDERLINE_TEXT_FLAG
    return button


def compact_file_row_padding(button):
    """Reduce native horizontal gutters as well as the row's layout slots."""
    inset = 0 if getattr(button, 'control_icon', None) else 2
    button._impl._content_inset = button._impl._content_trailing_inset = inset
    if type(button._impl).__module__.startswith('toga_android.'):
        native = button._impl.native
        padding = button._impl.scale_in(2)
        native.setPaddingRelative(padding, native.getPaddingTop(), padding, native.getPaddingBottom())
