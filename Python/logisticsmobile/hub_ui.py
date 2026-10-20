"""Native launch panels and live document summaries over existing commands."""
import toga
from .control_icons import icon_button, button_icons
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .hub_icons import icon
from .appearance import list_button
from .appearance import template_icon
from .appearance import surface, accessible_name
from .recent_documents import MAX_RECENT

DOCUMENT_TYPES = {'text': 'Text', 'markdown': 'Markdown', 'epub': 'EPUB books', 'comic': 'Comics', 'pdf': 'PDF documents'}


def text_document_kind(name):
    return 'markdown' if name.lower().endswith(('.md', '.markdown')) else 'text'


def document_groups(items):
    """Keep type order stable and omit empty sections."""
    for kind, title in DOCUMENT_TYPES.items():
        group = [item for item in items if item[0] == kind]
        if group:
            yield title, group


def heading(text):
    return toga.Label(text, style=Pack(font_size=19, font_weight='bold', margin_top=16, margin_bottom=8))


def session_identities(session, history):
    identities = {session.identity}
    source = getattr(session, 'history_source', None) or getattr(session, 'cache_source', None)
    if source is not None:
        identities.add(('file-reference', history.reference_id(source)))
    return identities


def status_badges(details, *, currently_open=False):
    """Text-labelled status remains readable without relying on colour."""
    box = toga.Box(style=Pack(direction=COLUMN, margin_left=8, margin_right=8))
    if currently_open:
        box.add(toga.Label('Currently open',
                           style=Pack(font_size=13, font_weight='bold', margin_bottom=4)))
    row, length = None, 0
    for detail in details:
        # Bound each line so phone-sized cards do not grow to fit long statuses.
        if row is None or length + len(detail) + 2 > 30:
            row = toga.Box(style=Pack(direction=ROW, margin_bottom=4))
            box.add(row)
            length = 0
        badge = surface(toga.Box(children=[toga.Label(detail, style=Pack(font_size=12, margin=4))],
                                 style=Pack(direction=COLUMN, margin_right=4)), radius=6)
        row.add(badge)
        length += len(detail) + 2
    return box


def panel(title, detail, glyph, actions):
    box = toga.Box(style=Pack(direction=COLUMN, margin=16))
    box.add(toga.Box(children=[
        template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24, margin_right=8))),
        toga.Label(title, style=Pack(flex=1, font_size=18, font_weight='bold'))],
        style=Pack(direction=ROW, margin_bottom=8)))
    if detail:
        box.add(toga.Label(detail, style=Pack(font_size=12, margin_bottom=4)))
    buttons = toga.Box(style=Pack(direction=ROW))
    for label, action in actions:
        buttons.add(toga.Button(label, on_press=action, style=Pack(height=48, flex=1)))
    box.add(buttons)
    return surface(toga.Box(children=[box], style=Pack(direction=COLUMN, margin_bottom=12)))


class PanelGrid(toga.Box):
    def __init__(self, cards, width, *, minimum_columns=1, maximum_columns=None):
        super().__init__(style=Pack(direction=COLUMN))
        self.cards = cards
        self.columns = 0
        self.minimum_columns = minimum_columns
        self.maximum_columns = maximum_columns
        self.reflow(width)

    def reflow(self, width):
        columns = max(self.minimum_columns, 3 if width >= 1100 else 2 if width >= 700 else 1)
        if self.maximum_columns is not None:
            columns = min(columns, self.maximum_columns)
        if columns == self.columns:
            return
        for row in list(self.children):
            for card in list(row.children):
                row.remove(card)
            self.remove(row)
        self.columns = columns
        for offset in range(0, len(self.cards), columns):
            row = toga.Box(style=Pack(direction=ROW))
            for index, card in enumerate(self.cards[offset:offset + columns]):
                card.style.flex = 1
                card.style.margin_right = 10 if index < columns - 1 else 0
                row.add(card)
            # Keep the final card the same width as all preceding cards.
            for _ in range(columns - len(row.children)):
                row.add(toga.Box(style=Pack(flex=1)))
            self.add(row)


class HubSections(toga.Box):
    """Retain hub controls while moving whole sections across a physical fold."""
    def __init__(self, content, trailing, *, before=None):
        super().__init__(style=Pack(direction=ROW, flex=1))
        self._hub_sections = True
        self.content = content  # Compact content compatibility for hub callers.
        self.trailing = trailing
        self.before = before
        self.leading_scroll = toga.ScrollContainer(horizontal=False, content=content, style=Pack(flex=1))
        self.trailing_content = toga.Box(style=Pack(direction=COLUMN, margin=16))
        self.trailing_scroll = toga.ScrollContainer(horizontal=False, content=self.trailing_content,
                                                    style=Pack(flex=1))
        self.add(self.leading_scroll)
        self.paired = False

    def reflow(self, app, destination):
        from .fold_layout import seam_fraction
        seam = seam_fraction(app, self, include_open=True)
        width = app.adaptive.content_width(destination, margin=0)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            measured = float(self._impl.native.bounds.size.width)
            if measured > 0:
                width = measured
        paired = seam is not None or width >= 700
        if paired != self.paired:
            if self.trailing.parent is not None:
                self.trailing.parent.remove(self.trailing)
            if paired:
                self.trailing_content.add(self.trailing)
                self.add(self.trailing_scroll)
            else:
                self.remove(self.trailing_scroll)
                index = self.content.children.index(self.before) if self.before is not None else len(self.content.children)
                self.content.insert(index, self.trailing)
            self.paired = paired
        left = round(width * (seam if seam is not None else .5))
        for scroll, size in ((self.leading_scroll, left), (self.trailing_scroll, round(width) - left)):
            if paired:
                size = max(1, size)
                if scroll.style.width != size:
                    scroll.style.width = size
                if scroll.style.flex != 0:
                    scroll.style.flex = 0
            else:
                from toga.style.pack import NONE
                if scroll.style.width != NONE:
                    del scroll.style.width
                if scroll.style.flex != 1:
                    scroll.style.flex = 1


class HubUI:
    def session_visible(self, session):
        if session.provider == 'credential-reference':
            return getattr(session, 'cache_id', None) in self.app.credential_document_lists.states
        if session.provider == 'provider-session':
            manager = getattr(self, 'private_sessions', None)
            return manager is not None and manager.available(session.id)
        return True

    def recent_items(self, *, excluding=()):
        """Merge history with live owners, resolving file aliases only in RAM."""
        excluded = set(excluding)
        live = {}
        for current in self.workspace.sessions.values():
            aliases = session_identities(current, self.recent_documents)
            if current.identity in excluded:
                excluded.update(aliases)
            if self.session_visible(current):
                live.update((identity, current) for identity in aliases)
        history = self.recent_documents.sessions()
        recorded = {session.identity for session in history}
        # Unrecorded session-only work is still discoverable without persisting it.
        missing = [session for session in reversed(list(self.workspace.sessions.values()))
                   if self.session_visible(session)
                   and not session_identities(session, self.recent_documents) & recorded]
        active_missing = [session for session in missing if session.id == self.workspace.active]
        other_missing = [session for session in missing if session.id != self.workspace.active]
        items, seen = [], set()
        for entry in [*active_missing, *history, *other_missing]:
            session = live.get(entry.identity, entry)
            aliases = session_identities(session, self.recent_documents)
            if aliases & (excluded | seen):
                continue
            seen.update(aliases)
            summary = self.session_summary(session)
            if session.id in self.workspace.sessions or 'Unavailable; retry to reopen' not in summary[2]:
                items.append((session, summary))
        return items[:MAX_RECENT]

    def recent_opener(self, session):
        async def reopen(widget=None, **kwargs):
            # Re-resolve at press time: the row may outlive a close or reopen.
            aliases = session_identities(session, self.recent_documents)
            current = next((item for item in self.workspace.sessions.values()
                            if self.session_visible(item)
                            and aliases & session_identities(item, self.recent_documents)), None)
            if current is not None:
                self.adaptive.menu_open['documents'] = False
                self.session_opener(current.id)()
                return
            if not self.checkpoint():
                return
            self.adaptive.menu_open['documents'] = False
            source = (getattr(session, 'source', None) or getattr(session, 'history_source', None)
                      or getattr(session, 'cache_source', None))
            if source is not None:
                from .document_sources import reopen_file
                try:
                    await reopen_file(self.app, source)
                except (OSError, ValueError, KeyError) as error:
                    await self.main_window.dialog(toga.InfoDialog('Could not open file', str(error)))
            elif session.provider == 'library':
                await self.open_book(session.resource)
            elif self.open_document(session.resource):
                self.show_documents(resume=True)
        return reopen

    def recent_row(self, session, summary):
        title, kind, details = summary
        row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        opener = self.recent_opener(session)
        from .browser_ui import middle_filename
        name = list_button(toga.Button(title, on_press=opener, style=Pack(height=48, flex=1)))
        middle_filename(name)
        self.document_button_icons(name, session)
        row.add(toga.Box(children=[name],
            style=Pack(direction=ROW, align_items=CENTER)))
        currently_open = session.id in self.workspace.sessions
        if currently_open or details:
            row.add(status_badges(details, currently_open=currently_open))
        return row

    def build_home(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 16, 16)))
        title = toga.Label('Your workspace', style=Pack(font_size=22, font_weight='bold', margin_bottom=16))
        if self.app.home_unlock_candidates():
            title.style.flex = 1
            unlock = surface(icon_button('storage_crypt', 'Unlock credentials',
                on_press=self.app.show_home_unlock), foreground='text')
            unlock.style.margin_left = 8
            box.add(toga.Box(children=[title, unlock],
                style=Pack(direction=ROW, align_items=CENTER)))
        else:
            box.add(title)
        self.home_continue = None
        box.add(toga.Label('Open a file or start a new document.', style=Pack(margin_bottom=12)))
        self.home_actions = toga.Box(children=[
            toga.Button('Open file…', on_press=self.open_hub_file, style=Pack(height=48, flex=1, margin_right=8)),
            toga.Button('New document', on_press=self.new_hub_document, style=Pack(height=48, flex=1))],
            style=Pack(direction=ROW))
        self.home_content = box
        box.add(self.home_actions)
        recent = self.recent_items()[:5]
        recent_box = toga.Box(style=Pack(direction=COLUMN))
        recent_box.add(heading('Recent'))
        for session, summary in recent:
            recent_box.add(self.recent_row(session, summary))
        if not recent:
            recent_box.add(toga.Label('Recently opened files will appear here.', style=Pack(font_size=13)))
        def see_all(widget=None, **kwargs):
            self.documents_query = ''
            self.app.show_documents_hub()
        recent_box.add(toga.Button('See all in Documents', on_press=see_all,
                                  style=Pack(height=48)))
        box.add(recent_box)
        notice = getattr(getattr(self.app, 'recovery_notice', None), 'text', '')
        if notice:
            box.add(toga.Label(notice, style=Pack(font_size=13, margin_top=12)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(font_size=13, margin_top=12)))
        self.register_transfer_status(box)
        self.home_sections = HubSections(box, recent_box)
        self.reflow_home()
        return self.home_sections

    def reflow_home(self):
        self.home_sections.reflow(self.app, 'home')

    def reflow_documents_hub(self):
        self.documents_sections.reflow(self.app, 'documents')

    def build_documents_hub(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Documents', style=Pack(font_size=22, font_weight='bold', margin_bottom=12)))
        self.document_search = toga.TextInput(placeholder='Search documents',
            value=getattr(self, 'documents_query', ''), on_change=self.search_documents,
            style=Pack(height=48, margin_bottom=8))
        box.add(self.document_search)
        self.document_grids = []
        self.document_categories = {}
        self.document_launchers = PanelGrid([], self.main_window.size.width)
        self.document_open_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_recent_list = toga.Box(style=Pack(direction=COLUMN))
        self.document_saved_list = toga.Box(style=Pack(direction=COLUMN))
        history = toga.Box(children=[self.document_recent_list, self.document_saved_list,
            toga.Button('Books & Comics library', on_press=self.show_library, style=Pack(height=48))],
            style=Pack(direction=COLUMN))
        box.add(self.document_open_list, history)
        self.refresh_document_list()
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.register_transfer_status(box)
        self.documents_sections = HubSections(box, history)
        self.reflow_documents_hub()
        return self.documents_sections

    def search_documents(self, widget, **kwargs):
        self.documents_query = widget.value
        self.refresh_document_list()

    def refresh_document_list(self):
        if not hasattr(self, 'document_open_list'):
            return
        from .workspace import Session
        query = getattr(self, 'documents_query', '').strip().casefold()
        def matches(summary):
            return not query or query in summary[0].casefold()
        for section in (self.document_open_list, self.document_recent_list, self.document_saved_list):
            for child in list(section.children):
                section.remove(child)
        sessions = [session for session in self.workspace.sessions.values() if self.session_visible(session)]
        sessions.sort(key=lambda session: session.id != self.workspace.active)
        entries = self.document_open_list
        entries.add(heading('All open'))
        entries.add(toga.Label('Closing keeps saved files. You’ll be asked about unsaved edits.',
                              style=Pack(font_size=12, margin_bottom=8)))
        found = False
        for session in sessions:
            summary = self.session_summary(session)
            if matches(summary):
                entries.add(self.session_panel(session, close=True, summary=summary))
                found = True
        if not found:
            entries.add(toga.Label('No matching open documents.' if query else 'No open documents.',
                                   style=Pack(font_size=13)))
        recent = self.recent_items(excluding=[session.identity for session in sessions])
        self.document_recent_list.add(heading('Recent'))
        found = False
        for session, summary in recent:
            if matches(summary):
                self.document_recent_list.add(self.recent_row(session, summary))
                found = True
        if not found:
            self.document_recent_list.add(toga.Label('No matching recent documents.' if query else
                'Closed recent documents will appear here.', style=Pack(font_size=13)))
        represented = {session.identity for session in sessions}
        represented.update(session.identity for session, _ in recent)
        self.document_saved_list.add(heading('Saved documents'))
        found = False
        for record in self.store.cached_summaries():
            if ('managed-text', record.id) in represented:
                continue
            summary = record.name, text_document_kind(record.name), []
            if matches(summary):
                session = Session('', 'managed-text', record.id, summary[1], title=record.name)
                self.document_saved_list.add(self.recent_row(session, summary))
                found = True
        if not found:
            self.document_saved_list.add(toga.Label('No matching saved documents.' if query else
                'Other saved text and Markdown documents will appear here.', style=Pack(font_size=13)))

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

    def document_button_icons(self, button, session):
        from .document_sources import source_icons
        return button_icons(button, source_icons(self.app, session))

    def session_summary(self, session):
        """Resolve display metadata from its owner; workspace manifests omit names."""
        title = session.title or 'Untitled document'
        kind = session.kind
        owner = self.text_views.get(session.id)
        dirty = owner.document.modified if owner is not None else session.dirty
        if session.provider == 'provider-session':
            manager = getattr(self, 'private_sessions', None)
            private_owner = manager.controllers.get(session.id) if manager else None
            if private_owner is not None:
                dirty = private_owner.private_dirty()
        details = ['Unsaved changes', 'Draft'] if dirty else []
        if owner is not None:
            title = owner.document.name
            kind = text_document_kind(title)
        if session.provider == 'provider-session':
            if not getattr(session, 'history_source', None):
                details.append('Session only')
        if owner is not None and owner.document.conflict:
            details.append('File changed outside editor')
        if session.provider == 'managed-text' and owner is None:
            try:
                prepared = getattr(self.app, '_startup_display', {}).get(session.resource)
                if (prepared is not None
                        and prepared['revision'] == self.store._recovery_revision(self.store.path(session.resource, '.json'))
                        and prepared['source_revision'] == self.store._recovery_revision(self.store.path(session.resource, '.data'))):
                    from types import SimpleNamespace
                    document = SimpleNamespace(**prepared)
                else:
                    document = self.store.open(session.resource)
                title = document.name
                kind = text_document_kind(title)
                if document.modified:
                    details = ['Unsaved changes', 'Recovered draft']
                if document.conflict:
                    details.append('File changed outside editor')
            except (OSError, ValueError, KeyError, TypeError):
                details.append('Unavailable; retry to reopen')
        elif session.provider == 'library':
            try:
                record = self.reader_manager().catalog.library_store.read_record(session.resource)[0]
                title, kind = record['name'], record['kind']
            except (OSError, ValueError, KeyError, TypeError):
                details.append('Unavailable; retry to reopen')
        return title, kind, details

    def session_panel(self, session, *, close=False, summary=None, show_kind=False):
        title, kind, details = summary if summary is not None else self.session_summary(session)
        if show_kind:
            details = [DOCUMENT_TYPES.get(kind, 'Document'), *details]
        # One compact row per item; names are the primary navigation target.
        box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        if details:
            box.add(status_badges(details))
        box.session_id = session.id
        button = list_button(toga.Button(title, on_press=self.session_opener(session.id), style=Pack(height=48, flex=1)))
        from .browser_ui import middle_filename
        middle_filename(button)
        self.document_button_icons(button, session)
        if close:
            close_button = icon_button('close', 'Close ' + title, on_press=self.session_closer(session.id))
            box.add(toga.Box(children=[button, close_button], style=Pack(direction=ROW)))
        else:
            box.add(toga.Box(children=[button],
                             style=Pack(direction=ROW)))
        return box

    def new_hub_document(self, widget=None, **kwargs):
        self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        destination = self.app.native_host.state.destination
        navigation = self.app.navigation_generation
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None:
            await restore
        if (not self.app.active_host or self.app.native_host.state.destination != destination
                or self.app.navigation_generation != navigation):
            return False
        return await self.adaptive.browser(destination).show_main_browser('Local files', title='Open file')

    def refresh_hub(self, destination):
        if destination == 'files' and self.routes.screens['files']:
            # Retain the existing folder and any document detail above it.
            return
        if destination == 'files' and self.window_id == 'primary':
            if getattr(self, 'folder_source', 'Local') != 'Local':
                self.show_cloud(present=False)
            view = self.folder_picker_or_error()
            root = self.routes.roots['files']
            if list(root.children) == [view]:
                return
            view = self.adaptive.prepare(view, 'files', root=True)
            self.routes.trim('files', 0)
            for child in list(root.children):
                root.remove(child)
            root.add(view)
            self.routes.render('files')
            return
        # Refresh only the visible root; retained detail routes remain untouched.
        if destination not in ('home', 'documents') or self.routes.screens[destination]:
            return
        if destination == 'documents' and self.adaptive.split is not None and self.adaptive.in_detail:
            return
        if destination == 'documents':
            self.refresh_documents()
        root = self.routes.roots[destination]
        view = self.build_home() if destination == 'home' else self.build_documents_hub()
        view = self.adaptive.prepare(view, destination, root=True)
        for child in list(root.children):
            root.remove(child)
        root.add(view)
