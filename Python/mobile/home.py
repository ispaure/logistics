"""Home screen construction and retained recent-document sections."""
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .hub_controls import HubSections, document_group, empty_document_row, heading


def _home_state(hub, recent):
    """Compare visible content, excluding credential badges refreshed in place."""
    from copy import deepcopy
    from .document_sources import session_source
    rows = [(session.id, session.identity, summary[0], summary[1], tuple(summary[2]),
             session.id in hub.workspace.sessions, deepcopy(session_source(hub.app, session)))
            for session, summary in recent]
    return (rows, bool(hub.app.home_unlock_candidates()),
            getattr(getattr(hub.app, 'recovery_notice', None), 'text', ''), hub.workspace.error,
            getattr(hub.app, '_favourites_version', 0),
            tuple(record.get('document_cache_id') for record in
                  getattr(getattr(hub.app, 'cloud_client', None), 'package_records', ())
                  if record.get('document_cache_id')))


class HomeScreen:
    """Presentation methods share the HubController state and service contract."""
    def build_home(self):
        recent = self.recent_items()[:5]
        self._home_content_state = _home_state(self, recent)
        self._home_recent_buttons = []
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 16, 16)))
        status_row = toga.Box(
            style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12))
        self.app._home_status_row = status_row
        self.home_continue = None
        self.home_actions = toga.Box(children=[
            toga.Button('Open Document', on_press=self.open_hub_file, style=Pack(height=72, flex=1, margin_right=8)),
            toga.Button('New Document', on_press=self.new_hub_document, style=Pack(height=72, flex=1))],
            style=Pack(direction=ROW))
        self.home_content = box
        from .document_choices import available_choices
        if not available_choices(self.app):
            self.home_actions.remove(self.home_actions.children[-1])
        box.add(self.home_actions)
        recent_box = toga.Box(style=Pack(direction=COLUMN))
        self._populate_home_recent(recent_box, recent)
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
        self.home_sections._home_primary_actions = self.home_actions
        self.home_sections._home_primary_buttons = tuple(self.home_actions.children)
        self.reflow_home()
        return self.home_sections

    def _populate_home_recent(self, recent_box, recent):
        self._home_recent_buttons = []
        for child in list(recent_box.children):
            recent_box.remove(child)
        from .favourites import populate
        populate(self.app, recent_box)
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

    def refresh_home_documents(self):
        if hasattr(self, 'home_sections'):
            self._populate_home_recent(self.home_sections.trailing, self.recent_items()[:5])

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
