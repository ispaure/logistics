"""Compact reading controls, native action menus and explicit appearance routes."""
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .action_menu import FeatureCommands
from .reader_controls import ReadingFrame, PageFooter


def sync_comic_chrome(app, view):
    """Host decides when to hide chrome; shared adapters own native restoration."""
    def immersive(widget):
        return (getattr(widget, '_reader_fullscreen', False)
                or getattr(widget, '_comic_fullscreen', False)
                or any(immersive(child) for child in widget.children))
    hidden = immersive(view)
    def comic(widget):
        return getattr(widget, '_comic_fullscreen', False) or any(comic(child) for child in widget.children)
    app._comic_chrome_hidden = comic(view)
    app._reader_chrome_hidden = hidden
    navigation = app.adaptive.secondary if app.adaptive.split is not None and app.native_host.state.destination == 'documents' else None
    app.native_host.chrome.set_hidden(hidden, navigation=navigation)
    from .ios_reader_chrome import sync
    sync(app)
    def page_swipes(widget):
        return getattr(widget, 'page_swipes_at_edges', False) or any(page_swipes(child) for child in widget.children)
    app.native_host.chrome.set_page_swipes(page_swipes(view), navigation=navigation)


class ReaderChrome:
    def compact_reader(self):
        old = self.library_view
        for child in list(old.children):
            old.remove(child)
        self.reader_actions_button = icon_button('more', 'Reader actions')
        self.reader_actions = FeatureCommands(self.reader_actions_button, self, [
            ('Read aloud…', self.show_read_aloud), ('Edit metadata…', self.show_book_metadata), ('Find in chapter…', self.show_epub_search), ('Contents and bookmarks…', self.show_reader_tools), ('Appearance…', self.show_reader_appearance),
            ('Reading mode', self.toggle_reading_mode), ('Fit comic page', self.fit_comic_page),
            ('First comic page', self.first_comic_page), ('Last comic page', self.last_comic_page),
            ('Previous comic', self.previous_comic_file), ('Next comic', self.next_comic_file),
            ('Lock protected comic', self.lock_book), ('All documents', self.show_documents_hub)], self.show_reader_tools)
        from .workspace_navigation import menu_button
        self.reader_header = toga.Box(children=[
            menu_button(lambda widget, **kw: self.app.adaptive.show_browser(self.presentation_destination)),
            icon_button('contents', 'Contents and bookmarks', on_press=self.show_reader_tools),
            icon_button('appearance', 'Reading appearance', on_press=self.show_reader_appearance),
            self.reader_actions_button], style=Pack(direction=ROW))
        self.chapter_selector.style.flex = 1
        self.page_footer = PageFooter(self.previous_page, self.next_page, self.move_book_page)
        self.reader_footer = self.page_footer.widget
        self.reader_restore = toga.Button('Show reading controls', on_press=self.toggle_reading_mode, style=Pack(height=48))
        self.book_status.style.font_size = 12
        self.reader_immersive = False
        self.reading_frame = ReadingFrame(self.book_content, [self.reader_header, self.reader_footer, self.book_status])
        self.library_view = self.reading_frame.widget
        self.library_view._workspace_menu_button = self.reader_header.children[0]
        self.reader_tools_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
            toga.Label('Contents and bookmarks', style=Pack(font_size=20, margin_bottom=8)),
            self.chapter_selector, self.bookmark_button, self.bookmark_selector,
            self.book_lock,
            toga.Button('Return to reading', on_press=self.show_library, style=Pack(height=48))],
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
        from features.books.mobile.appearance import ReaderAppearance
        box = ReaderAppearance(self.preferences.values, self.apply_reader_appearance)
        self.reader_appearance = box
        self.reader_font, self.reader_margin = box.font_choice, box.margin_choice
        self.reader_theme, self.reader_layout = box.theme_choice, box.layout_choice
        self.reader_appearance_status = box.status
        self.show_view(box, reader_route='appearance', title='Reading appearance')

    async def apply_reader_appearance(self, widget=None, **kwargs):
        try:
            self.preferences.save(font_size=self.reader_font.value, reading_margin=self.reader_margin.value,
                                  reading_theme=self.reader_theme.value, comic_layout=self.reader_layout.value, **self.reader_appearance.typography())
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
        if self.book_busy or not self.active_host:
            return
        task = getattr(self, '_comic_swipe_task', None)
        if task is None or task.done():
            amount = -direction if self.book_reader.right_to_left else direction
            self._comic_swipe_task = self.loop.create_task(self.move_comic(amount))


    def show_read_aloud(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_record['kind'] != 'epub' or self.book_busy:
            return
        self.close_read_aloud()
        from features.books.mobile.speech_view import ReadAloudPanel
        from features.books.mobile.presentation import speech_source
        async def source():
            return await speech_source(self.epub_view, self.epub_text, self.epub_offset)
        def follow(start, end):
            self.epub_offset = start
            self.epub_view._chapter_bridge.seek(start, end)
            self.epub_event(self.book_reader, self.book_epoch, self.book_record['position'], 'position', start)
        self.speech_panel = ReadAloudPanel(loop=self.loop, source=source, on_range=follow, close=self.close_read_aloud)
        self.book_content.insert(0, self.speech_panel)

    def close_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, 'speech_panel', None)
        if panel is not None:
            panel.dispose()
            if panel in self.book_content.children:
                self.book_content.remove(panel)
            del self.speech_panel
