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


def status_badges(details, *, currently_open=False, icon_count=0):
    """One quiet summary, retaining warnings and the platform's default font."""
    short_names = {'Unsaved changes': 'Unsaved', 'Recovered draft': 'Recovered'}
    statuses = ['Open'] if currently_open else []
    statuses.extend(short_names.get(detail, detail) for detail in details)
    return surface(toga.Label(' · '.join(statuses),
        style=Pack(font_size=12, margin=(0, 12, 8, 12 + 28 * icon_count + (4 if icon_count else 0)))),
        radius=0, background='transparent', foreground='muted',
        outlined=False, eink_outlined=False)


def document_group(rows):
    """One rounded surface for a document section, with quiet inset dividers."""
    group = surface(toga.Box(style=Pack(direction=COLUMN, margin_bottom=8)), radius=16)
    group._document_group = True
    def borderless(widget):
        if isinstance(widget, toga.Button):
            surface(widget, radius=0, background='transparent', foreground='text',
                    outlined=False, eink_outlined=False)
        elif isinstance(widget, toga.Box):
            surface(widget, radius=0, background='transparent', outlined=False, eink_outlined=False)
        for child in widget.children:
            borderless(child)
    for index, row in enumerate(rows):
        if index:
            group.add(surface(toga.Box(style=Pack(height=1, margin_left=16, margin_right=16)),
                radius=0, background='border', outlined=False, eink_outlined=False))
        row.style.margin_bottom = 8 if index == len(rows) - 1 else 0
        row.style.margin_top = 8 if index == 0 else 0
        row.style.margin_left = row.style.margin_right = 8
        borderless(row)
        group.add(row)
    backend = type(group._impl).__module__
    if backend.startswith('toga_iOS.'):
        group._impl.native.layer.masksToBounds = True
    elif backend.startswith('toga_android.'):
        group._impl.native.setClipToOutline(True)
    return group


def empty_document_row(text):
    """Informational copy sits directly on the page, outside action surfaces."""
    return surface(toga.Label(text, style=Pack(font_size=13, margin_bottom=12)),
                   radius=0, background='transparent', foreground='muted',
                   outlined=False, eink_outlined=False)


def document_list(rows, empty_text):
    return document_group(rows) if rows else empty_document_row(empty_text)


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
        from .fold_layout import division
        from .pane_layout import panes
        fold = division(app, self)
        width = app.adaptive.content_width(destination, margin=0)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            measured = float(self._impl.native.bounds.size.width)
            if measured > 0:
                # A retained landscape hub can still report its old width
                # after its destination returns to a portrait viewport.
                width = min(width, measured)
        paired = fold is not None or width >= 700
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
        allocation = panes(width, self.layout.content_height or 1, fold=fold, gutter=0)
        vertical = paired and allocation.axis == 'column'
        self.style.direction = COLUMN if vertical else ROW
        self.trailing_scroll.style.margin_left = allocation.gap if paired and not vertical else 0
        self.trailing_scroll.style.margin_top = allocation.gap if vertical else 0
        for scroll, size in ((self.leading_scroll, allocation.leading), (self.trailing_scroll, allocation.trailing)):
            del scroll.style.height
            if vertical:
                del scroll.style.width
                scroll.style.height, scroll.style.flex = size, 0
                continue
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


def _home_state(hub, recent):
    """Compare visible content, excluding credential badges refreshed in place."""
    from copy import deepcopy
    from .document_sources import session_source
    rows = [(session.id, session.identity, summary[0], summary[1], tuple(summary[2]),
             session.id in hub.workspace.sessions, deepcopy(session_source(hub.app, session)))
            for session, summary in recent]
    return (rows, bool(hub.app.home_unlock_candidates()),
            getattr(getattr(hub.app, 'recovery_notice', None), 'text', ''), hub.workspace.error)


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
        row.document_button = name
        row.add(toga.Box(children=[name],
            style=Pack(direction=ROW, align_items=CENTER)))
        currently_open = session.id in self.workspace.sessions
        if currently_open or details:
            row.add(status_badges(details, currently_open=currently_open,
                                  icon_count=len(getattr(name, 'leading_icons', ()))))
        return row

    def build_home(self):
        recent = self.recent_items()[:5]
        self._home_content_state = _home_state(self, recent)
        self._home_recent_buttons = []
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 16, 16)))
        title = toga.Label('Your workspace', style=Pack(font_size=22, font_weight='bold', margin_bottom=16))
        if self._home_content_state[1]:
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
        recent_box = toga.Box(style=Pack(direction=COLUMN))
        recent_box.add(heading('Recent'))
        recent_rows = []
        for session, summary in recent:
            row = self.recent_row(session, summary)
            self._home_recent_buttons.append(row.document_button)
            recent_rows.append(row)
        if not recent:
            recent_box.add(empty_document_row('No recent documents.'))
        def see_all(widget=None, **kwargs):
            self.documents_query = ''
            self.app.show_documents_hub()
        recent_rows.append(toga.Button('See all in Documents', on_press=see_all, style=Pack(height=48)))
        recent_box.add(document_group(recent_rows))
        box.add(recent_box)
        notice = getattr(getattr(self.app, 'recovery_notice', None), 'text', '')
        if notice:
            box.add(toga.Label(notice, style=Pack(font_size=13, margin_top=12)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(font_size=13, margin_top=12)))
        self.register_transfer_status(box)
        from features.images.mobile.burst_camera import available, present
        camera_heading = None
        if available(self.app):
            camera_heading = heading('Camera')
            box.add(camera_heading)
            box.add(toga.Button('Burst camera', on_press=lambda widget: present(self.app),
                                style=Pack(height=48)))
        self.home_sections = HubSections(box, recent_box, before=camera_heading)
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
            toga.Button('Open Books & Comics library', on_press=self.show_library, style=Pack(height=48))],
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
        rows = []
        for session in sessions:
            summary = self.session_summary(session)
            if matches(summary):
                rows.append(self.session_panel(session, close=True, summary=summary))
        entries.add(document_list(rows,
            'No matching open documents.' if query else 'No open documents.'))
        recent = self.recent_items(excluding=[session.identity for session in sessions])
        self.document_recent_list.add(heading('Recent'))
        rows = []
        for session, summary in recent:
            if matches(summary):
                rows.append(self.recent_row(session, summary))
        self.document_recent_list.add(document_list(rows,
            'No matching recent documents.' if query else 'No closed recent documents.'))
        represented = {session.identity for session in sessions}
        represented.update(session.identity for session, _ in recent)
        self.document_saved_list.add(heading('Saved documents'))
        rows = []
        for record in self.store.cached_summaries():
            if ('managed-text', record.id) in represented:
                continue
            summary = record.name, text_document_kind(record.name), []
            if matches(summary):
                session = Session('', 'managed-text', record.id, summary[1], title=record.name)
                rows.append(self.recent_row(session, summary))
        self.document_saved_list.add(document_list(rows,
            'No matching saved documents.' if query else 'No other saved documents.'))

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
        icons = source_icons(self.app, session)
        if getattr(button, 'leading_icons', None) != tuple(icons):
            button_icons(button, icons)
        return button

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
        box.session_id = session.id
        button = list_button(toga.Button(title, on_press=self.session_opener(session.id), style=Pack(height=48, flex=1)))
        from .browser_ui import middle_filename
        middle_filename(button)
        self.document_button_icons(button, session)
        box.document_button = button
        if close:
            close_button = icon_button('close', 'Close ' + title, on_press=self.session_closer(session.id))
            box.close_button = close_button
            box.add(toga.Box(children=[button, close_button], style=Pack(direction=ROW)))
        else:
            box.add(toga.Box(children=[button],
                             style=Pack(direction=ROW)))
        if details:
            box.add(status_badges(details, icon_count=len(getattr(button, 'leading_icons', ()))))
        return box

    def new_hub_document(self, widget=None, **kwargs):
        self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        destination = self.app.native_host.state.destination
        navigation = self.app.navigation_generation
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
                self.start_cloud_restore()
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
        if destination == 'home' and hasattr(self, 'home_sections'):
            recent = self.recent_items()[:5]
            if _home_state(self, recent) == getattr(self, '_home_content_state', None):
                for button, (session, _) in zip(self._home_recent_buttons, recent):
                    self.document_button_icons(button, session)
                return
        root = self.routes.roots[destination]
        view = self.build_home() if destination == 'home' else self.build_documents_hub()
        view = self.adaptive.prepare(view, destination, root=True)
        for child in list(root.children):
            root.remove(child)
        root.add(view)
