"""Memory-only native EPUB navigation when a private WebView is unsuitable."""
from bisect import bisect_left
from array import array
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.books.locations import ChapterText, contents, utf16_length, link_destination
from .content import chapter_html
from .navigation import ChapterTools


class TextBookView(toga.Box):
    """Exact passage anchors, nested contents and search without browser storage."""
    def __init__(self, book, index, *, offset=0, font_size=16, on_chapter, on_position):
        self.book, self.index = book, index
        self.on_chapter, self.on_position = on_chapter, on_position
        self.chapter = ChapterText(chapter_html(book, index, links=True))
        self.units = array('I', [0])
        for char in self.chapter.text:
            self.units.append(self.units[-1] + utf16_length(char))
        self.offset = offset
        self.choices = {f'{n+1}. ' + '  '*entry.depth + entry.label: entry
                        for n, entry in enumerate(contents(book))}
        self.loading = True
        selected = next((label for label, entry in self.choices.items() if entry.index == index), None)
        self.toc = toga.Selection(items=list(self.choices), value=selected, on_change=self.choose,
                                  style=Pack(height=44))
        self.link_choices = {f'{n+1}. {label or href}': href for n, (href, label) in enumerate(self.chapter.links)}
        self.link_selector = toga.Selection(items=['Links…'] + list(self.link_choices),
            on_change=self.choose_link, style=Pack(height=44))
        self.query = toga.TextInput(placeholder='Find in chapter…', on_confirm=self.find,
                                    style=Pack(height=44, flex=1))
        self.status = toga.Label('')
        self.text = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, font_size=font_size))
        self.loading = False
        self.tools = ChapterTools([self.toc, self.link_selector,
            toga.Box(children=[self.query, toga.Button('Find next', on_press=self.find, style=Pack(height=44))],
                     style=Pack(direction=ROW)), self.status])
        super().__init__(children=[self.tools.widget, self.text], style=Pack(direction=COLUMN, flex=1))
        self.seek(offset)

    def seek(self, offset):
        start = min(bisect_left(self.units, max(0, offset)), len(self.chapter.text))
        self.offset = self.units[start]
        # Bounded passages make the exact anchor visible at the top on every
        # native backend; native text views do not expose portable caret scroll.
        self.end = min(len(self.chapter.text), start + 1200)
        self.text.value = self.chapter.text[start:self.end]
        self.text.scroll_to_top()
        self.status.text = f'Text {self.offset}/{self.chapter.length}'
        self.on_position(self.offset)

    def turn(self, direction):
        if direction > 0 and self.end < len(self.chapter.text):
            self.seek(self.units[self.end])
            return True
        if direction < 0 and self.offset > 0:
            start = bisect_left(self.units, self.offset)
            self.seek(self.units[max(0, start - 1200)])
            return True
        return False

    def choose(self, widget, **kwargs):
        if not self.loading and widget.value in self.choices:
            entry = self.choices[widget.value]
            self.tools.close()
            self.on_chapter(entry.index, entry.fragment)

    def find(self, widget=None, **kwargs):
        result = self.chapter.find(self.query.value, self.offset + 1)
        if result is None:
            self.status.text = 'No matching text in this chapter.'
        else:
            self.seek(result[0])
            self.tools.close()

    def dispose(self):
        self.text.value = self.query.value = self.status.text = ''
        self.toc.items = []
        self.link_selector.items = []
        self.choices, self.link_choices, self.units = {}, {}, []
        self.book = self.chapter = None
        self.on_chapter = self.on_position = lambda *args: None


    def choose_link(self, widget, **kwargs):
        if not self.loading and widget.value in self.link_choices:
            index, fragment = link_destination(self.book, self.index, self.link_choices[widget.value])
            self.tools.close()
            self.on_chapter(index, fragment)
