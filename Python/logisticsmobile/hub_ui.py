"""Native launch panels and live document summaries over existing commands."""
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .hub_icons import icon
from .appearance import list_button
from .appearance import template_icon
from .appearance import surface, action_button, accessible_name
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


def status_badges(details):
    """Text-labelled status remains readable without relying on colour."""
    box = toga.Box(style=Pack(direction=COLUMN, margin_left=8, margin_right=8))
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


def home_surface(widget, *, hero=False):
    return surface(widget, radius=20 if hero else 16)


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
        row.add(toga.Box(children=[*self.document_source_badges(session, opener), name],
            style=Pack(direction=ROW, align_items=CENTER)))
        badges = (['Open'] if session.id in self.workspace.sessions else []) + details
        if badges:
            row.add(status_badges(badges))
        return row

    def build_home(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        title = toga.Label('Your workspace', style=Pack(font_size=22, font_weight='bold', margin_top=8, margin_bottom=16))
        if self.app.home_unlock_candidates():
            title.style.flex = 1
            unlock = surface(icon_button('storage_crypt', 'Unlock credentials',
                on_press=self.app.show_home_unlock), foreground='text')
            unlock.style.margin_left = 8
            box.add(toga.Box(children=[title, unlock],
                style=Pack(direction=ROW, align_items=CENTER)))
        else:
            box.add(title)
        active = self.workspace.sessions.get(self.workspace.active)
        active = active if active is not None and self.session_visible(active) else None
        self.home_continue = None
        if active is not None:
            title, kind, details = self.session_summary(active)
            hero = toga.Box(style=Pack(direction=COLUMN, margin_bottom=12))
            hero_content = toga.Box(style=Pack(direction=COLUMN, margin=16))
            hero.add(hero_content)
            hero_content.add(toga.Label('Continue', style=Pack(font_size=13, margin_bottom=8)))
            from textwrap import fill
            hero_content.add(toga.Label(fill(title, width=26), style=Pack(font_size=22, font_weight='bold', margin_bottom=8)))
            if details:
                hero_content.add(status_badges(details))
            self.home_continue_button = action_button(toga.Button('Continue', on_press=self.session_opener(active.id),
                                style=Pack(height=48)))
            hero_content.add(self.home_continue_button)
            box.add(home_surface(hero, hero=True))
            self.home_continue = hero
        else:
            box.add(toga.Label('Open a file or start a new document.', style=Pack(margin_bottom=12)))
        self.home_actions = toga.Box(children=[
            toga.Button('New document', on_press=self.new_hub_document, style=Pack(height=48, flex=1, margin_right=8)),
            toga.Button('Open file…', on_press=self.open_hub_file, style=Pack(height=48, flex=1))],
            style=Pack(direction=ROW))
        self.home_content = box
        box.add(self.home_actions)
        recent = self.recent_items()
        recent_box = toga.Box(style=Pack(direction=COLUMN))
        recent_box.add(heading('Recent'))
        for session, summary in recent:
            recent_box.add(self.recent_row(session, summary))
        if not recent:
            recent_box.add(toga.Label('Recently opened files\nwill appear here.', style=Pack(font_size=13)))
        spaces = toga.Box(style=Pack(direction=COLUMN))
        spaces.add(heading('Your spaces'))
        for title, subtitle, glyph, action in (
            ('Folder Hub', 'Local · LocalCrypt · Remote', 'folder_hub', self.show_home_files),
            ('Books & Comics', 'Browse your library', 'books', self.show_library),
        ):
            text = toga.Box(children=[
                list_button(toga.Button(title, on_press=action, style=Pack(height=48))),
                toga.Label(subtitle, style=Pack(font_size=12, margin_left=8, margin_right=8))],
                style=Pack(direction=COLUMN, flex=1))
            spaces.add(toga.Box(children=[
                template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24, margin_right=8))),
                text], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12)))
        self.home_panels = PanelGrid([recent_box, spaces], self.main_window.size.width, maximum_columns=2)
        box.add(self.home_panels)
        self.register_transfer_status(box)
        self.reflow_home()
        return toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))

    def reflow_home(self):
        from .fold_layout import seam_fraction
        seam = seam_fraction(self, self.home_content)
        paired = seam is not None
        self.home_panels.minimum_columns = 2 if paired else 1
        self.home_panels.reflow(self.main_window.size.width)
        # Both rows use the same physical seam; half the gutter lies on each side.
        width = self.home_content.layout.content_width
        for row, gap in ((self.home_actions, 8), (self.home_panels.children[0], 10)):
            sizes = [None] * len(row.children)
            if paired and width and len(row.children) == 2:
                left = max(1, width * seam - gap / 2)
                sizes = [left, max(1, width - left - gap)]
            for child, size in zip(row.children, sizes):
                flex = 1 if size is None else 0
                if child.style.flex != flex:
                    child.style.flex = flex
                if size is None:
                    from toga.style.pack import NONE
                    if child.style.width != NONE:
                        del child.style.width
                elif child.style.width != size:
                    child.style.width = size

    def build_documents_hub(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Box(children=[
            toga.Button('New document', on_press=self.new_hub_document,
                        style=Pack(height=48, flex=1, margin_right=8)),
            toga.Button('Open file…', on_press=self.open_hub_file, style=Pack(height=48, flex=1))],
            style=Pack(direction=ROW)))
        self.document_grids = []
        self.document_categories = {}
        self.document_launchers = PanelGrid([], self.main_window.size.width)
        sessions = [session for session in self.workspace.sessions.values() if self.session_visible(session)]
        switcher = toga.Box(style=Pack(direction=COLUMN))
        entries = toga.Box(style=Pack(direction=COLUMN))

        def toggle(widget, **kwargs):
            if entries in switcher.children:
                switcher.remove(entries)
                widget.text = f'Open · {len(sessions)} ▸'
                accessible_name(widget, f'Show {len(sessions)} open documents')
            else:
                switcher.add(entries)
                widget.text = f'Open · {len(sessions)} ▾'
                accessible_name(widget, f'Hide {len(sessions)} open documents')

        switcher.add(accessible_name(toga.Button(f'Open · {len(sessions)} ▸', on_press=toggle,
                                enabled=bool(sessions), style=Pack(height=48)),
                                f'Show {len(sessions)} open documents'))
        entries.add(toga.Label('Closing keeps saved files.\nYou’ll be asked about unsaved edits.',
                              style=Pack(font_size=12, margin_bottom=8)))
        for session in sessions:
            entries.add(self.session_panel(session, close=True))
        box.add(switcher)
        box.add(heading('Recent'))
        recent = self.recent_items()
        if self.preferences.values['document_card_overview'] == 'true' and recent:
            grid = PanelGrid([self.session_card(session, summary, recent=True) for session, summary in recent],
                             self.main_window.size.width, maximum_columns=3)
            self.document_grids.append(grid)
            box.add(grid)
        else:
            for session, summary in recent:
                box.add(self.recent_row(session, summary))
        if not recent:
            box.add(toga.Label('Recently used documents\nwill appear here.', style=Pack(font_size=13)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.register_transfer_status(box)
        return toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))

    async def open_document_category(self, category):
        extensions = {
            'Text Editor': ('.txt', '.py', '.json', '.csv', '.log', '.ini', '.yaml', '.xml'),
            'Markdown Editor': ('.md', '.markdown'),
            'EPUB Reader': ('.epub',),
            'Comic Reader': ('.cbz', '.zip'),
            'Archives': ('.zip', '.cbz', '.epub'),
        }
        await self.adaptive.browser('documents').show_main_browser(
            'Local files', extensions=extensions[category], title=category)

    def document_source_badges(self, session, opener):
        from .document_sources import source_icons
        from .folder_hub_style import compact_icon
        badges = []
        for glyph, label in source_icons(self.app, session):
            button = icon_button(glyph, label, on_press=opener)
            compact_icon(button, width=26)
            badges.append(button)
        return badges

    def session_card(self, session, summary, *, recent=False):
        """A lightweight overview; never mount live editors or private readers."""
        title, kind, details = summary
        box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=12))
        box.session_id = session.id
        from .browser_ui import middle_filename
        opener = self.recent_opener(session) if recent else self.session_opener(session.id)
        name = list_button(toga.Button(title, on_press=opener, style=Pack(flex=1, height=48)))
        middle_filename(name)
        actions = [*self.document_source_badges(session, opener), name]
        if not recent:
            actions.append(icon_button('close', 'Close ' + title, on_press=self.session_closer(session.id)))
        box.add(toga.Box(children=actions, style=Pack(direction=ROW, margin=12)))
        preview = ''
        owner = self.text_views.get(session.id)
        if owner is not None and session.provider == 'managed-text':
            preview = owner.document.text
        elif session.provider == 'managed-text':
            try:
                preview = self.store.open(session.resource).text
            except (OSError, ValueError, KeyError, TypeError):
                pass
        # A bounded excerpt keeps card height and native layout work predictable.
        from textwrap import wrap
        excerpt = '\n'.join(wrap(' '.join(preview[:600].split()), width=32)[:4])
        box.add(toga.Label(excerpt or 'No preview available',
                           style=Pack(height=80, font_size=12, margin_left=12, margin_right=12, margin_bottom=8)))
        badges = (['Open'] if recent and session.id in self.workspace.sessions else []) + details
        if badges:
            box.add(status_badges(badges))
        return surface(box)

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
        if close:
            close_button = icon_button('close', 'Close ' + title, on_press=self.session_closer(session.id))
            box.add(toga.Box(children=[*self.document_source_badges(session, self.session_opener(session.id)), button, close_button], style=Pack(direction=ROW)))
        else:
            box.add(toga.Box(children=[*self.document_source_badges(session, self.session_opener(session.id)), button],
                             style=Pack(direction=ROW)))
        return box

    def new_hub_document(self, widget=None, **kwargs):
        self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None:
            await restore
        return await self.adaptive.browser('documents').show_main_browser(
            'Local files', title='Open file')

    def refresh_hub(self, destination):
        if destination == 'files' and self.window_id == 'primary':
            self.show_cloud(present=False)
            view = self.folder_picker_or_error()
            view = self.adaptive.prepare(view, 'files', root=True)
            root = self.routes.roots['files']
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
