"""Native launch panels and live document summaries over existing commands."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .hub_icons import icon
from commonUtils.ui.native.presentation import list_button, template_icon
from .appearance import surface

DOCUMENT_TYPES = {'text': 'Text', 'markdown': 'Markdown', 'epub': 'EPUB books', 'comic': 'Comics'}


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


def home_surface(widget, *, hero=False):
    return surface(widget, radius=20 if hero else 16)


def panel(title, detail, glyph, actions):
    box = toga.Box(style=Pack(direction=COLUMN, padding=8, margin_bottom=8))
    box.add(toga.Box(children=[
        template_icon(toga.ImageView(icon(glyph), style=Pack(width=24, height=24, margin_right=8))),
        toga.Label(title, style=Pack(flex=1, font_size=18, font_weight='bold'))],
        style=Pack(direction=ROW, margin_bottom=8)))
    if detail:
        box.add(toga.Label(detail, style=Pack(font_size=12, margin_bottom=4)))
    buttons = toga.Box(style=Pack(direction=ROW))
    for label, action in actions:
        buttons.add(toga.Button(label, on_press=action, style=Pack(height=44, flex=1)))
    box.add(buttons)
    return surface(box)


class PanelGrid(toga.Box):
    def __init__(self, cards, width, *, minimum_columns=1):
        super().__init__(style=Pack(direction=COLUMN))
        self.cards = cards
        self.columns = 0
        self.minimum_columns = minimum_columns
        self.reflow(width)

    def reflow(self, width):
        columns = max(self.minimum_columns, 3 if width >= 1100 else 2 if width >= 700 else 1)
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
            for _ in range(columns - len(row.children) if self.minimum_columns > 1 else 0):
                row.add(toga.Box(style=Pack(flex=1)))
            self.add(row)


class HubUI:
    def build_home(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Welcome to Logistics', style=Pack(font_size=28, font_weight='bold', margin_bottom=20)))
        active = self.workspace.sessions.get(self.workspace.active)
        if active is not None:
            title, kind, details = self.session_summary(active)
            hero = toga.Box(style=Pack(direction=COLUMN, margin_bottom=12))
            hero_content = toga.Box(style=Pack(direction=COLUMN, margin=18))
            hero.add(hero_content)
            hero_content.add(toga.Label('PICK UP WHERE YOU LEFT OFF', style=Pack(font_size=11, margin_bottom=12)))
            from textwrap import fill
            hero_content.add(toga.Label(fill(title, width=26), style=Pack(font_size=22, font_weight='bold', margin_bottom=8)))
            hero_content.add(toga.Label(' · '.join([DOCUMENT_TYPES.get(kind, 'Document'), *details]),
                                style=Pack(font_size=12, margin_bottom=12)))
            self.home_continue_button = toga.Button('Continue →', on_press=self.session_opener(active.id),
                                style=Pack(height=48))
            hero_content.add(self.home_continue_button)
            box.add(home_surface(hero, hero=True))
            self.home_continue = hero
        else:
            box.add(toga.Label('Read. Write. Organize.', style=Pack(margin_bottom=12)))
        box.add(toga.Box(children=[
            toga.Button('+ New document', on_press=self.new_hub_document, style=Pack(height=48, flex=1, margin_right=8)),
            toga.Button('Open file…', on_press=self.open_hub_file, style=Pack(height=48, flex=1))],
            style=Pack(direction=ROW)))
        box.add(heading('Your spaces'))
        spaces = toga.Box(style=Pack(direction=COLUMN))
        for title, subtitle, glyph, action in (
            ('Folder Hub', 'Your folders · browse, pull & push', 'folder_hub', self.show_home_files),
            ('Books & Comics', 'Your library, ready to read', 'books', self.show_library),
        ):
            text = toga.Box(children=[
                list_button(toga.Button(title, on_press=action, style=Pack(height=44))),
                toga.Label(subtitle, style=Pack(font_size=12, margin_left=8, margin_right=8))],
                style=Pack(direction=COLUMN, flex=1))
            item = toga.Box(children=[
                template_icon(toga.ImageView(icon(glyph), style=Pack(width=28, height=28, margin_right=12))),
                text], style=Pack(direction=ROW, align_items=CENTER, margin=16, margin_bottom=12))
            spaces.add(home_surface(item))
        box.add(spaces)
        box.add(toga.Box(children=[
            toga.Button('Open documents', on_press=self.show_documents_hub, style=Pack(height=44, flex=1)),
            toga.Button('LM Chat →', on_press=self.show_chat, style=Pack(height=44, flex=1))],
            style=Pack(direction=ROW, margin_top=8)))
        self.register_transfer_status(box)
        return toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))

    def build_documents_hub(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Documents', style=Pack(font_size=24, margin_bottom=8)))
        box.add(toga.Label('Read, write and continue your work.', style=Pack(margin_bottom=12)))
        box.add(toga.Box(children=[
            toga.Button('New', on_press=self.new_hub_document, style=Pack(height=44, flex=1)),
            toga.Button('Open…', on_press=self.open_hub_file, style=Pack(height=44, flex=1))],
            style=Pack(direction=ROW, margin_bottom=8)))
        launchers = []
        for title, detail, glyph, extension in (
            ('Text Editor', 'Edit plain text and code files.', 'documents', 'txt'),
            ('Markdown Editor', 'Write and preview formatted notes.', 'markdown', 'md'),
            ('EPUB Reader', 'Read books and resume your progress.', 'books', None),
            ('Comic Reader', 'Read comics and image archives.', 'books', None),
            ('Archives', 'Browse archive files.', 'files', None),
        ):
            actions = []
            if extension:
                def create(widget=None, selected=extension, **kwargs):
                    self.create_chosen_document(selected)
                actions.append(('New', create))
            async def open_category(widget=None, selected=title, **kwargs):
                await self.open_document_category(selected)
            actions.append(('Open…', open_category))
            launchers.append(panel(title, detail, glyph, actions))
        self.document_launchers = PanelGrid(launchers, self.main_window.size.width)
        box.add(self.document_launchers)
        box.add(heading(f'Open documents · {len(self.workspace.sessions)}'))
        sessions = []
        self.document_grids = []
        for session in self.workspace.sessions.values():
            summary = self.session_summary(session)
            sessions.append((summary[1], session, summary))
        for title, group in document_groups(sessions):
            box.add(heading(f'{title} · {len(group)}'))
            if self.preferences.values['document_card_overview'] == 'true':
                grid = PanelGrid([self.session_card(session, summary) for _, session, summary in group],
                                 self.main_window.size.width, minimum_columns=2)
                self.document_grids.append(grid)
                box.add(grid)
            else:
                for kind, session, summary in group:
                    box.add(self.session_panel(session, close=True, summary=summary, show_kind=False))
        if not self.workspace.sessions:
            box.add(toga.Label('Create or open a document to begin.'))
        box.add(heading(f'Stored documents · {len(self.labels)}'))
        stored = [(self.stored_document_kinds[resource], title, resource) for title, resource in self.labels.items()]
        for title, group in document_groups(stored):
            box.add(heading(f'{title} · {len(group)}'))
            for kind, name, resource in group:
                box.add(list_button(toga.Button(name, on_press=self.stored_document_opener(resource),
                                                style=Pack(height=48, margin_bottom=4))))
        if not self.labels:
            box.add(toga.Label('Your saved writing will appear here.'))
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

    def session_card(self, session, summary):
        """A lightweight overview; never mount live editors or private readers."""
        title, kind, details = summary
        box = toga.Box(style=Pack(direction=COLUMN, padding=8, margin_bottom=10))
        box.session_id = session.id
        box.add(toga.Box(children=[
            list_button(toga.Button(title, on_press=self.session_opener(session.id),
                                    style=Pack(flex=1, height=44))),
            toga.Button('×', on_press=self.session_closer(session.id), style=Pack(width=44, height=44))],
            style=Pack(direction=ROW)))
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
        excerpt = '\n'.join(line[:24] for line in preview[:600].splitlines()[:6])
        box.add(toga.Label(excerpt or DOCUMENT_TYPES.get(kind, 'Document'),
                           style=Pack(height=120, font_size=12, margin_top=8, margin_bottom=8)))
        if details:
            box.add(toga.Label('\n'.join(details), style=Pack(font_size=12)))
        caption = 'Current document' if self.workspace.active == session.id else 'Resume document'
        box.add(toga.Button(caption, on_press=self.session_opener(session.id), style=Pack(height=44)))
        return surface(box)

    def session_summary(self, session):
        """Resolve display metadata from its owner; workspace manifests omit names."""
        title = session.title or 'Untitled document'
        kind = session.kind
        owner = self.text_views.get(session.id)
        dirty = owner.document.modified if owner is not None else session.dirty
        details = ['Unsaved changes'] if dirty else []
        if owner is not None:
            title = owner.document.name
            kind = text_document_kind(title)
        if session.provider == 'provider-session':
            details.append('Session only')
        if owner is not None and owner.document.conflict:
            details.append('File changed outside editor')
        if session.provider == 'managed-text' and owner is None:
            try:
                document = self.store.open(session.resource)
                title = document.name
                kind = text_document_kind(title)
                if document.modified:
                    details.append('Recovered draft')
            except (OSError, ValueError, KeyError, TypeError):
                details.append('Unavailable; retry to reopen')
        elif session.provider == 'library':
            try:
                record = self.reader_manager().catalog.library_store.read_record(session.resource)[0]
                title, kind = record['name'], record['kind']
            except (OSError, ValueError, KeyError, TypeError):
                details.append('Unavailable; retry to reopen')
        return title, kind, details

    def session_panel(self, session, *, close=False, summary=None, show_kind=True):
        title, kind, details = summary if summary is not None else self.session_summary(session)
        if show_kind:
            details = [DOCUMENT_TYPES.get(kind, 'Document'), *details]
        # One compact row per item; names are the primary navigation target.
        box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        if details:
            box.add(toga.Label(' · '.join(details), style=Pack(font_size=12)))
        button = list_button(toga.Button(title, on_press=self.session_opener(session.id), style=Pack(height=48, flex=1)))
        if close:
            from .action_menu import FeatureCommands
            more = toga.Button('•••', style=Pack(width=44, height=48))
            box.commands = FeatureCommands(more, self,
                [('Close document', self.session_closer(session.id))], self.session_closer(session.id))
            box.add(toga.Box(children=[button, more], style=Pack(direction=ROW)))
        else:
            box.add(button)
        return box

    def new_hub_document(self, widget=None, **kwargs):
        self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        await self.show_editor_open()

    def refresh_hub(self, destination):
        if destination == 'files' and self.window_id == 'primary':
            self.show_cloud(present=False)
            self.routes.trim('files', 0)
            root = self.routes.roots['files']
            for child in list(root.children):
                root.remove(child)
            view = self.build_folder_picker()
            view = self.adaptive.prepare(view, 'files', root=True)
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
