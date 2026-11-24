"""Documents tabs, local search results and library launchers."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
from threading import Event

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .appearance import accessible_name, batch_surfaces, list_button, selection_row, surface
from .control_icons import icon_button, button_icons
from .hub_controls import (
    DocumentCardMedia, PanelGrid, append_document_group_rows, document_group, document_list,
    empty_document_row, library_discovery_heading, retire_document_actions, source_title, text_document_kind,
)
from .recent_documents import MAX_RECENT
from .ui_metrics import TOUCH_TARGET, WRAPPED_FILENAME_ROW_HEIGHT


COLLECTIONS = ('Libraries', 'Favourites', 'Recent')
TABS_BREAKPOINT = 300
COLLECTION_SPLIT_WIDTH = 720
COLLECTION_FONT = 13
FILENAME_FONT = 15


def library_heading_style(*, font_size=19):
    return Pack(font_size=font_size, font_weight='bold', margin_top=8, margin_bottom=8)


def library_folder_button(record, on_press):
    from .browser_ui import middle_filename

    button = toga.Button(record['name'], on_press=on_press,
        style=Pack(height=TOUCH_TARGET, font_size=FILENAME_FONT, font_weight='bold'))
    # These rows switch between a transparent surface and a selection fill.
    button._impl._content_inset = 8
    list_button(button)
    middle_filename(button)
    return button


def library_folder_row(button, record, *, category=None):
    source = record['source']
    folder = record['location'][1] if 'location' in record else record['folder']
    row = button
    if source.endswith(' - Encrypted Copy'):
        row = source_title(button, [('storage_unlocked', source)], text='Encrypted library')
    row._document_library_key = (category, source, folder)
    return row


class DocumentsHub:
    """Presentation methods share the HubController state and service contract."""
    def visible_library_drawer(self):
        routes = self.app.routes
        body = routes.body('documents')
        page = next(iter(body.children), None)
        return getattr(page, '_document_library_drawer', None)

    def reflow_documents_hub(self):
        from commonUtils.ui.native.forms import fit_text
        from .fold_layout import division
        from .pane_layout import panes

        if self.main_window is None:
            return
        body = self._document_collection_body
        width = self.adaptive.content_width('documents', margin=32)
        viewport = self.main_window.size
        drawer = self.visible_library_drawer()
        fold = division(self.app, drawer.page if drawer is not None else body)
        searching = self.document_search.parent is self.app._documents_status_row
        split = fold.vertical if fold is not None else width >= COLLECTION_SPLIT_WIDTH
        allocation = panes(width, viewport.height, fold=fold, leading_fraction=.43)
        selector_width = allocation.leading if split else width
        gap = allocation.gap if split or fold is not None else 0
        result_width = width - selector_width - gap if split else width
        wrapped = selector_width < TABS_BREAKPOINT
        fit_text(self.documents_sections._document_unlock_hint, selector_width)

        nav = self._document_collection_navigation
        nav_host = drawer.library_sidebar if drawer is not None and split else body
        if nav.parent is not nav_host:
            nav.parent.remove(nav)
            if nav_host is body:
                body.insert(0, nav)
            else:
                nav_host.add(nav)
        if drawer is not None:
            drawer.layout_library(nav, selector_width, gap, split=split)
        self.mark_document_library(drawer.library_key if drawer is not None and split else None)
        self.documents_sections._bottom_scrolls = (self._document_results_scroll,)
        if split and nav_host is body:
            self.documents_sections._bottom_scrolls += (nav,)

        geometry = (split, wrapped, searching, selector_width, fold, gap, nav_host is body)
        if geometry != self._document_collection_geometry:
            self._document_collection_geometry = geometry
            body.style.direction = ROW if split else COLUMN
            detail = self._document_collection_detail
            nav.style.flex = 0 if nav_host is body else 1
            if split:
                del nav.style.height
                if nav_host is body:
                    nav.style.width = selector_width
                else:
                    del nav.style.width
            else:
                del nav.style.width
                # Both panes scroll independently when a horizontal fold fixes
                # the space above the crease, including in a short window.
                nav.style.height = (fold.y if fold is not None else
                    0 if searching else (TOUCH_TARGET + 4) * (2 if wrapped else 1))
            detail.style.margin_left = gap if split and nav_host is body else 0
            detail.style.margin_top = gap if not split else 0
            self._layout_document_tabs(wrapped)
        use_companion = split and not searching
        target = self._document_collection_header if use_companion else self._document_results_pane
        if self.document_results.parent is not target:
            self.document_results.parent.remove(self.document_results)
            target.add(self.document_results)
        # Mount only the active viewport. Retaining two flex children, even
        # with one excluded from display, can halve the native browser's height.
        detail = self._document_collection_detail
        active = self._document_companion if use_companion else self._document_results_scroll
        inactive = self._document_results_scroll if use_companion else self._document_companion
        if inactive.parent is detail:
            detail.remove(inactive)
        if active.parent is not detail:
            detail.add(active)

        # Pack's display flag only changes allocation. Hide the native view too:
        # otherwise a pane retains its last frame and can cover the library list
        # after rotating or opening search on the Duo.
        self._document_results_scroll.style.update(
            display='none' if use_companion else 'pack',
            visibility='hidden' if use_companion else 'visible')
        self._document_companion.style.update(
            display='pack' if use_companion else 'none',
            visibility='visible' if use_companion else 'hidden')

        # Fit status and source text to the allocated pane, including after a
        # fold or search transition, without letting it expand the viewport.
        def fit(widget):
            if isinstance(widget, toga.Label):
                fit_text(widget, max(1, int(selector_width if use_companion else result_width) - 32))
            for child in widget.children:
                fit(child)
        fit(self.document_results)

    def mark_document_library(self, key):
        def visit(row):
            if hasattr(row, '_document_library_key'):
                selected = row._document_library_key == key
                if selected != getattr(row, '_document_library_selected', False):
                    selection_row(row, selected)
                    row._document_library_selected = selected
                return
            for child in row.children:
                visit(child)

        visit(self.document_libraries_list)

    def _layout_document_tabs(self, wrapped):
        mode = 'wrapped' if wrapped else 'tabs'
        if mode == self._document_tabs_mode:
            return
        self._document_tabs_mode = mode
        for button in self.document_view_buttons.values():
            if button.parent is not None:
                button.parent.remove(button)
        self.document_views.clear()
        names = (COLLECTIONS[:2], COLLECTIONS[2:]) if wrapped else (COLLECTIONS,)
        for group in names:
            row = toga.Box(style=Pack(direction=ROW))
            for name in group:
                row.add(self.document_view_buttons[name])
            self.document_views.add(row)
        self._style_document_tabs()

    def _style_document_tabs(self):
        from .folder_hub_style import source_tab
        with batch_surfaces():
            for name, button in self.document_view_buttons.items():
                selected = self.documents_view == name
                source_tab(button, selected, quiet=True)

    def build_documents_hub(self):
        from commonUtils.ui.native.event_loop import DebouncedCallback
        previous_search = getattr(self, '_document_search_route', None)
        if previous_search is not None and previous_search.active:
            previous_search.close()
        previous = getattr(self, '_document_search_delay', None)
        if previous is not None:
            previous.cancel()
        search = getattr(self, '_documents_file_search', None)
        if search is not None:
            search.stop_local_search()
        from .notes_discovery import cancel
        cancel(self.app)
        for name in ('_document_books_discovery', '_document_comics_discovery'):
            task = getattr(self, name, None)
            if task is not None:
                task.cancel()
        self._document_search_delay = DebouncedCallback(self.refresh_document_list)
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 0, 16), flex=1))
        box._documents_overview = True
        self.document_search = toga.TextInput(placeholder='Search local documents',
            value=getattr(self, 'documents_query', ''), on_change=self.search_documents,
            style=Pack(height=48, flex=1))
        self.app._documents_status_row = toga.Box(children=[],
            style=Pack(direction=ROW, align_items=CENTER))
        self.document_grids = []
        self.document_categories = {}
        self.document_launchers = PanelGrid([], self.main_window.size.width)
        if hasattr(self, 'document_recent_list'):
            for section in (self.document_recent_list, self.document_saved_list,
                            self.document_favourites_list):
                retire_document_actions(section)
        self.document_recent_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_recent_list._open_documents = True
        self.document_saved_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_notes_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_comics_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_books_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_favourites_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_libraries_list = toga.Box(
            children=[self.document_notes_list, self.document_books_list, self.document_comics_list,
                      self.document_saved_list],
            style=Pack(direction=COLUMN))
        self._document_libraries_ready = False
        for menu in getattr(self, '_document_search_menus', ()):
            menu.dispose()
        self._document_search_menus = []
        self.document_search_results = toga.Box(style=Pack(direction=COLUMN))
        self.document_results = toga.Box(style=Pack(direction=COLUMN))
        self.document_views = toga.Box(style=Pack(direction=COLUMN))
        self.document_view_buttons = {}
        self._document_tabs_mode = None
        self._document_collection_geometry = None
        if getattr(self, 'documents_view', None) == 'Open':
            self.documents_view = 'Recent'
        if getattr(self, 'documents_view', None) not in COLLECTIONS:
            self.documents_view = 'Libraries'
        for name in COLLECTIONS:
            def choose(widget=None, name=name, **kwargs):
                if self.documents_view != name:
                    drawer = self.visible_library_drawer()
                    if drawer is not None and not drawer.cancel_browser():
                        return
                    from .haptics import feedback
                    feedback(widget)
                self.documents_view = name
                self.document_library = None
                self.show_document_collection()
            button = toga.Button(name, on_press=choose,
                style=Pack(height=TOUCH_TARGET, flex=1, margin=2, font_size=COLLECTION_FONT))
            accessible_name(button, name)
            self.document_view_buttons[name] = button

        self._document_collection_header = toga.Box(children=[self.document_views],
                                                    style=Pack(direction=COLUMN))
        self._document_collection_navigation = toga.ScrollContainer(horizontal=False,
            content=self._document_collection_header)
        box._duo_heading_pane = self._document_collection_navigation
        results = toga.Box(children=[self.document_results],
                           style=Pack(direction=COLUMN, margin=(8, 0, 16, 0)))
        self._document_results_pane = results
        self._document_results_scroll = toga.ScrollContainer(horizontal=False, content=results, style=Pack(flex=1))
        self._document_companion = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self._document_collection_detail = toga.Box(children=[self.app._documents_status_row,
            self._document_results_scroll, self._document_companion],
            style=Pack(direction=COLUMN, flex=1))
        self._document_collection_body = toga.Box(
            children=[self._document_collection_navigation, self._document_collection_detail],
            style=Pack(direction=COLUMN, flex=1))
        from commonUtils.ui.native.forms import FittedLabel
        box._document_unlock_hint = FittedLabel('Unlock encrypted copies to include their libraries.',
            style=Pack(font_size=12, margin_bottom=8, display='none', visibility='hidden'))
        box.add(box._document_unlock_hint, self._document_collection_body)
        from .scroll_edges import fill_bottom
        fill_bottom(box, self._document_results_scroll)
        from .document_search import DocumentSearch
        from commonUtils.ui.native.presentation import allow_label_to_shrink
        self._documents_search_location = empty_document_row('')
        self._documents_search_location.style.margin_bottom = 2
        allow_label_to_shrink(self._documents_search_location)
        self._documents_search_status = empty_document_row('Searching local filenames…')
        allow_label_to_shrink(self._documents_search_status)
        self._documents_search_header = toga.Box(
            children=[self._documents_search_location, self._documents_search_status],
            style=Pack(direction=COLUMN))
        self._documents_file_search = DocumentSearch(
            self.app, self.publish_document_search, self.show_document_search_progress)
        self.documents_sections = box
        self.refresh_document_list()
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.register_transfer_status(box)
        return box

    def show_document_collection(self):
        if not hasattr(self, 'document_results'):
            return
        # Search owns a separate retained route; collection panes stay intact.
        searching = False
        library = getattr(self, 'document_library', None)
        for name, section in (('Notes', self.document_notes_list), ('Books', self.document_books_list),
                              ('Comics', self.document_comics_list), (None, self.document_saved_list)):
            visible = library is None or library == name
            section.style.update(display='pack' if visible else 'none',
                                 visibility='visible' if visible else 'hidden')
        self._style_document_tabs()
        selected = self.document_search_results if searching else {
            'Recent': self.document_recent_list,
            'Libraries': self.document_libraries_list,
            'Favourites': self.document_favourites_list}[self.documents_view]
        if list(self.document_results.children) != [selected]:
            self.document_results.clear()
            self.document_results.add(selected)
        discover = not getattr(self.app, '_startup_in_progress', False)
        if discover and not searching and self.documents_view == 'Libraries' and not self._document_libraries_ready:
            self.populate_document_libraries()
        if discover and not searching and self.documents_view == 'Favourites':
            from .favourites import populate
            retire_document_actions(self.document_favourites_list)
            self.document_favourites_list.clear()
            populate(self.app, self.document_favourites_list, heading=False, row_font=FILENAME_FONT,
                     allow_remove=True)
        previews = getattr(selected, '_document_card_media', None)
        if previews is not None:
            previews.start()
        self.reflow_documents_hub()

    async def browse_document_library(self, storage, *, provider, folder, title, category=None):
        drawer = self.adaptive.browser('documents')
        return await drawer.show_main_browser(storage, folder=folder, title=title, provider=provider,
                                              library_key=(category, storage, folder))

    def populate_document_libraries(self):
        self._document_libraries_ready = True
        from .notes_discovery import populate
        populate(self.app, self.document_notes_list, title='Notes', refresh=False,
                 title_style=library_heading_style(), row_font=FILENAME_FONT)
        self.populate_book_libraries()
        self.document_comics_list.clear()
        if not self.app.feature_enabled('comics'):
            self.document_comics_list.add(toga.Label('Comics', style=library_heading_style()),
                                          empty_document_row('Comics is disabled.'))
            return
        catalog = self.app.reader_manager().catalog
        target = self.document_comics_list
        finish = library_discovery_heading(target, 'Comics', library_heading_style())
        async def discover():
            await catalog.refresh_library_folders()
            if target is not self.document_comics_list or not self.app.active_host:
                return
            finish()
            rows = []
            for record in catalog.library_records:
                if not self.app.library_folder_visible(record):
                    continue
                async def open_library(widget=None, record=record, **kwargs):
                    if self.app.checkpoint():
                        await catalog.library_host.open_folder(record, destination='documents')
                rows.append(library_folder_row(library_folder_button(record, open_library), record, category='Comics'))
            target.add(document_list(rows, 'No Comics libraries found.', outlined=True))
            if 'could not' in catalog.book_status.text:
                target.add(empty_document_row(catalog.book_status.text))
            self.reflow_documents_hub()
        old = getattr(self, '_document_comics_discovery', None)
        if old is not None:
            old.cancel()
        self._document_comics_discovery = self.app.loop.create_task(discover())

    def populate_book_libraries(self):
        from commonUtils.runtime.operations import OperationCancelled
        from .library_ui import discover_book_libraries

        app, target = self.app, self.document_books_list
        old = getattr(self, '_document_books_discovery', None)
        if old is not None:
            old.cancel()
        target.clear()
        if not app.feature_enabled('books'):
            target.add(toga.Label('Books', style=library_heading_style()),
                       empty_document_row('Books is disabled.'))
            return
        finish = library_discovery_heading(target, 'Books', library_heading_style())
        cancel = Event()

        async def discover():
            try:
                records, failures = await asyncio.to_thread(discover_book_libraries, app, cancelled=cancel.is_set)
            except (asyncio.CancelledError, OperationCancelled):
                cancel.set()
                return
            except (OSError, ValueError):
                records, failures = [], 1
            if target is not self.document_books_list or not app.active_host or not app.feature_enabled('books'):
                return
            rows = []
            for record in records:
                location = record['location']
                if not app.folder_path_visible(location[1]):
                    continue

                async def open_library(widget=None, record=record, location=location, **kwargs):
                    if (target is self.document_books_list and app.feature_enabled('books')
                            and app.checkpoint()):
                        label, folder = location
                        try:
                            provider = app.storage_provider(label, app.ordinary_file_roots(include_collections=False))
                        except (OSError, ValueError) as error:
                            await app.main_window.dialog(toga.InfoDialog('Could not open library', str(error)))
                            return False
                        return await self.browse_document_library(record['source'], folder=folder,
                            title=record['name'], provider=provider, category='Books')

                button = library_folder_button(record, open_library)
                source = record['source']
                accessible_name(button, f'{source} / {location[1]}' if location[1] else source)
                rows.append(library_folder_row(button, record, category='Books'))
            finish()
            target.add(document_list(rows, 'No Books libraries found.', outlined=True))
            if failures:
                target.add(empty_document_row('Some local folders could not be checked.'))
            self.reflow_documents_hub()

        self._document_books_discovery = app.loop.create_task(discover())

    def clear_document_search_results(self):
        for menu in getattr(self, '_document_search_menus', ()):
            menu.dispose()
        self._document_search_menus = []
        self._document_search_published = 0
        self._document_search_group = None
        self.document_search_results.clear()

    def show_document_search_progress(self, checked=0, cache_phase='', hits=(), location=''):
        from .local_search import filename_scan_label

        status = self._documents_search_status
        caption = self._documents_search_location
        caption.style.update(display='pack' if location else 'none', visibility='visible')
        if caption.text != location:
            caption.text = location
        message = (f'{filename_scan_label(cache_phase)} · {checked:,} checked'
                   if location else 'Searching local filenames…')
        if status.text != message:
            status.text = message
        if self._documents_search_header.parent is None:
            self.document_search_results.insert(0, self._documents_search_header)
        if len(hits) > getattr(self, '_document_search_published', 0):
            self.publish_document_search(hits, (), finished=False)

    def publish_document_search(self, hits, failures, *, finished=True, checked_localcrypt_cache=False):
        from .browser_ui import entry_icon, wrapped_filename

        target = self.document_search_results
        published = getattr(self, '_document_search_published', 0)
        rows = []
        for hit in hits[published:]:
            async def open_result(widget=None, source=hit['source'], hit=hit, **kwargs):
                if not self.app.checkpoint():
                    return
                if hit.get('directory'):
                    from .search_panels import visit_document_folder
                    return await visit_document_folder(self.app, hit)
                if source['type'] == 'managed':
                    return self.app.stored_document_opener(source['resource'])()
                if source['type'] == 'notebook':
                    from features.notebooks.mobile.documents import open_notebook
                    return await open_notebook(self.app, key=source['resource'])
                from .document_search import open_search_file
                try:
                    await open_search_file(self.app, hit)
                except (OSError, ValueError) as error:
                    await self.main_window.dialog(toga.InfoDialog('Could not open file', str(error)))
            button = list_button(toga.Button(hit['name'], on_press=open_result,
                style=Pack(height=WRAPPED_FILENAME_ROW_HEIGHT, flex=1, font_size=FILENAME_FONT)))
            wrapped_filename(button)
            row = toga.Box(children=[entry_icon(hit.get('directory', False)), button],
                           style=Pack(direction=ROW, align_items=CENTER))
            rows.append(row)
        if rows:
            group = getattr(self, '_document_search_group', None)
            if group is None:
                group = self._document_search_group = document_group(())
                target.add(group)
            append_document_group_rows(group, rows, compact=True)
            self._document_search_published = len(hits)
        if finished:
            count = max(published, len(hits))
            if self._documents_search_header.parent is target:
                # Reserve the location line through completion to keep live
                # results under the same touch targets.
                self._documents_search_location.style.visibility = 'hidden'
                cache_status = ' · LocalCrypt cache checked' if checked_localcrypt_cache else ''
                self._documents_search_status.text = f'{count:,} matches{cache_status}'
            if not count:
                target.add(empty_document_row('No matching local documents.'))
        if failures:
            target.add(empty_document_row('Some local locations could not be searched.'))
        self.reflow_documents_hub()

    def open_document_search(self, widget=None, *, scope=None, destination='documents', **kwargs):
        from .search_panels import SearchRoute
        if not hasattr(self, 'document_search'):
            self.build_documents_hub()
        panel = getattr(self, '_document_search_route', None)
        if panel is not None and panel.active:
            if panel.destination == destination and self._documents_file_search.scope == scope:
                panel.show()
                return panel
            panel.close()
            if panel.active:
                return False
        self._documents_file_search.scope = scope
        self.document_search.placeholder = ('Search rclone copies' if scope == 'copies' else
                                           'Search files on this device' if scope == 'device' else 'Search local documents')
        self.documents_search_open = True
        if self.document_search_results.parent is not None:
            self.document_search_results.parent.remove(self.document_search_results)
        if self.document_search.parent is not None:
            self.document_search.parent.remove(self.document_search)
        results = self._document_search_scroll = toga.ScrollContainer(
            horizontal=False, content=self.document_search_results, style=Pack(flex=1))
        content = toga.Box(children=[self.document_search, results], style=Pack(direction=COLUMN, flex=1))
        panel = self._document_search_route = SearchRoute(self.app, content, destination=destination,
                                                         retire=self._retire_document_search)
        from .scroll_edges import fill_bottom
        fill_bottom(panel.view, results)
        if not self.documents_query.strip():
            self.clear_document_search_results()
            self.document_search_results.add(empty_document_row('Search filenames in all local folders.'))
        panel.show()
        self.document_search.focus()
        return panel

    def _retire_document_search(self):
        self._document_search_route = None
        scroll = getattr(self, '_document_search_scroll', None)
        if scroll is not None:
            # Scroll content has a native container, not a Toga parent. Release
            # that owner before a later search attaches the retained results.
            scroll.content = None
            self._document_search_scroll = None
        self._documents_file_search.stop_local_search()
        self._document_search_delay.cancel()
        self.document_search.value = ''
        self._document_search_delay.cancel()
        self.documents_search_open = False
        self._document_query_started = None
        self.clear_document_search_results()
        for widget in (self.document_search, self.document_search_results):
            if widget.parent is not None:
                widget.parent.remove(widget)
        self.show_document_collection()

    def close_document_search(self, widget=None, **kwargs):
        panel = getattr(self, '_document_search_route', None)
        if panel is not None and panel.active:
            panel.close()
        else:
            self._retire_document_search()

    def search_documents(self, widget, **kwargs):
        self.documents_query = widget.value
        self._document_query_started = None
        self._documents_file_search.stop_local_search()
        self.clear_document_search_results()
        if widget.value.strip():
            self.show_document_search_progress()
        self.show_document_collection()
        self._document_search_delay()

    async def clear_recent_documents(self, widget=None, **kwargs):
        try:
            self.app.credential_document_lists.clear_recent()
            self.recent_documents.clear()
            notes = getattr(self.app, 'vault_browser', None)
            if notes is not None:
                notes.recent_notes.clear()
        except (OSError, ValueError) as error:
            await self.main_window.dialog(toga.InfoDialog('Could not clear recent documents', str(error)))
            return
        self.refresh_document_list()
        self.refresh_hub('home')

    def refresh_document_list(self):
        if not hasattr(self, 'document_recent_list'):
            return
        from .workspace import Session
        query = getattr(self, 'documents_query', '').strip().casefold()
        if query:
            if getattr(self, '_document_query_started', None) != query:
                self._document_query_started = query
                self.clear_document_search_results()
                self.show_document_search_progress()
                self._documents_file_search.start(query)
            self.show_document_collection()
            return
        self._documents_file_search.stop_local_search()
        for section in (self.document_recent_list, self.document_saved_list):
            retire_document_actions(section)
            for child in list(section.children):
                section.remove(child)
        sessions = self.open_document_sessions()
        owner = getattr(self.app, '_archives', None)
        recent = self.recent_items()
        clear = surface(toga.Button('Clear', on_press=self.clear_recent_documents,
            style=Pack(height=44, margin_top=8)), radius=0, background='transparent',
            foreground='accent', outlined=False, eink_outlined=False)
        self.document_recent_list.add(toga.Box(children=[toga.Box(style=Pack(flex=1)), clear],
            style=Pack(direction=ROW, align_items=CENTER)))
        rows = []
        previews = self.document_recent_list._document_card_media = DocumentCardMedia(self.app)
        show_archive = owner is not None and owner.enabled() and owner.item is not None
        history_slots = MAX_RECENT - int(show_archive)
        for session, summary in recent:
            if len(rows) >= history_slots:
                break
            if (owner is not None and owner.item is not None and session.kind == 'archive'
                    and owner.matches_reference(session.source)):
                continue
            rows.append(self.recent_row(session, summary, wrap_name=True, show_source=True,
                                        previews=previews))
        if show_archive:
            rows.append(toga.Box(children=[
                toga.Button(owner.name, on_press=lambda widget: owner.present(), style=Pack(height=48, flex=1)),
                toga.Button('×', on_press=owner.close, style=Pack(height=48)),
            ], style=Pack(direction=ROW)))
        self.document_recent_list.add(document_list(rows, 'No recent items.'))
        represented = {session.identity for session in sessions}
        represented.update(session.identity for session, _ in recent)
        rows = []
        for record in self.store.cached_summaries():
            if not self.app.feature_enabled('text_editor'):
                continue
            if ('managed-text', record.id) in represented:
                continue
            summary = record.name, text_document_kind(record.name), []
            session = Session('', 'managed-text', record.id, summary[1], title=record.name)
            rows.append(self.recent_row(session, summary))
        from features.notebooks.mobile.documents import repository
        for key, name in (repository(self.app).list() if self.app.feature_enabled('notebooks') else ()):
            if ('notebook', key) not in represented and self.recent_documents.notebook_file_reference(
                    dict(provider='notebook', resource=key))['provider'] == 'notebook':
                summary = name, 'notebook', []
                rows.append(self.recent_row(Session('', 'notebook', key, 'notebook', title=name), summary))
        for row in rows:
            row.document_button.style.font_size = FILENAME_FONT
        if rows:
            self.document_saved_list.add(
                toga.Label('Saved files', style=library_heading_style(font_size=COLLECTION_FONT)), document_group(rows))
        self.show_document_collection()

    async def open_document_category(self, category):
        extensions = {
            'Text Editor': ('.txt', '.py', '.json', '.csv', '.log', '.ini', '.yaml', '.xml'),
            'Markdown Editor': ('.md', '.markdown'),
            'EPUB Reader': ('.epub',),
            'Comic Reader': ('.cbz', '.zip'),
            'Archives': ('.zip', '.cbz', '.epub'),
        }
        await self.adaptive.browser(self.app.native_host.state.destination).show_main_browser(
            'Local files', extensions=extensions[category], title=category)
