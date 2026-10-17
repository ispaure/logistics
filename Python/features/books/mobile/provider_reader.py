"""Native private EPUB reader, sharing the imported reader's safe HTML and bridge."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.books.locations import ChapterText, contents, link_destination
from .content import chapter_html
from .presentation import chapter_view
from .private_view import PrivateWebView, private_webview_supported
from .text_reader import TextBookView
from .navigation import ChapterTools


class RichBookView(toga.Box):
    def __init__(self, book, index, *, offset=0, font_size=16, margin=16, theme='system', typography=None, on_chapter, on_position):
        self.book, self.index, self.offset = book, index, offset
        self.on_chapter, self.on_position = on_chapter, on_position
        self.disposed, self.loading = False, True
        content = chapter_html(book, index, font_size, margin=margin, theme=theme, links=True, **(typography or {}))
        self.chapter = ChapterText(content)
        self.offset = min(max(0, offset), self.chapter.length)
        self.choices = {f'{n+1}. ' + '  '*entry.depth + entry.label: entry
                        for n, entry in enumerate(contents(book))}
        selected = next((label for label, entry in self.choices.items() if entry.index == index), None)
        self.toc = toga.Selection(items=list(self.choices), value=selected,
            on_change=self.choose, style=Pack(height=44))
        self.query = toga.TextInput(placeholder='Find in chapter…', on_confirm=self.find, style=Pack(height=44, flex=1))
        self.status = toga.Label('Private reader · position and\nbookmarks stay in this session')
        self.webview = chapter_view(content, PrivateWebView(style=Pack(flex=1)), offset=self.offset,
            on_event=self.event, on_link=self.link)
        self.tools = ChapterTools([self.toc,
            toga.Box(children=[self.query, toga.Button('Find next', on_press=self.find, style=Pack(height=44))],
                     style=Pack(direction=ROW)), self.status])
        super().__init__(children=[self.tools.widget, self.webview], style=Pack(direction=COLUMN, flex=1))
        self.loading = False

    def event(self, action, offset):
        if self.disposed:
            return
        self.offset = min(max(0, offset), self.chapter.length)
        self.on_position(self.offset)
        if action in {'previous', 'next'}:
            target = self.index + (1 if action == 'next' else -1)
            if 0 <= target < len(self.book.spine):
                self.on_chapter(target, 0 if action == 'next' else 16 * 1024 * 1024)

    def choose(self, widget, **kwargs):
        if not self.loading and not self.disposed and widget.value in self.choices:
            entry = self.choices[widget.value]
            self.tools.close()
            self.on_chapter(entry.index, entry.fragment)

    def link(self, href):
        if not self.disposed:
            index, fragment = link_destination(self.book, self.index, href)
            self.on_chapter(index, fragment)

    def seek(self, offset):
        if not self.disposed:
            self.offset = min(max(0, offset), self.chapter.length)
            self.webview._chapter_bridge.seek(self.offset)
            self.on_position(self.offset)

    def turn(self, direction):
        if self.disposed:
            return False
        self.webview._chapter_bridge.turn(direction)
        return True

    def find(self, widget=None, **kwargs):
        if self.disposed:
            return
        found = self.chapter.find(self.query.value, self.offset + 1)
        if found is None:
            self.status.text = 'No matching text in this chapter.'
            return
        start, end = found
        self.offset = start
        self.webview._chapter_bridge.seek(start, end)
        self.on_position(start)
        self.tools.close()

    def dispose(self):
        if self.disposed:
            return
        self.close_read_aloud()
        self.disposed = True
        self.webview._chapter_bridge.dispose()
        if self.webview in self.children:
            self.remove(self.webview)
        self.webview.clear_private_content()
        self.query.value = self.status.text = ''
        self.toc.items = []
        self.choices = {}
        self.book = self.chapter = None
        self.on_chapter = self.on_position = lambda *args: None


    def show_read_aloud(self, loop):
        self.close_read_aloud()
        from .speech_view import ReadAloudPanel
        from .presentation import speech_source
        async def source():
            return await speech_source(self.webview, self.chapter, self.offset)
        def follow(start, end):
            if not self.disposed:
                self.offset = start
                self.webview._chapter_bridge.seek(start, end)
                self.on_position(start)
        self.speech_panel = ReadAloudPanel(loop=loop, source=source, on_range=follow, close=self.close_read_aloud)
        self.insert(0, self.speech_panel)

    def close_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, 'speech_panel', None)
        if panel is not None:
            panel.dispose()
            self.remove(panel)
            del self.speech_panel


def provider_view(book, index, *, offset=0, font_size=16, margin=16, theme='system', typography=None, on_chapter, on_position):
    if private_webview_supported():
        return RichBookView(book, index, offset=offset, font_size=font_size, margin=margin, theme=theme, typography=typography,
            on_chapter=on_chapter, on_position=on_position)
    return TextBookView(book, index, offset=offset, font_size=font_size,
        on_chapter=on_chapter, on_position=on_position)
