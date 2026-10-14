"""Compact reading controls, native action menus and explicit appearance routes."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .action_menu import FeatureCommands
from .reader_controls import ReadingFrame, schedule_swipe


def sync_comic_chrome(app, view):
    """Host decides when to hide chrome; shared adapters own native restoration."""
    def immersive(widget):
        return getattr(widget, '_comic_fullscreen', False) or any(immersive(child) for child in widget.children)
    hidden = immersive(view)
    app._comic_chrome_hidden = hidden
    navigation = app.adaptive.secondary if app.adaptive.split is not None and app.native_host.state.destination == 'documents' else None
    app.native_host.chrome.set_hidden(hidden, navigation=navigation)


class ReaderChrome:
    def compact_reader(self):
        old = self.library_view
        for child in list(old.children):
            old.remove(child)
        self.reader_actions_button = toga.Button('•••', style=Pack(width=44, height=44))
        self.reader_actions = FeatureCommands(self.reader_actions_button, self, [
            ('Contents and bookmarks…', self.show_reader_tools), ('Appearance…', self.show_reader_appearance),
            ('Reading mode', self.toggle_reading_mode), ('Fit comic page', self.fit_comic_page),
            ('Lock protected comic', self.lock_book), ('All documents', self.show_documents_hub)], self.show_reader_tools)
        self.reader_header = toga.Box(children=[
            toga.Button('Contents', on_press=self.show_reader_tools, style=Pack(height=44, flex=1)),
            toga.Button('Appearance', on_press=self.show_reader_appearance, style=Pack(height=44, flex=1)),
            self.reader_actions_button], style=Pack(direction=ROW))
        self.chapter_selector.style.flex = 1
        self.reader_footer = toga.Box(children=[self.previous_page, self.next_page], style=Pack(direction=ROW))
        self.reader_restore = toga.Button('Show reading controls', on_press=self.toggle_reading_mode, style=Pack(height=44))
        self.book_status.style.font_size = 12
        self.reader_immersive = False
        self.reading_frame = ReadingFrame(self.book_content, [self.reader_header, self.reader_footer, self.book_status])
        self.library_view = self.reading_frame.widget
        self.reader_tools_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
            toga.Label('Contents and bookmarks', style=Pack(font_size=20, margin_bottom=8)),
            self.chapter_selector, self.bookmark_button, self.bookmark_selector,
            self.book_lock,
            toga.Button('Return to reading', on_press=self.show_library, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))

    def show_reader_tools(self, widget=None, **kwargs):
        self.show_view(self.reader_tools_view, reader_route='tools', title='Contents and bookmarks')

    def toggle_reading_mode(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_busy:
            return
        self.set_reading_mode(not self.reader_immersive)

    def set_reading_mode(self, immersive, *, present=True):
        self.reader_immersive = immersive
        comic = self.book_record is not None and self.book_record['kind'] == 'comic'
        self.reading_frame.set_immersive(immersive, comic=comic)
        if self.reader_immersive:
            if not comic and self.reader_restore not in self.library_view.children:
                self.library_view.add(self.reader_restore)
        else:
            if self.reader_restore in self.library_view.children:
                self.library_view.remove(self.reader_restore)
        self.refresh_transfer_status()
        if present:
            self.show_library()
        else:
            sync_comic_chrome(self.app, self.app.body)

    def show_reader_appearance(self, widget=None, **kwargs):
        self.reader_font = toga.Selection(items=['12', '14', '16', '18', '20', '24', '28', '32'], value=self.preferences.values['font_size'], style=Pack(height=44))
        self.reader_margin = toga.Selection(items=['8', '16', '24', '32'], value=self.preferences.values['reading_margin'], style=Pack(height=44))
        self.reader_theme = toga.Selection(items=['system', 'light', 'dark'], value=self.preferences.values['reading_theme'], style=Pack(height=44))
        self.reader_appearance_status = toga.Label('Appearance changes keep your current chapter.')
        box = toga.Box(children=[toga.Label('Reading font size'), self.reader_font,
            toga.Label('Page margins'), self.reader_margin, toga.Label('Theme'), self.reader_theme,
            toga.Button('Apply and return', on_press=self.apply_reader_appearance, style=Pack(height=44)),
            self.reader_appearance_status], style=Pack(direction=COLUMN, margin=12))
        self.show_view(box, reader_route='appearance', title='Reading appearance')

    async def apply_reader_appearance(self, widget=None, **kwargs):
        try:
            self.preferences.save(font_size=self.reader_font.value, reading_margin=self.reader_margin.value,
                                  reading_theme=self.reader_theme.value)
            if self.book_reader is not None:
                await self.move_book_page(self.book_record['position'])
            self.show_library()
        except (OSError, ValueError) as error:
            self.reader_appearance_status.text = str(error)

    def fit_comic_page(self, widget=None, **kwargs):
        if self.book_content.children:
            view = self.book_content.children[0]
            if hasattr(view, 'fit_page'):
                view.fit_page()

    def swipe_book_page(self, direction):
        if self.book_reader is None:
            return
        schedule_swipe(self, direction, position=self.book_record['position'],
                       count=len(self.book_reader.pages), right_to_left=getattr(self.book_reader, 'right_to_left', False),
                       busy=self.book_busy, move=self.move_book_page)
