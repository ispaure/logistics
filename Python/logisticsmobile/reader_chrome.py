"""Compact reading controls, native action menus and explicit appearance routes."""
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .action_menu import FeatureCommands
from .reader_controls import ReadingFrame, PageFooter, ComicHeader, comic_actions, comic_pages


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
        comic = self.session.kind == 'comic'
        tools_title = 'Comic pages' if comic else 'Contents and bookmarks'
        if comic:
            actions = comic_actions(pages=self.show_reader_tools, appearance=self.show_reader_appearance,
                reading_mode=self.toggle_reading_mode, fit=self.fit_comic_page,
                metadata=self.show_book_metadata, info=self.show_comic_info,
                close=lambda: self.app.request_close_session(self.session.id))
        else:
            actions = [('Edit metadata…', self.show_book_metadata),
                ('Chapters and bookmarks…', self.show_reader_tools), ('Appearance…', self.show_reader_appearance),
                ('Fullscreen', self.toggle_reading_mode), ('Read aloud…', self.show_read_aloud),
                ('Find in chapter…', self.show_epub_search),
                ('Open beside another document', self.app.adaptive.show_pair_picker)]
        self.reader_actions = FeatureCommands(self.reader_actions_button, self, actions, self.show_reader_tools)
        from .workspace_navigation import menu_button
        browser = (menu_button(lambda widget, **kw: self.app.adaptive.show_browser(self.presentation_destination))
                   if comic else menu_button(self.show_reader_tools, label=tools_title))
        if comic:
            self.comic_header = ComicHeader(browser, self.reader_actions_button,
                previous=self.previous_comic_file, following=self.next_comic_file)
            self.reader_header = self.comic_header.widget
        else:
            self.reader_speech_button = icon_button('speaker', 'Read aloud', on_press=self.show_read_aloud)
            self.reader_header = toga.Box(children=[browser,
                self.book_status,
                self.reader_speech_button,
                self.reader_actions_button], style=Pack(direction=ROW))
        self.chapter_selector.style.flex = 1
        self.page_footer = PageFooter(self.previous_page, self.next_page, self.move_book_page, compact=not comic)
        self.reader_footer = self.page_footer.widget
        if not comic:
            self.reader_header.insert(1, self.reader_footer)
            self.book_status.style.update(flex=1, width=1, height=48, margin_top=0)
        self.reader_restore = toga.Button('Show reading controls', on_press=self.toggle_reading_mode, style=Pack(height=48))
        self.book_status.style.font_size = 12
        self.reader_immersive = False
        content = self.book_content
        if not comic:
            from commonUtils.ui.native.adaptive import AdaptiveSidebar
            self.chapter_rows = toga.Box(style=Pack(direction=COLUMN))
            tree = toga.Box(children=[toga.Label('Chapters', style=Pack(font_size=20)),
                toga.ScrollContainer(content=self.chapter_rows, horizontal=False, style=Pack(flex=1)),
                self.bookmark_button, self.bookmark_selector], style=Pack(direction=COLUMN, flex=1, margin=8))
            self.chapter_sidebar = AdaptiveSidebar(tree, self.book_content, label='Browse book chapters')
            self.chapter_collapsed = set()
            content = self.chapter_sidebar.view
        self.reading_frame = ReadingFrame(content,
            [self.reader_header, self.reader_footer, self.book_status] if comic else [self.reader_header],
            margin=16 if comic else 0, restore=self.reader_restore)
        self.library_view = self.reading_frame.widget
        self.library_view._workspace_menu_button = self.reader_header.children[0]
        if not comic:
            self.library_view._native_reader_toolbar = self.reader_header
            self.library_view._native_reader_status = self.book_status
            self.library_view._native_reader_buttons = lambda: [self.previous_page, self.next_page,
                self.reader_speech_button, self.reader_actions_button]
        if comic:
            self.reader_tools_view = comic_pages(self.chapter_selector, self.show_library)
        else:
            self.reader_tools_view = tree

    def reflow_chapters(self):
        sidebar = getattr(self, 'chapter_sidebar', None)
        if sidebar is not None:
            width = 0 if self.reader_immersive else self.app.adaptive.content_width(self.presentation_destination, margin=0)
            sidebar.reflow(width)

    def render_chapters(self):
        if not hasattr(self, 'chapter_sidebar'):
            return
        from features.books.mobile.navigation import ChapterList
        from types import SimpleNamespace
        entries = list(self.contents_choices.values()) or [
            SimpleNamespace(label=label, depth=0, index=index, fragment='')
            for index, label in enumerate(self.chapter_labels)]
        async def choose(entry):
            self._epub_target = entry.fragment
            self.chapter_sidebar.show_detail()
            await self.open_reader_destination(entry.index)
        def activate(entry):
            return self.loop.create_task(choose(entry))
        self.chapter_tree = ChapterList(entries, activate)
        self.chapter_rows.clear()
        self.chapter_rows.add(self.chapter_tree.rows)
        self.reflow_chapters()

    def show_reader_tools(self, widget=None, **kwargs):
        if self.session.kind == 'comic':
            self.show_view(self.reader_tools_view, reader_route='tools', title='Comic pages')
        else:
            if self.reader_immersive:
                self.set_reading_mode(False, present=False)
            self.reflow_chapters()
            self.chapter_sidebar.toggle()
            self.show_library()

    async def show_comic_info(self, widget=None, **kwargs):
        if self.book_reader is None or self.session.kind != 'comic':
            return
        path = self.library_store.path(self.session.resource, '.cbz')
        await self.main_window.dialog(toga.InfoDialog('Comic path', str(path)))

    def toggle_reading_mode(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_busy:
            return
        self.set_reading_mode(not self.reader_immersive)

    def set_reading_mode(self, immersive, *, present=True):
        self.reader_immersive = immersive
        comic = self.session.kind == 'comic'
        self.reading_frame.set_immersive(immersive, comic=comic)
        if not comic:
            self.reflow_chapters()
            self.chapter_sidebar.show_detail()
        self.refresh_transfer_status()
        if present:
            self.show_library()
        else:
            sync_comic_chrome(self.app, self.app.body)

    def show_reader_appearance(self, widget=None, **kwargs):
        from features.books.mobile.appearance import ReaderAppearance
        box = ReaderAppearance(self.preferences.values, self.apply_reader_appearance, kind=self.session.kind)
        self.reader_appearance = box
        if self.session.kind == 'epub':
            self.reader_font, self.reader_margin = box.font_choice, box.margin_choice
            self.reader_theme = box.theme_choice
        else:
            self.reader_layout = box.layout_choice
        self.reader_appearance_status = box.status
        self.show_view(box, reader_route='appearance', title='Reading appearance')

    async def apply_reader_appearance(self, widget=None, **kwargs):
        try:
            self.preferences.save(**self.reader_appearance.settings())
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
        from .reader_controls import schedule_swipe
        schedule_swipe(self, direction, right_to_left=self.book_reader.right_to_left,
                       busy=self.book_busy, move=self.move_comic)


    def show_read_aloud(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_record['kind'] != 'epub' or self.book_busy:
            return
        self.close_read_aloud()
        from features.books.mobile.speech_view import ReadAloudPanel
        from features.books.mobile.presentation import speech_source
        async def source():
            return await speech_source(self.epub_view, self.epub_text, self.epub_offset)
        def follow(start, end):
            if not self.app.screen_privacy.inactive:
                self.epub_view._chapter_bridge.highlight(start, end)
            if start < 0:
                return
            self.epub_offset = start
            self.epub_event(self.book_reader, self.book_epoch, self.book_record['position'], 'position', start)
        self.speech_panel = ReadAloudPanel(loop=self.loop, source=source, on_range=follow, close=self.close_read_aloud, app=self.app)
        self.speech_panel.show_over(self.book_content)

    def close_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, 'speech_panel', None)
        if panel is not None:
            panel.dispose()
            if panel in self.book_content.children:
                self.book_content.remove(panel)
            del self.speech_panel
