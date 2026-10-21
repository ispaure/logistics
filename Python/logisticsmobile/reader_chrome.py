"""Compact reading controls, native action menus and explicit appearance routes."""
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .action_menu import FeatureCommands
from .reader_controls import ReadingFrame, PageFooter, ComicHeader, comic_actions, comic_pages


def refresh_transfer_chrome(app):
    """Update live toolbar labels; rebuild native groups only on appearance/removal."""
    def update(view):
        if hasattr(view, '_native_reader_buttons'):
            transfer_control(app, view)
        for child in view.children:
            update(child)
    if not hasattr(app, 'routes'):
        return
    update(app.routes.body())
    visible = getattr(app, 'transfer_busy', False) or getattr(app, 'transfer_notification', False)
    if visible != getattr(app, '_transfer_chrome_visible', False):
        app._transfer_chrome_visible = visible
        app.adaptive.render()


def transfer_control(app, view):
    """A window-owned transfer shortcut, outside the document's reading area."""
    visible = (getattr(app, 'transfer_busy', False) or getattr(app, 'transfer_notification', False))
    visible = visible and not (getattr(view, '_reader_fullscreen', False)
                              or getattr(view, '_comic_fullscreen', False))
    if not visible:
        return None
    button = getattr(view, '_reader_transfer_button', None)
    if button is None:
        button = view._reader_transfer_button = toga.Button('', on_press=app.show_transfers,
            style=Pack(width=44, height=44, font_size=12))
    busy = getattr(app, 'transfer_busy', False)
    percentage = getattr(app, 'transfer_percentage', None)
    if busy:
        text = f'{percentage:.0f}%' if percentage is not None else '⇅'
        label = (f'Transfer: {percentage:.0f}% of known work. Open details' if percentage is not None
                 else 'Transfer in progress. Open details')
    else:
        complete = getattr(app, 'transfer_complete', False)
        text = '✓' if complete else '!'
        label = 'Transfer finished. Open details' if complete else 'Transfer stopped. Open details'
    if button.text != text:
        button.text = text
    from .appearance import accessible_name
    accessible_name(button, label)
    return button


def reader_buttons(app, view):
    buttons = list(view._native_reader_buttons())
    transfer = transfer_control(app, view)
    if transfer is not None:
        buttons.insert(0, transfer)
    return buttons


def sync_comic_chrome(app, view, *, destination=None):
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
    destination = destination or app.native_host.state.destination
    adapter = app.native_host.adapter
    navigation = None
    if app.adaptive.split is not None and destination == 'documents':
        navigation = app.adaptive.secondary
    elif adapter is not None and hasattr(adapter, 'navigation'):
        navigation = adapter.navigation[app.native_host.destinations.index(destination)]
    app.native_host.chrome.set_hidden(hidden, navigation=navigation)
    sync_document_tabs(app, view, fullscreen=hidden, destination=destination)
    from .ios_reader_chrome import sync
    sync(app)
    def page_swipes(widget):
        return (getattr(widget, 'page_swipes_at_edges', False) or hasattr(widget, '_reader_session_id')
                or any(page_swipes(child) for child in widget.children))
    app.native_host.chrome.set_page_swipes(page_swipes(view), navigation=navigation)


def sync_document_tabs(app, view, *, fullscreen=False, destination=None):
    """Document routes hide destinations without hiding their Back/title bar.

    Apply after immersive restoration, which can restore an older tab state.
    Keyboard snapshots must also use the current route's visibility so dismissing
    the keyboard cannot reveal destinations over an open document.
    """
    from .reader_lifecycle import session_route
    destination = destination or app.native_host.state.destination
    screens = app.routes.screens[destination]
    details = app.adaptive.detail_routes if destination == 'documents' else ()
    if (getattr(app.adaptive, 'split', None) is not None
            and not app.adaptive.in_detail):
        # UIKit retains the secondary reader when Back/All documents shows
        # the list, including on a collapsed iPhone split controller.
        details = ()

    def document(widget):
        return (hasattr(widget, '_reader_session_id')
                or any(document(child) for child in widget.children))

    hidden = fullscreen or document(view) or any(
        session_route(route) for route, *_ in (*screens, *details))
    app._document_tabs_hidden = hidden
    adapter = app.native_host.adapter
    if adapter is None:
        return
    if hasattr(adapter, 'navigation'):
        from rubicon.objc import SEL
        modern = bool(adapter.controller.respondsToSelector(SEL('setTabBarHidden:animated:')))
        keyboard = adapter.keyboard_tab_visibility
        if keyboard is not None:
            adapter.keyboard_tab_visibility = (modern, hidden)
        effective = hidden or keyboard is not None
        if adapter.tabs_hidden() != effective:
            adapter.set_keyboard_tabs_hidden(modern, effective)
    elif hasattr(adapter, 'bottom'):
        bar = adapter.impl.native_navigationview
        keyboard = adapter.keyboard_chrome
        visibility = 8 if hidden else 0
        if keyboard is not None:
            saved_bar, _, title, showing = keyboard
            adapter.keyboard_chrome = (saved_bar, visibility, title, showing)
        effective = 8 if keyboard is not None else visibility
        if bar.getVisibility() != effective:
            bar.setVisibility(effective)


class ReaderChrome:
    def refresh_folder_action(self):
        if not hasattr(self, 'reader_actions'):
            return
        self.reader_actions.refresh()

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
        from .document_sources import folder_action
        folder_actions = folder_action(self.app, self.session)
        self._folder_menu_available = bool(folder_actions)
        actions.extend(folder_actions)
        actions.append(('All documents', self.app.show_documents_hub))
        self.reader_actions = FeatureCommands(self.reader_actions_button, self, actions, self.show_reader_tools, document=True)
        from .workspace_navigation import menu_button
        if comic:
            self.comic_header = ComicHeader(self.reader_actions_button,
                previous=self.previous_comic_file, following=self.next_comic_file)
            self.reader_header = self.comic_header.widget
        else:
            browser = menu_button(self.show_reader_tools, label=tools_title)
            self.reader_speech_button = icon_button('speaker', 'Read aloud', on_press=self.show_read_aloud)
            self.reader_header = toga.Box(children=[browser,
                self.book_status,
                self.reader_speech_button,
                self.reader_actions_button], style=Pack(direction=ROW))
        self.chapter_selector.style.flex = 1
        self.page_footer = PageFooter(self.previous_page, self.next_page, self.move_book_page,
                                      status=self.book_status if comic else None, unit='page' if comic else 'chapter')
        self.reader_footer = self.page_footer.widget
        if not comic:
            self.book_status.style.update(flex=1, width=1, height=48, margin_top=0)
        self.reader_restore = toga.Button('Show reading controls', on_press=self.toggle_reading_mode, style=Pack(height=48))
        self.book_status.style.font_size = 12
        if comic:
            self.book_status.style.text_align = 'center'
        self.reader_immersive = False
        content = self.book_content
        if not comic:
            from commonUtils.ui.native.adaptive import AdaptiveSidebar
            self.chapter_rows = toga.Box(style=Pack(direction=COLUMN))
            tree = toga.Box(children=[toga.Label('Chapters', style=Pack(font_size=20)),
                self.chapter_rows, self.bookmark_button, self.bookmark_selector],
                style=Pack(direction=COLUMN, margin=8))
            from features.books.mobile.navigation import chapter_sidebar
            sidebar = chapter_sidebar(tree)
            self.chapter_sidebar = AdaptiveSidebar(sidebar, self.book_content, label='Browse book chapters')
            self.chapter_collapsed = set()
            content = self.chapter_sidebar.view
        self.reading_frame = ReadingFrame(content,
            [self.reader_header, self.reader_footer], margin=0, restore=self.reader_restore)
        self.library_view = self.reading_frame.widget
        self.library_view._native_reader_title = lambda: self.session.title
        self.library_view._native_reader_toolbar = self.reader_header
        self.library_view._native_reader_status = self.book_status
        if not comic:
            self.library_view._workspace_menu_button = browser
            self.library_view._native_reader_toolbar = self.reader_header
            self.library_view._native_reader_status = self.book_status
            self.library_view._native_reader_buttons = lambda: [self.reader_speech_button, self.reader_actions_button]
        else:
            self.library_view._native_reader_buttons = lambda: [
                *([self.comic_header.previous] if self.comic_header.available[0] else []),
                *([self.comic_header.following] if self.comic_header.available[1] else []), self.reader_actions_button]
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
        from .appearance import hierarchy_row_style
        self.chapter_tree = ChapterList(entries, activate, row_style=hierarchy_row_style,
                                       current=self.book_record['position'])
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
            from .font_scaling import refresh
            refresh(self)
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
        from .layout_events import notify_layout
        notify_layout(self.app)

    def swipe_book_page(self, direction):
        if self.book_reader is None:
            return
        from .reader_controls import schedule_swipe
        schedule_swipe(self, direction, right_to_left=self.book_reader.right_to_left,
                       busy=self.book_busy, move=self.move_comic)


    def show_read_aloud(self, widget=None, **kwargs):
        if self.book_reader is None or self.book_record['kind'] != 'epub' or self.book_busy:
            return
        panel = getattr(self, 'speech_panel', None)
        if panel is not None and not panel.closed:
            panel.toggle_over(self.book_content, anchor=getattr(self, 'reader_speech_button', None))
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
        self.speech_panel = ReadAloudPanel(loop=self.loop, source=source, on_range=follow, close=self.close_read_aloud,
            app=self.app, document_title=lambda: self.book_record['name'])
        self.speech_panel.show_over(self.book_content, anchor=getattr(self, 'reader_speech_button', None))

    def close_read_aloud(self, widget=None, **kwargs):
        panel = getattr(self, 'speech_panel', None)
        if panel is not None:
            panel.dispose()
            if panel in self.book_content.children:
                self.book_content.remove(panel)
            del self.speech_panel
