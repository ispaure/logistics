"""Chapter labels and shared hierarchical navigation for mobile readers."""
from commonUtils.ui.native.presentation import HierarchyList


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


class ChapterList(HierarchyList):
    """Book destinations use the shared documentation/contents row language."""
    def __init__(self, entries, choose, *, row_style=None, current=None):
        self.current = current
        super().__init__(entries, choose, row_style=row_style)

    def render(self):
        target = next((entry for entry in self.entries if entry.index == self.current), None)
        self.selected = lambda entry: entry is target
        super().render()
        for row in self.rows.children:
            row.title_button.chapter_entry = row.title_button.hierarchy_entry


def chapter_sidebar(content):
    """Scroll chapters and bookmarks together inside even a short landscape pane."""
    import toga
    from toga.style import Pack
    class ChapterSidebar(toga.ScrollContainer):
        _MIN_HEIGHT = 44
    return ChapterSidebar(horizontal=False, content=content, style=Pack(flex=1))
