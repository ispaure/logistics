"""Shared retained panels and document rows for Home and Documents."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .appearance import surface, template_icon
from .hub_icons import icon


DOCUMENT_TYPES = {'text': 'Text', 'markdown': 'Markdown', 'epub': 'EPUB books', 'comic': 'Comics', 'pdf': 'PDF documents', 'video': 'Videos'}
SHOW_SOURCE_TEXT = True


def source_caption(kinds, *, row=None, text=None):
    """Use the reader's colored storage symbols beside a short subtitle."""
    from toga.style.pack import CENTER
    from .appearance import accessible_name

    if row is None:
        row = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin=(0, 4, 6, 8)))
    elif getattr(row, '_source_caption_state', None) == (tuple(kinds), text, SHOW_SOURCE_TEXT):
        return row
    row._source_caption_state = (tuple(kinds), text, SHOW_SOURCE_TEXT)
    row.clear()
    glyphs = {'storage_crypt': 'folder_locked', 'storage_unlocked': 'folder_unlocked'}
    for glyph, label in kinds:
        name = glyphs.get(glyph, glyph)
        symbol = template_icon(toga.ImageView(icon(name), style=Pack(width=12, height=12, margin_right=4)))
        accessible_name(symbol, label)
        row.add(surface(symbol, radius=0, background='transparent',
            foreground=name if name.startswith('folder_') else 'accent', eink_outlined=False))
    if SHOW_SOURCE_TEXT and (text or kinds):
        if text is None:
            names = {name for name, _ in kinds}
            text = ('Cloud file' if 'storage_remote' in names else
                    'Encrypted copy' if names & {'storage_crypt', 'storage_unlocked'} else 'Local file')
            if 'storage_crypt' in names:
                text += ' · Locked'
        label = toga.Label(text,
            style=Pack(font_size=12, font_style='italic', flex=1))
        row.add(surface(label, radius=0, background='transparent', foreground='muted', eink_outlined=False))
    return row


def source_title(button, kinds, *, text=None):
    caption = button._source_caption = source_caption(kinds, text=text)
    return toga.Box(children=[button, caption], style=Pack(direction=COLUMN, flex=1))


class DocumentThumbnails:
    """Load local artwork in order, scoped to the lifetime of one retained list."""

    def __init__(self, app):
        from threading import Event

        self.app = app
        self.pending = []
        self.cancelled = Event()

    def artwork(self, reference, kind, *, width=72, height=72):
        from .browser_preview import PREVIEW_SUFFIXES
        from pathlib import Path
        from toga.style.pack import CENTER

        glyph = {'notebook': 'nav_notebooks', 'notes': 'markdown', 'archive': 'archives'}.get(kind, kind)
        placeholder = template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24)))
        artwork = toga.Box(children=[toga.Box(style=Pack(flex=1)), placeholder, toga.Box(style=Pack(flex=1))],
            style=Pack(direction=ROW, align_items=CENTER, width=width, height=height,
                       margin_left=4, margin_right=8))
        artwork._document_artwork = True
        native = type(self.app._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))
        if (native and reference and reference.get('type') == 'local'
                and Path(reference.get('path', '')).suffix.lower() in PREVIEW_SUFFIXES):
            self.pending.append((reference['path'], artwork, placeholder, width, height))
        return surface(artwork, radius=8, background='hover', eink_outlined=False)

    def start(self):
        if not self.pending:
            return
        pending, self.pending = self.pending, []
        self.app.loop.create_task(self._load(pending))

    def cancel(self):
        self.cancelled.set()
        self.pending.clear()

    async def _load(self, pending):
        import asyncio
        from commonUtils.runtime.operations import OperationCancelled
        from commonUtils.runtime.resources.local import LocalFiles
        from .browser_preview import LocalThumbnails, local_image_bridge
        from .document_sources import local_document_path

        def load(path, width, height):
            physical = local_document_path(self.app, path)
            provider = LocalFiles(physical.parent)
            return LocalThumbnails(provider, local_image_bridge(), '').load(
                provider.entry(physical.name), (width * 2, height * 2), self.cancelled.is_set)

        for path, artwork, placeholder, width, height in pending:
            if self.cancelled.is_set() or not self.app.active_host:
                return
            try:
                data = await asyncio.to_thread(load, path, width, height)
                if data and not self.cancelled.is_set() and self.app.active_host:
                    cover = toga.Image(src=data)
                    scale = min(width / cover.width, height / cover.height)
                    image = toga.ImageView(cover, style=Pack(width=max(1, round(cover.width * scale)),
                                                           height=max(1, round(cover.height * scale))))
                    artwork.remove(placeholder)
                    artwork.insert(1, image)
                    artwork._document_cover = image
            except (OSError, ValueError, RuntimeError, OperationCancelled):
                continue

def text_document_kind(name):
    return 'markdown' if name.lower().endswith(('.md', '.markdown')) else 'text'

def document_groups(items):
    """Keep type order stable and omit empty sections."""
    for kind, title in DOCUMENT_TYPES.items():
        group = [item for item in items if item[0] == kind]
        if group:
            yield title, group

def heading(text):
    return toga.Label(text, style=Pack(font_size=19, font_weight='bold', margin_top=16, margin_bottom=8))

def status_badges(details, *, currently_open=False, icon_count=0):
    """One quiet summary, retaining warnings and the platform's default font."""
    short_names = {'Unsaved changes': 'Unsaved', 'Recovered draft': 'Recovered'}
    statuses = ['Open'] if currently_open else []
    statuses.extend(short_names.get(detail, detail) for detail in details)
    return surface(toga.Label(' · '.join(statuses),
        style=Pack(font_size=12, margin=(0, 12, 8, 12 + 28 * icon_count + (4 if icon_count else 0)))),
        radius=0, background='transparent', foreground='muted',
        outlined=False, eink_outlined=False)

def document_group(rows, *, outlined=False):
    """One rounded surface for a document section, with quiet inset dividers."""
    group = surface(toga.Box(style=Pack(direction=COLUMN, margin_bottom=8)), radius=16,
                    outlined=outlined)
    group._document_group = True
    append_document_group_rows(group, rows)
    backend = type(group._impl).__module__
    if backend.startswith('toga_iOS.'):
        group._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        group._impl.native.setClipToOutline(True)
    return group

def append_document_group_rows(group, rows, *, compact=False):
    """Append rows without moving any existing hit targets."""
    def borderless(widget):
        if isinstance(widget, toga.Button):
            foreground = 'accent' if hasattr(widget, 'document_actions') else 'text'
            surface(widget, radius=0, background='transparent', foreground=foreground,
                    outlined=False, eink_outlined=False)
        elif isinstance(widget, toga.Box):
            if not getattr(widget, '_document_artwork', False):
                surface(widget, radius=0, background='transparent', outlined=False, eink_outlined=False)
        for child in widget.children:
            borderless(child)
    for index, row in enumerate(rows):
        first = not group.children
        if not first:
            group.add(surface(toga.Box(style=Pack(height=1, margin_left=16, margin_right=16)),
                radius=0, background='border', outlined=False, eink_outlined=False))
        row.style.margin_bottom = 8 if not compact and index == len(rows) - 1 else 0
        row.style.margin_top = 8 if first else 0
        row.style.margin_left = row.style.margin_right = 8
        borderless(row)
        group.add(row)

def empty_document_row(text):
    """Informational copy sits directly on the page, outside action surfaces."""
    return surface(toga.Label(text, style=Pack(font_size=13, margin_bottom=12)),
                   radius=0, background='transparent', foreground='muted',
                   outlined=False, eink_outlined=False)

def document_list(rows, empty_text, *, outlined=False):
    return document_group(rows, outlined=outlined) if rows else empty_document_row(empty_text)

def retire_document_actions(widget):
    """Release each row's menu before removing its containing section."""
    menu = getattr(widget, 'document_actions', None)
    if menu is not None:
        menu.dispose()
    previews = getattr(widget, '_document_thumbnails', None)
    if previews is not None:
        previews.cancel()
    for child in widget.children:
        retire_document_actions(child)

def panel(title, detail, glyph, actions):
    box = toga.Box(style=Pack(direction=COLUMN, margin=16))
    box.add(toga.Box(children=[
        template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24, margin_right=8))),
        toga.Label(title, style=Pack(flex=1, font_size=18, font_weight='bold'))],
        style=Pack(direction=ROW, margin_bottom=8)))
    if detail:
        box.add(toga.Label(detail, style=Pack(font_size=12, margin_bottom=4)))
    buttons = toga.Box(style=Pack(direction=ROW))
    for label, action in actions:
        buttons.add(toga.Button(label, on_press=action, style=Pack(height=48, flex=1)))
    box.add(buttons)
    return surface(toga.Box(children=[box], style=Pack(direction=COLUMN, margin_bottom=12)))

class PanelGrid(toga.Box):
    def __init__(self, cards, width, *, minimum_columns=1, maximum_columns=None):
        super().__init__(style=Pack(direction=COLUMN))
        self.cards = cards
        self.columns = 0
        self.minimum_columns = minimum_columns
        self.maximum_columns = maximum_columns
        self.reflow(width)

    def reflow(self, width):
        columns = max(self.minimum_columns, 3 if width >= 1100 else 2 if width >= 700 else 1)
        if self.maximum_columns is not None:
            columns = min(columns, self.maximum_columns)
        if columns == self.columns:
            return
        for row in list(self.children):
            for card in list(row.children):
                row.remove(card)
            self.remove(row)
        self.columns = columns
        for offset in range(0, len(self.cards), columns):
            row = toga.Box(style=Pack(direction=ROW))
            for index, card in enumerate(self.cards[offset:offset + columns]):
                card.style.flex = 1
                card.style.margin_right = 10 if index < columns - 1 else 0
                row.add(card)
            # Keep the final card the same width as all preceding cards.
            for _ in range(columns - len(row.children)):
                row.add(toga.Box(style=Pack(flex=1)))
            self.add(row)

class HubSections(toga.Box):
    """Retain hub controls while moving whole sections across a physical fold."""
    def __init__(self, content, trailing):
        super().__init__(style=Pack(direction=ROW, flex=1))
        self._hub_sections = True
        self.content = content  # Compact content compatibility for hub callers.
        self.trailing = trailing
        self.leading_scroll = toga.ScrollContainer(horizontal=False, content=content, style=Pack(flex=1))
        self.trailing_content = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.trailing_scroll = toga.ScrollContainer(horizontal=False, content=self.trailing_content,
                                                    style=Pack(flex=1))
        self.add(self.leading_scroll)
        self.paired = False

    def reflow(self, app, destination):
        from .fold_layout import division
        from .pane_layout import panes
        fold = division(app, self)
        width = app.adaptive.content_width(destination, margin=0)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            measured = float(self._impl.native.bounds.size.width)
            if measured > 0:
                # A retained landscape hub can still report its old width
                # after its destination returns to a portrait viewport.
                width = min(width, measured)
        paired = fold is not None or width >= 580
        if paired != self.paired:
            if self.trailing.parent is not None:
                self.trailing.parent.remove(self.trailing)
            if paired:
                self.trailing_content.add(self.trailing)
                self.add(self.trailing_scroll)
            else:
                self.remove(self.trailing_scroll)
                self.content.add(self.trailing)
            self.paired = paired
        allocation = panes(width, self.layout.content_height or 1, fold=fold, gutter=0)
        vertical = paired and allocation.axis == 'column'
        self.style.direction = COLUMN if vertical else ROW
        self.trailing_scroll.style.margin_left = allocation.gap if paired and not vertical else 0
        self.trailing_scroll.style.margin_top = allocation.gap if vertical else 0
        for scroll, size in ((self.leading_scroll, allocation.leading), (self.trailing_scroll, allocation.trailing)):
            del scroll.style.height
            if vertical:
                del scroll.style.width
                scroll.style.height, scroll.style.flex = size, 0
                continue
            if paired:
                size = max(1, size)
                if scroll.style.width != size:
                    scroll.style.width = size
                if scroll.style.flex != 0:
                    scroll.style.flex = 0
            else:
                from toga.style.pack import NONE
                if scroll.style.width != NONE:
                    del scroll.style.width
                if scroll.style.flex != 1:
                    scroll.style.flex = 1
