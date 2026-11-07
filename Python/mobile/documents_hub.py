"""Documents tabs, local search results and library launchers."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .appearance import accessible_name, batch_surfaces, list_button, surface
from .control_icons import icon_button, button_icons
from .hub_controls import PanelGrid, document_list, empty_document_row, text_document_kind
from .ui_metrics import TOUCH_TARGET


COLLECTIONS = ('Libraries', 'Favourites', 'Open', 'Recent', 'Saved')
SIDEBAR_WIDTH = 160
SIDEBAR_BREAKPOINT = 480
TABS_BREAKPOINT = 300
COLLECTION_FONT = 13
FILENAME_FONT = 15


def library_heading_style():
    return Pack(font_size=COLLECTION_FONT, font_weight='bold', margin_bottom=8)


class DocumentsHub:
    """Presentation methods share the HubController state and service contract."""
    def reflow_documents_hub(self):
        from commonUtils.ui.native.forms import fit_text
        from .fold_layout import division

        body = self._document_collection_body
        width = self.adaptive.content_width('documents', margin=32)
        fold = division(self.app, body)
        searching = self.document_search.parent is not None
        sidebar = fold.vertical if fold is not None else width >= SIDEBAR_BREAKPOINT and not searching
        selector_width = (fold.x if fold is not None else SIDEBAR_WIDTH) if sidebar else None
        if fold is not None:
            gap = fold.width if sidebar else fold.height
        else:
            gap = 16 if sidebar else 0
        result_width = width - selector_width - gap if sidebar else width
        wrapped = not sidebar and width < TABS_BREAKPOINT

        geometry = (sidebar, wrapped, searching, selector_width, fold, gap)
        if geometry != self._document_collection_geometry:
            self._document_collection_geometry = geometry
            body.style.direction = ROW if sidebar else COLUMN
            nav = self._document_collection_navigation
            detail = self._document_collection_detail
            if sidebar:
                del nav.style.height
                nav.style.width = selector_width
            else:
                del nav.style.width
                # Both panes scroll independently when a horizontal fold fixes
                # the space above the crease, including in a short window.
                nav.style.height = (fold.y if fold is not None else
                    44 + (0 if searching else (TOUCH_TARGET + 2) * (2 if wrapped else 1)))
            detail.style.margin_left = gap if sidebar else 0
            detail.style.margin_top = gap if not sidebar else 0
            self._layout_document_tabs(sidebar, wrapped)

        # Fit status and source text to the allocated pane, including after a
        # fold or search transition, without letting it expand the viewport.
        def fit(widget):
            if isinstance(widget, toga.Label):
                fit_text(widget, max(1, int(result_width) - 32))
            for child in widget.children:
                fit(child)
        fit(self.document_results)

    def _layout_document_tabs(self, sidebar, wrapped):
        mode = 'sidebar' if sidebar else 'wrapped' if wrapped else 'tabs'
        if mode == self._document_tabs_mode:
            return
        self._document_tabs_mode = mode
        for cell in self._document_tab_cells.values():
            if cell.parent is not None:
                cell.parent.remove(cell)
        self.document_views.clear()
        names = (COLLECTIONS[:3], COLLECTIONS[3:]) if wrapped else (COLLECTIONS,)
        for group in names:
            row = toga.Box(style=Pack(direction=COLUMN if sidebar else ROW))
            for name in group:
                cell = self._document_tab_cells[name]
                weight = 1.35 if name in ('Libraries', 'Favourites') else 1
                cell.style.flex = 0 if sidebar else weight
                row.add(cell)
            self.document_views.add(row)
        self._style_document_tabs()

    def _style_document_tabs(self):
        from .folder_hub_style import source_tab
        sidebar = self._document_tabs_mode == 'sidebar'
        with batch_surfaces():
            for name, button in self.document_view_buttons.items():
                selected = self.documents_view == name
                source_tab(button, selected)
                surface(button, radius=8 if sidebar else 0,
                        background='hover' if sidebar and selected else 'transparent',
                        foreground='accent' if selected else 'muted', outlined=False,
                        eink_outlined=False, eink_selected=selected)
                indicator = self._document_tab_cells[name].children[-1]
                surface(indicator, radius=0,
                        background='accent' if selected and not sidebar else 'transparent',
                        outlined=False, eink_outlined=False)

    def build_documents_hub(self):
        from commonUtils.ui.native.event_loop import DebouncedCallback
        previous = getattr(self, '_document_search_delay', None)
        if previous is not None:
            previous.cancel()
        search = getattr(self, '_documents_file_search', None)
        if search is not None:
            search.stop_local_search()
        from .notes_discovery import cancel
        cancel(self.app)
        comics = getattr(self, '_document_comics_discovery', None)
        if comics is not None:
            comics.cancel()
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
        self.document_open_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_open_list._open_documents = True
        self.document_recent_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_saved_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_notes_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_comics_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_favourites_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_libraries_list = toga.Box(children=[self.document_notes_list, self.document_comics_list],
                                                style=Pack(direction=COLUMN))
        self._document_libraries_ready = False
        for menu in getattr(self, '_document_search_menus', ()):
            menu.dispose()
        self._document_search_menus = []
        self.document_search_results = toga.Box(style=Pack(direction=COLUMN))
        self.document_results = toga.Box(style=Pack(direction=COLUMN))
        self.document_views = toga.Box(style=Pack(direction=COLUMN))
        self.document_view_buttons = {}
        self._document_tab_cells = {}
        self._document_tabs_mode = None
        self._document_collection_geometry = None
        self.documents_view = getattr(self, 'documents_view', 'Libraries')
        for name in COLLECTIONS:
            def choose(widget=None, name=name, **kwargs):
                self.documents_view = name
                self.show_document_collection()
            button = toga.Button(name, on_press=choose,
                style=Pack(height=TOUCH_TARGET, font_size=COLLECTION_FONT))
            accessible_name(button, name)
            self.document_view_buttons[name] = button
            indicator = toga.Box(style=Pack(height=2, margin_left=4, margin_right=4))
            self._document_tab_cells[name] = toga.Box(children=[button, indicator],
                                                     style=Pack(direction=COLUMN))

        title = toga.Label('Documents', style=Pack(font_size=26, font_weight='bold'))
        self._document_collection_header = toga.Box(children=[title, self.document_views],
                                                    style=Pack(direction=COLUMN))
        self._document_collection_navigation = toga.ScrollContainer(horizontal=False,
            content=self._document_collection_header)
        self._document_collection_title = toga.Label(self.documents_view,
            style=Pack(font_size=16, font_weight='bold', margin_bottom=8))
        results = toga.Box(children=[self._document_collection_title, self.document_results],
                           style=Pack(direction=COLUMN, margin=(8, 0, 16, 0)))
        self._document_collection_detail = toga.Box(children=[self.app._documents_status_row,
            toga.ScrollContainer(horizontal=False, content=results, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, flex=1))
        self._document_collection_body = toga.Box(
            children=[self._document_collection_navigation, self._document_collection_detail],
            style=Pack(direction=COLUMN, flex=1))
        box.add(self._document_collection_body)
        from .document_search import DocumentSearch
        self._documents_file_search = DocumentSearch(self.app, self.publish_document_search)
        self.documents_sections = box
        self.refresh_document_list()
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.register_transfer_status(box)
        return box

    def show_document_collection(self):
        if not hasattr(self, 'document_results'):
            return
        query = bool(getattr(self, 'documents_query', '').strip())
        searching = query or getattr(self, 'documents_search_open', False)
        status = self.app._documents_status_row
        if searching and self.document_search.parent is None:
            status.add(self.document_search)
        elif not searching and self.document_search.parent is status:
            status.remove(self.document_search)
        parent = self.document_views.parent
        if searching and parent is not None:
            parent.remove(self.document_views)
        elif not searching and parent is None:
            self._document_collection_header.add(self.document_views)
        self._document_collection_title.text = 'Search results' if searching else self.documents_view
        self._style_document_tabs()
        selected = self.document_search_results if searching else {
            'Open': self.document_open_list, 'Recent': self.document_recent_list,
            'Saved': self.document_saved_list, 'Libraries': self.document_libraries_list,
            'Favourites': self.document_favourites_list}[self.documents_view]
        if list(self.document_results.children) != [selected]:
            self.document_results.clear()
            self.document_results.add(selected)
        discover = not getattr(self.app, '_startup_in_progress', False)
        if discover and not searching and self.documents_view == 'Libraries' and not self._document_libraries_ready:
            self.populate_document_libraries()
        if discover and not searching and self.documents_view == 'Favourites':
            from .favourites import populate
            self.document_favourites_list.clear()
            populate(self.app, self.document_favourites_list, heading=False, row_font=FILENAME_FONT)
        self.reflow_documents_hub()

    def populate_document_libraries(self):
        self._document_libraries_ready = True
        from .notes_discovery import populate
        populate(self.app, self.document_notes_list, title='Notes', refresh=False,
                 title_style=library_heading_style(), row_font=FILENAME_FONT)
        self.document_comics_list.clear()
        self.document_comics_list.add(toga.Label('Comics', style=library_heading_style()))
        if not self.app.feature_enabled('comics'):
            self.document_comics_list.add(empty_document_row('Comics is disabled.'))
            return
        catalog = self.app.reader_manager().catalog
        target = self.document_comics_list
        target.add(empty_document_row('Finding libraries…'))
        async def discover():
            await catalog.refresh_library_folders()
            if target is not self.document_comics_list or not self.app.active_host:
                return
            target.clear()
            target.add(toga.Label('Comics', style=library_heading_style()))
            rows = []
            for record in catalog.library_records:
                if not self.app.library_folder_visible(record):
                    continue
                async def open_library(widget=None, record=record, **kwargs):
                    if self.app.checkpoint():
                        await catalog.library_host.open_folder(record)
                button = list_button(toga.Button(record['name'], on_press=open_library,
                                                  style=Pack(height=TOUCH_TARGET, font_size=FILENAME_FONT)))
                from .browser_ui import middle_filename
                middle_filename(button)
                button_icons(button, [('folder_hub', record['source'])])
                rows.append(button)
            target.add(document_list(rows, 'No Comics libraries found.'))
            if 'could not' in catalog.book_status.text:
                target.add(empty_document_row(catalog.book_status.text))
            self.reflow_documents_hub()
        old = getattr(self, '_document_comics_discovery', None)
        if old is not None:
            old.cancel()
        self._document_comics_discovery = self.app.loop.create_task(discover())

    def clear_document_search_results(self):
        for menu in getattr(self, '_document_search_menus', ()):
            menu.dispose()
        self._document_search_menus = []
        self.document_search_results.clear()

    def publish_document_search(self, hits, failures):
        target = self.document_search_results
        self.clear_document_search_results()
        rows = []
        for hit in hits:
            async def open_result(widget=None, source=hit['source'], hit=hit, **kwargs):
                if not self.app.checkpoint():
                    return
                if hit.get('directory'):
                    from .document_search import reveal_search_hit
                    return await reveal_search_hit(self.app, hit)
                if source['type'] == 'managed':
                    return self.app.stored_document_opener(source['resource'])()
                if source['type'] == 'notebook':
                    from features.notebooks.mobile.documents import open_notebook
                    return await open_notebook(self.app, key=source['resource'])
                from .document_sources import reopen_file
                try:
                    await reopen_file(self.app, source)
                except (OSError, ValueError) as error:
                    await self.main_window.dialog(toga.InfoDialog('Could not open file', str(error)))
            button = list_button(toga.Button(hit['name'], on_press=open_result,
                                             style=Pack(height=TOUCH_TARGET, flex=1, font_size=FILENAME_FONT)))
            from .browser_ui import middle_filename
            middle_filename(button)
            button_icons(button, [('storage_local', 'Local document'), *(
                [('storage_unlocked', 'Unlocked LocalCrypt')] if hit['private'] else [])])
            from .browser_ui import entry_icon
            from .action_menu import ActionMenu
            more = icon_button('more', 'File actions for ' + hit['name'])
            actions = [('Open folder' if hit.get('directory') else 'Open', open_result)]
            if hit['source']['type'] in {'local', 'crypt'}:
                async def reveal(widget=None, hit=hit, **kwargs):
                    from .document_search import reveal_search_hit
                    try:
                        return await reveal_search_hit(self.app, hit)
                    except (OSError, ValueError) as error:
                        await self.main_window.dialog(toga.InfoDialog('Could not show file', str(error)))
                actions.append(('Show in folder', reveal))
            more._document_search_menu = ActionMenu(more, self.app, actions, document=False)
            self._document_search_menus.append(more._document_search_menu)
            row = toga.Box(children=[entry_icon(hit.get('directory', False)), button, more],
                           style=Pack(direction=ROW, align_items=CENTER))
            rows.append(row)
        target.add(document_list(rows, 'No matching local documents.'))
        if failures:
            target.add(empty_document_row('Some local locations could not be searched.'))
        self.reflow_documents_hub()

    def open_document_search(self, widget=None, **kwargs):
        self.documents_search_open = True
        self.show_document_collection()
        if not self.documents_query.strip():
            self.clear_document_search_results()
            self.document_search_results.add(empty_document_row('Search filenames in all local folders.'))
        self.app.adaptive.render()
        self.document_search.focus()

    def close_document_search(self, widget=None, **kwargs):
        self._documents_file_search.stop_local_search()
        self.document_search.value = ''
        self._document_search_delay.cancel()
        self.documents_search_open = False
        self.clear_document_search_results()
        self.show_document_collection()
        self.app.adaptive.render()

    def search_documents(self, widget, **kwargs):
        self.documents_query = widget.value
        self._documents_file_search.stop_local_search()
        self.clear_document_search_results()
        if widget.value.strip():
            self.document_search_results.add(empty_document_row('Searching local filenames…'))
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
        if not hasattr(self, 'document_open_list'):
            return
        from .workspace import Session
        query = getattr(self, 'documents_query', '').strip().casefold()
        if query:
            self.clear_document_search_results()
            self.document_search_results.add(empty_document_row('Searching local filenames…'))
            self._documents_file_search.start(query)
            self.show_document_collection()
            return
        self._documents_file_search.stop_local_search()
        for section in (self.document_open_list, self.document_recent_list, self.document_saved_list):
            for child in list(section.children):
                section.remove(child)
        sessions = self.open_document_sessions()
        entries = self.document_open_list
        rows = []
        for session in sessions:
            summary = self.session_summary(session)
            row = self.session_panel(session, close=True, summary=summary)
            row.document_button.style.font_size = FILENAME_FONT
            rows.append(row)
        entries.add(document_list(rows, 'No open documents.'))
        if rows:
            entries.add(empty_document_row('Close a view with ×. Your saved file stays.'))
        recent = self.recent_items(excluding=[session.identity for session in sessions])
        clear = surface(toga.Button('Clear', on_press=self.clear_recent_documents,
            style=Pack(height=44, margin_top=8)), radius=0, background='transparent',
            foreground='accent', outlined=False, eink_outlined=False)
        self.document_recent_list.add(toga.Box(children=[toga.Box(style=Pack(flex=1)), clear],
            style=Pack(direction=ROW, align_items=CENTER)))
        rows = []
        for session, summary in recent:
            row = self.recent_row(session, summary)
            row.document_button.style.font_size = FILENAME_FONT
            rows.append(row)
        self.document_recent_list.add(document_list(rows, 'No closed recent documents.'))
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
        self.document_saved_list.add(document_list(rows, 'No other saved documents.'))
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
