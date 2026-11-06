"""Shared retained panels and document rows for Home and Documents."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

from .appearance import surface, template_icon
from .hub_icons import icon


DOCUMENT_TYPES = {'text': 'Text', 'markdown': 'Markdown', 'epub': 'EPUB books', 'comic': 'Comics', 'pdf': 'PDF documents', 'video': 'Videos'}

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

def document_group(rows):
    """One rounded surface for a document section, with quiet inset dividers."""
    group = surface(toga.Box(style=Pack(direction=COLUMN, margin_bottom=8)), radius=16)
    group._document_group = True
    def borderless(widget):
        if isinstance(widget, toga.Button):
            surface(widget, radius=0, background='transparent', foreground='text',
                    outlined=False, eink_outlined=False)
        elif isinstance(widget, toga.Box):
            surface(widget, radius=0, background='transparent', outlined=False, eink_outlined=False)
        for child in widget.children:
            borderless(child)
    for index, row in enumerate(rows):
        if index:
            group.add(surface(toga.Box(style=Pack(height=1, margin_left=16, margin_right=16)),
                radius=0, background='border', outlined=False, eink_outlined=False))
        row.style.margin_bottom = 8 if index == len(rows) - 1 else 0
        row.style.margin_top = 8 if index == 0 else 0
        row.style.margin_left = row.style.margin_right = 8
        borderless(row)
        group.add(row)
    backend = type(group._impl).__module__
    if backend.startswith('toga_iOS.'):
        group._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        group._impl.native.setClipToOutline(True)
    return group

def empty_document_row(text):
    """Informational copy sits directly on the page, outside action surfaces."""
    return surface(toga.Label(text, style=Pack(font_size=13, margin_bottom=12)),
                   radius=0, background='transparent', foreground='muted',
                   outlined=False, eink_outlined=False)

def document_list(rows, empty_text):
    return document_group(rows) if rows else empty_document_row(empty_text)

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
    def __init__(self, content, trailing, *, before=None):
        super().__init__(style=Pack(direction=ROW, flex=1))
        self._hub_sections = True
        self.content = content  # Compact content compatibility for hub callers.
        self.trailing = trailing
        self.before = before
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
        paired = fold is not None or width >= 700
        if paired != self.paired:
            if self.trailing.parent is not None:
                self.trailing.parent.remove(self.trailing)
            if paired:
                self.trailing_content.add(self.trailing)
                self.add(self.trailing_scroll)
            else:
                self.remove(self.trailing_scroll)
                index = self.content.children.index(self.before) if self.before is not None else len(self.content.children)
                self.content.insert(index, self.trailing)
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
