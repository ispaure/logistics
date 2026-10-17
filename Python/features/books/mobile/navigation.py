"""Chapter labels and compact navigation tools for mobile readers.

These labels describe spine items; nested TOC fragments remain a separate
navigation capability, rather than being presented as supported destinations.
"""


def chapter_labels(book):
    titles = {}
    for chapter in book.chapters:
        titles.setdefault(chapter.path, chapter.label)
    return [f'{index + 1}. {titles.get(path, f"Chapter {index + 1}")}'
            for index, path in enumerate(book.spine)]


class ChapterTools:
    """Keep native contents/search available without covering the reading area."""
    def __init__(self, controls):
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.panel = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=8))
        self.button = toga.Button('Contents & search', on_press=self.toggle, style=Pack(height=44))
        self.widget = toga.Box(children=[self.button], style=Pack(direction=COLUMN))

    def toggle(self, widget=None, **kwargs):
        if self.panel in self.widget.children:
            self.close()
        else:
            self.widget.add(self.panel)
            self.button.text = 'Hide contents & search'

    def close(self):
        if self.panel in self.widget.children:
            self.widget.remove(self.panel)
        self.button.text = 'Contents & search'


class ChapterList:
    """Nested contents rows with independent disclosure and chapter activation."""
    def __init__(self, entries, choose):
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.entries, self.choose = list(entries), choose
        self.collapsed = set()
        self.rows = toga.Box(style=Pack(direction=COLUMN))
        self.render()

    def render(self):
        import toga
        from toga.style import Pack
        from toga.style.pack import ROW
        from commonUtils.ui.native.presentation import list_button
        self.rows.clear()
        hidden_depth = None
        for number, entry in enumerate(self.entries):
            if hidden_depth is not None and entry.depth > hidden_depth:
                continue
            hidden_depth = None
            nested = number + 1 < len(self.entries) and self.entries[number + 1].depth > entry.depth
            children = [toga.Box(style=Pack(width=min(entry.depth, 12) * 16))]
            if nested:
                def toggle(widget=None, number=number, **kwargs):
                    if number in self.collapsed:
                        self.collapsed.remove(number)
                    else:
                        self.collapsed.add(number)
                    self.render()
                disclosure = toga.Button('▸' if number in self.collapsed else '▾', on_press=toggle, style=Pack(width=48, height=48))
                disclosure.accessible_name = ('Expand ' if number in self.collapsed else 'Collapse ') + entry.label
                backend = type(disclosure._impl).__module__
                if backend.startswith('toga_iOS.'):
                    disclosure._impl.native.accessibilityLabel = disclosure.accessible_name
                elif backend.startswith('toga_android.'):
                    disclosure._impl.native.setContentDescription(disclosure.accessible_name)
                children.append(disclosure)
            def activate(widget=None, entry=entry, **kwargs):
                return self.choose(entry)
            button = list_button(toga.Button(entry.label, on_press=activate, style=Pack(height=48, flex=1)))
            button.chapter_entry = entry
            children.append(button)
            self.rows.add(toga.Box(children=children, style=Pack(direction=ROW)))
            if nested and number in self.collapsed:
                hidden_depth = entry.depth
