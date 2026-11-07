"""Home screen construction and retained document overview."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .appearance import accessible_name, surface
from .hub_controls import HubSections, document_group, empty_document_row, heading


def _home_state(hub, overview):
    """Compare visible content, excluding credential badges refreshed in place."""
    from copy import deepcopy
    from .document_sources import session_source
    count, opened, recent = overview
    rows = [(session.id, session.identity, summary[0], summary[1], tuple(summary[2]),
             deepcopy(session_source(hub.app, session))) for session, summary in [*opened, *recent]]
    return (count, rows, bool(hub.app.home_unlock_candidates()),
            getattr(getattr(hub.app, 'recovery_notice', None), 'text', ''), hub.workspace.error,
            getattr(hub.app, '_favourites_version', 0),
            tuple(record.get('document_cache_id') for record in
                  getattr(getattr(hub.app, 'cloud_client', None), 'package_records', ())
                  if record.get('document_cache_id')))


class HomeScreen:
    """Presentation methods share the HubController state and service contract."""
    def _home_overview(self):
        sessions = self.open_document_sessions()
        opened = [(session, self.session_summary(session)) for session in sessions[:1]]
        recent = self.recent_items(excluding=[session.identity for session in sessions])
        return len(sessions), opened, recent[:1]

    def build_home(self):
        overview = self._home_overview()
        self._home_content_state = _home_state(self, overview)
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 16, 16)))
        status_row = toga.Box(
            style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12))
        self.app._home_status_row = status_row
        self.home_continue = None
        opener = surface(toga.Button('Open Document', on_press=self.open_hub_file,
                                     style=Pack(height=48, flex=1)),
                         background='alternate', foreground='accent', outlined=True)
        opener._toolbar_symbol = 'folder'
        opener._toolbar_group = 'home-documents'
        self.home_actions = toga.Box(children=[opener],
            style=Pack(direction=ROW, align_items=CENTER))
        self.home_content = box
        from .document_choices import available_choices
        if available_choices(self.app):
            creator = toga.Button('New Document', on_press=self.new_hub_document,
                                  style=Pack(height=48, flex=1, margin_left=8))
            creator._toolbar_symbol = 'plus'
            creator._toolbar_group = 'home-documents'
            self.home_actions.add(creator)
        overview_box = toga.Box(style=Pack(direction=COLUMN))
        self._populate_home_overview(overview_box, overview)
        favourites = toga.Box(style=Pack(direction=COLUMN))
        from .favourites import populate
        favourites.add(heading('Favourites'))
        populate(self.app, favourites, heading=False)
        box.add(self.home_actions, overview_box, favourites)
        notice = getattr(getattr(self.app, 'recovery_notice', None), 'text', '')
        if notice:
            box.add(toga.Label(notice, style=Pack(font_size=13, margin_top=12)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(font_size=13, margin_top=12)))
        self.register_transfer_status(box)
        from features.images.mobile.burst_camera import available, present
        if available(self.app):
            box.add(heading('Camera'))
            box.add(toga.Button('Burst camera', on_press=lambda widget: present(self.app),
                                style=Pack(height=48)))
        self.home_sections = HubSections(box, overview_box, before=favourites)
        self.home_sections._home_primary_actions = self.home_actions
        self.home_sections._home_primary_buttons = tuple(self.home_actions.children)
        self.reflow_home()
        return self.home_sections

    def _populate_home_overview(self, box, overview):
        count, opened, recent = overview
        box.clear()
        self._home_open_buttons = self._home_document_preview(
            box, 'Open now', opened, 'No open documents.', 'Open' if count > 1 else None)
        self._home_recent_buttons = self._home_document_preview(
            box, 'Recent', recent, 'No closed recent documents.', 'Recent' if recent else None)

    def _home_document_preview(self, box, title, items, empty, collection):
        header = toga.Box(children=[heading(title), toga.Box(style=Pack(flex=1))],
                          style=Pack(direction=ROW, align_items=CENTER))
        if collection:
            def see_all(widget=None, **kwargs):
                return self.app.show_documents_hub(collection=collection)

            button = surface(toga.Button('See all', on_press=see_all,
                                         style=Pack(height=44, margin_left=8)),
                             radius=0, background='transparent', foreground='accent',
                             outlined=False, eink_outlined=False)
            accessible_name(button, f'See all {collection.lower()} documents')
            header.add(button)
        box.add(header)
        rows = [self.recent_row(session, summary, show_kind=True) for session, summary in items]
        box.add(document_group(rows) if rows else empty_document_row(empty))
        return [row.document_button for row in rows]

    def refresh_home_documents(self):
        if hasattr(self, 'home_sections'):
            overview = self._home_overview()
            self._populate_home_overview(self.home_sections.trailing, overview)
            self._home_content_state = None

    def reflow_home(self):
        self.home_sections.reflow(self.app, 'home')

    def new_hub_document(self, widget=None, **kwargs):
        return self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        destination = self.app.native_host.state.destination
        navigation = self.app.navigation_generation
        if (not self.app.active_host or self.app.native_host.state.destination != destination
                or self.app.navigation_generation != navigation):
            return False
        return await self.adaptive.browser(destination).show_main_browser('Local files', title='Open file')
