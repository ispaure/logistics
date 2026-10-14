"""Compact reading controls, native action menus and explicit appearance routes."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .action_menu import FeatureCommands


class ReaderChrome:
    def compact_reader(self):
        old = self.library_view
        for child in list(old.children):
            old.remove(child)
        self.reader_actions_button = toga.Button('Actions', style=Pack(height=44))
        self.reader_actions = FeatureCommands(self.reader_actions_button, self, [
            ('Contents and bookmarks…', self.show_reader_tools), ('Appearance…', self.show_reader_appearance),
            ('Reading mode', self.toggle_reading_mode), ('Fit comic page', self.fit_comic_page),
            ('Lock protected comic', self.lock_book), ('All documents', self.show_documents_hub)], self.show_reader_tools)
        self.reader_header = toga.Box(children=[self.chapter_selector, self.reader_actions_button], style=Pack(direction=ROW))
        self.chapter_selector.style.flex = 1
        self.reader_footer = toga.Box(children=[self.previous_page, self.next_page], style=Pack(direction=ROW))
        self.reader_restore = toga.Button('Show reading controls', on_press=self.toggle_reading_mode, style=Pack(height=44))
        self.reader_immersive = False
        self.library_view = toga.Box(children=[self.reader_header, self.book_content, self.reader_footer, self.book_status],
                                     style=Pack(direction=COLUMN, margin=8, flex=1))
        self.reader_tools_view = toga.ScrollContainer(content=toga.Box(children=[
            toga.Label('Contents and bookmarks'), self.bookmark_button, self.bookmark_selector,
            self.book_lock, self.book_selector, self.book_import, self.book_open,
            toga.Button('Return to reading', on_press=self.show_library, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))

    def show_reader_tools(self, widget=None, **kwargs):
        self.show_view(self.reader_tools_view)

    def toggle_reading_mode(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_busy:
            return
        self.reader_immersive = not self.reader_immersive
        if self.reader_immersive:
            for child in (self.reader_header, self.reader_footer, self.book_status):
                self.library_view.remove(child)
            self.library_view.add(self.reader_restore)
        else:
            self.library_view.remove(self.reader_restore)
            self.library_view.insert(0, self.reader_header)
            self.library_view.add(self.reader_footer)
            self.library_view.add(self.book_status)
        self.show_library()

    def show_reader_appearance(self, widget=None, **kwargs):
        self.reader_font = toga.Selection(items=['12', '14', '16', '18', '20', '24', '28', '32'], value=self.preferences.values['font_size'], style=Pack(height=44))
        self.reader_margin = toga.Selection(items=['8', '16', '24', '32'], value=self.preferences.values['reading_margin'], style=Pack(height=44))
        self.reader_theme = toga.Selection(items=['system', 'light', 'dark'], value=self.preferences.values['reading_theme'], style=Pack(height=44))
        self.reader_appearance_status = toga.Label('Appearance changes keep your current chapter.')
        box = toga.Box(children=[toga.Label('Reading font size'), self.reader_font,
            toga.Label('Page margins'), self.reader_margin, toga.Label('Theme'), self.reader_theme,
            toga.Button('Apply and return', on_press=self.apply_reader_appearance, style=Pack(height=44)),
            self.reader_appearance_status], style=Pack(direction=COLUMN, margin=12))
        self.show_view(box)

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
        if self.book_busy or self.book_reader is None or not self.active_host:
            return
        if getattr(self.book_reader, 'right_to_left', False):
            direction = -direction
        self.loop.create_task(self.move_book_page(self.book_record['position'] + direction))
