"""Shared retained panels and document rows for Home and Documents."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
from weakref import WeakSet

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

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
            foreground=name if name.startswith('folder_') else 'file_icon', eink_outlined=False))
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
    impl = button._impl
    backend = type(impl).__module__
    if backend.startswith('toga_iOS.'):
        impl.native.contentVerticalAlignment = 2  # UIControlContentVerticalAlignmentBottom
    elif backend.startswith('toga_android.'):
        from android.view import Gravity
        impl.native.setGravity(Gravity.START | Gravity.BOTTOM)
    # Balance the empty space above the bottom-aligned title below the caption,
    # so the two text lines sit together beside the thumbnail and row actions.
    caption.style.margin_top = -2
    caption.style.margin_bottom = 17
    return toga.Box(children=[button, caption], style=Pack(direction=COLUMN, flex=1, justify_content=CENTER))


def completion_caption(percent):
    role = 'muted' if percent == 0 else 'reading_complete' if percent == 100 else 'reading_active'
    return f'{percent}%', role


def make_completion_badge():
    return toga.Label('', style=Pack(width=56, height=18, text_align='right',
                                    font_size=12, font_weight='bold', margin_right=4))


def paint_completion_badge(badge, percent):
    badge.text, role = completion_caption(percent)
    surface(badge, radius=0, background='transparent', foreground=role,
            outlined=False, eink_outlined=False)


class DocumentCardMedia:
    """Load artwork and progress for the cards in one retained list."""

    def __init__(self, app):
        from threading import Event
        from .browser_preview import dark_notebook_thumbnails

        self.app = app
        self.pending_artwork = []
        self.notebook_artwork = []
        self.dark_notebooks = dark_notebook_thumbnails(app)
        self.notebook_appearance_revision = 0
        self.pending_progress = []
        self.cancelled = Event()

    def completion_badge(self, target):
        if target is None:
            return None
        badge = make_completion_badge()
        self.pending_progress.append((target, badge))
        return badge

    def artwork(self, reference, kind, *, width=72, height=72):
        from .browser_preview import PREVIEW_SUFFIXES
        from toga.style.pack import CENTER

        glyph = {'notebook': 'nav_notebooks', 'notes': 'markdown', 'archive': 'archives'}.get(kind, kind)
        placeholder = template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24)))
        artwork = toga.Box(children=[toga.Box(style=Pack(flex=1)), placeholder, toga.Box(style=Pack(flex=1))],
            style=Pack(direction=ROW, align_items=CENTER, width=width, height=height,
                       margin=(3, 8, 3, 4)))
        artwork._document_artwork = True
        native = type(self.app._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))
        if (native and reference and reference.get('type') == 'local'
                and Path(reference.get('path', '')).suffix.lower() in PREVIEW_SUFFIXES):
            row = (reference['path'], artwork, placeholder, width, height)
            self.pending_artwork.append(row)
            if Path(reference['path']).suffix.lower() == '.rmdoc':
                if not hasattr(self.app, '_notebook_card_media'):
                    self.app._notebook_card_media = WeakSet()
                self.app._notebook_card_media.add(self)
                self.notebook_artwork.append(row)
        return surface(artwork, radius=8, background='hover', eink_outlined=False)

    def start(self):
        if self.pending_artwork:
            pending, self.pending_artwork = self.pending_artwork, []
            self.app.loop.create_task(self._load_artwork(pending, self.dark_notebooks, self.notebook_appearance_revision))
        if self.pending_progress:
            pending_progress, self.pending_progress = self.pending_progress, []
            self.app.loop.create_task(self._load_progress(pending_progress))

    def cancel(self):
        self.cancelled.set()
        self.pending_artwork.clear()
        self.pending_progress.clear()
        self.notebook_artwork.clear()

    def refresh_notebook_thumbnails(self, dark):
        if not self.active() or dark == self.dark_notebooks:
            return
        self.dark_notebooks = dark
        self.notebook_appearance_revision += 1
        for _, artwork, placeholder, _, _ in self.notebook_artwork:
            cover = getattr(artwork, '_document_cover', None)
            if cover is not None:
                artwork.remove(cover)
                artwork.insert(1, placeholder)
                artwork._document_cover = None
        if self.notebook_artwork and not self.pending_artwork:
            self.app.loop.create_task(self._load_artwork(list(self.notebook_artwork), dark,
                                                       self.notebook_appearance_revision))

    def active(self):
        return self.app.active_host and not self.cancelled.is_set()

    async def _load_progress(self, pending):
        from .document_completion import load_percentage
        for target, badge in pending:
            if not self.active():
                return
            percent = await load_percentage(self.app, target, active=self.active)
            if percent is not None and self.active():
                paint_completion_badge(badge, percent)
                badge.style.display = 'pack'

    async def _load_artwork(self, pending, dark, revision):
        import asyncio
        from commonUtils.runtime.operations import OperationCancelled
        from commonUtils.runtime.resources.local import LocalFiles
        from .browser_preview import LocalThumbnails, local_image_bridge
        from .document_sources import local_document_path

        def load(path, width, height):
            physical = local_document_path(self.app, path)
            provider = LocalFiles(physical.parent)
            return LocalThumbnails(provider, local_image_bridge(), '', dark_notebooks=dark).load(
                provider.entry(physical.name), (width * 2, height * 2), self.cancelled.is_set)

        for path, artwork, placeholder, width, height in pending:
            if not self.active():
                return
            notebook = Path(path).suffix.lower() == '.rmdoc'
            if notebook and revision != self.notebook_appearance_revision:
                continue
            try:
                data = await asyncio.to_thread(load, path, width, height)
                if data and self.active() and (not notebook or revision == self.notebook_appearance_revision):
                    cover = toga.Image(src=data)
                    scale = min(width / cover.width, height / cover.height)
                    image = toga.ImageView(cover, style=Pack(width=max(1, round(cover.width * scale)),
                                                           height=max(1, round(cover.height * scale))))
                    artwork.remove(placeholder)
                    artwork.insert(1, image)
                    artwork._document_cover = image
            except (OSError, ValueError, RuntimeError, OperationCancelled):
                continue

def card_trailing(badge, tools):
    if badge is None or not tools:
        return tools
    menu, *other_tools = tools
    # Tuck the caption into the blank space above the glyph while retaining
    # the full overflow touch target. Align it to the menu even with Close beside it.
    badge.style.update(width=menu.style.width, text_align='center', margin_right=0, margin_bottom=-16,
                       display='none')
    surface(menu, radius=0, background='transparent', foreground='text', eink_outlined=False)
    return [toga.Box(children=[badge, menu], style=Pack(direction=COLUMN, align_items=CENTER)),
            *other_tools]


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


def library_discovery_heading(section, title, style, *, font_size=13):
    heading = toga.Label(title, style=style)
    status = empty_document_row('– Looking for libraries…')
    status.style.update(font_size=font_size, margin_bottom=0, margin_left=8)
    row = toga.Box(children=[heading, status], style=Pack(direction=ROW, align_items='center'))
    section.add(row)

    def finish():
        index = list(section.children).index(row)
        row.remove(heading)
        section.remove(row)
        section.insert(index, heading)

    return finish


def document_list(rows, empty_text, *, outlined=False):
    return document_group(rows, outlined=outlined) if rows else empty_document_row(empty_text)

def retire_document_actions(widget):
    """Release each row's menu before removing its containing section."""
    menu = getattr(widget, 'document_actions', None)
    if menu is not None:
        menu.dispose()
    previews = getattr(widget, '_document_card_media', None)
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
        # The navigation container owns the current safe width. This retained
        # view can still have its previous orientation's bounds during reflow.
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
