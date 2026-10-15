"""Native launch panels and live document summaries over existing commands."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .hub_icons import icon
from commonUtils.ui.native.presentation import surface, list_button, template_icon


def heading(text):
    return toga.Label(text, style=Pack(font_size=19, font_weight='bold', margin_top=16, margin_bottom=8))


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
    def __init__(self, cards, width):
        super().__init__(style=Pack(direction=COLUMN))
        self.cards = cards
        self.columns = 0
        self.reflow(width)

    def reflow(self, width):
        columns = 3 if width >= 1100 else 2 if width >= 700 else 1
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
            self.add(row)


class HubUI:
    def build_home(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Logistics', style=Pack(font_size=24, font_weight='bold', margin_bottom=8)))
        box.add(toga.Label('Read. Write. Organize.', style=Pack(margin_bottom=8)))
        active = self.workspace.sessions.get(self.workspace.active)
        if active is not None:
            box.add(heading('Continue'))
            box.add(self.session_panel(active))
        box.add(heading('Your workspaces'))
        cards = []
        for title, detail, glyph, actions in (
            ('Files', '', 'files', [('Browse files', self.show_home_files)]),
            ('Text & Markdown', '', 'markdown', [('New document', self.new_hub_document), ('Open file…', self.open_hub_file)]),
            ('Books & Comics', '', 'books', [('Open library', self.show_library)]),
        ):
            cards.append(panel(title, detail, glyph, actions))
        self.home_panels = PanelGrid(cards, self.main_window.size.width)
        box.add(self.home_panels)
        box.add(toga.Box(children=[
            toga.Button('Open documents', on_press=self.show_documents_hub, style=Pack(height=44, flex=1)),
            toga.Button('LM Chat', on_press=self.show_chat, style=Pack(height=44, flex=1))], style=Pack(direction=ROW)))
        self.register_transfer_status(box)
        return toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))

    def build_documents_hub(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(toga.Label('Documents', style=Pack(font_size=24, margin_bottom=8)))
        box.add(toga.Label('Read, write and continue your work.', style=Pack(margin_bottom=12)))
        box.add(toga.Box(children=[
            toga.Button('New', on_press=self.new_hub_document, style=Pack(height=44, flex=1)),
            toga.Button('Open…', on_press=self.open_hub_file, style=Pack(height=44, flex=1)),
            toga.Button('Library', on_press=self.show_library, style=Pack(height=44, flex=1)),
            toga.Button('Chat', on_press=self.show_chat, style=Pack(height=44, flex=1))],
            style=Pack(direction=ROW, margin_bottom=8)))
        box.add(heading(f'Open documents · {len(self.workspace.sessions)}'))
        for session in list(self.workspace.sessions.values()):
            box.add(self.session_panel(session, close=True))
        if not self.workspace.sessions:
            box.add(toga.Label('Create or open a document to begin.'))
        box.add(heading(f'Stored documents · {len(self.labels)}'))
        for title, resource in self.labels.items():
            box.add(list_button(toga.Button(title, on_press=self.stored_document_opener(resource),
                                            style=Pack(height=48, margin_bottom=4))))
        if not self.labels:
            box.add(toga.Label('Your saved writing will appear here.'))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(margin_top=8)))
        self.register_transfer_status(box)
        return toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))

    def session_panel(self, session, *, close=False):
        title = session.title or 'Untitled document'
        kind = {'text': 'Text', 'markdown': 'Markdown', 'epub': 'EPUB book', 'comic': 'Comic'}.get(session.kind, 'Document')
        owner = self.text_views.get(session.id)
        dirty = owner.document.modified if owner is not None else session.dirty
        detail = kind + (' · Unsaved changes' if dirty else '')
        if session.provider == 'provider-session':
            detail += ' · Session only'
        if owner is not None and owner.document.conflict:
            detail += ' · File changed outside editor'
        if session.provider == 'managed-text' and owner is None:
            try:
                document = self.store.open(session.resource)
                title = session.title or document.name
                if document.modified:
                    detail += ' · Recovered draft'
            except (OSError, ValueError, KeyError, TypeError):
                detail += ' · Unavailable; retry to reopen'
        # One compact row per item; names are the primary navigation target.
        box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        box.add(toga.Label(detail, style=Pack(font_size=12)))
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
        previous = self.current
        self.new_document()
        if self.current is not previous:
            self.show_documents()

    async def open_hub_file(self, widget=None, **kwargs):
        await self.show_editor_open()

    def refresh_hub(self, destination):
        if destination == 'files' and self.window_id == 'primary':
            self.show_cloud(present=False)
            self.routes.trim('files', 0)
            root = self.routes.roots['files']
            for child in list(root.children):
                root.remove(child)
            root.add(self.build_folder_picker())
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
        for child in list(root.children):
            root.remove(child)
        root.add(view)
