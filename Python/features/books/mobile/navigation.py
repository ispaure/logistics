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
