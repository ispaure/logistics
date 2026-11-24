"""Home screen construction and retained document overview."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .ui_metrics import TOUCH_TARGET
from .appearance import accessible_name, surface
from .control_icons import button_icons, icon_button
from .hub_controls import (DocumentThumbnails, HubSections, document_group, empty_document_row,
                           heading, retire_document_actions)


HOME_LIBRARY_SHORTCUTS = (
    ('Notes', 'notes_library', 'compose'), ('Books', 'books', 'books'), ('Comics', 'comics', 'file_tiles'),
)


def _home_state(hub, overview):
    """Compare visible content, excluding credential badges refreshed in place."""
    from copy import deepcopy
    from .document_sources import session_source
    rows = [(session.id, session.identity, session.id in hub.workspace.sessions,
             summary[0], summary[1], tuple(summary[2]),
             deepcopy(session_source(hub.app, session))) for session, summary in overview]
    return (rows, bool(hub.app.home_unlock_candidates()),
            getattr(getattr(hub.app, 'recovery_notice', None), 'text', ''), hub.workspace.error,
            getattr(hub.app, '_favourites_version', 0),
            tuple(record.get('document_cache_id') for record in
                  getattr(getattr(hub.app, 'cloud_client', None), 'package_records', ())
                  if record.get('document_cache_id')))


class HomeScreen:
    """Presentation methods share the HubController state and service contract."""
    def _home_overview(self):
        return self.recent_items()[:3]

    def build_home(self):
        if hasattr(self, 'home_sections'):
            retire_document_actions(self.home_sections.content)
            if self.home_sections.paired:
                retire_document_actions(self.home_sections.trailing)
        overview = self._home_overview()
        self._home_content_state = _home_state(self, overview)
        box = toga.Box(style=Pack(direction=COLUMN, margin=(8, 16, 16, 16)))
        self.app._home_status_row = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
        self.home_continue = None
        self.home_actions = None
        if self.app.routes.apple:
            self.home_actions = toga.Box(style=Pack(direction=ROW, align_items=CENTER))
            box.add(self.home_actions)
        self.home_content = box
        from .document_choices import available_choices
        primary = ()
        if available_choices(self.app):
            creator = icon_button('compose', 'New document', on_press=self.new_hub_document)
            creator._toolbar_symbol = 'plus'
            if self.home_actions is not None:
                from .appearance import action_button
                action_button(creator)
                creator._toolbar_group = 'home-documents'
                self.home_actions.add(creator)
            else:
                surface(creator, background='transparent', foreground='accent', eink_outlined=False)
            primary = (creator,)
        self._home_title = toga.Label('Home',
            style=Pack(font_size=30, font_weight='bold', height=40, margin_bottom=8))
        box.add(self._home_title)
        self._home_recents = toga.Box(style=Pack(direction=COLUMN))
        self._populate_home_overview(self._home_recents, overview)
        secondary = toga.Box(style=Pack(direction=COLUMN))
        from .favourites import populate
        secondary.add(self._home_section_header('Favourites', see_all=True))
        populate(self.app, secondary, heading=False, row_font=15, limit=2)
        shortcuts = toga.Box(style=Pack(direction=ROW, margin_bottom=12))
        for title, feature, glyph in HOME_LIBRARY_SHORTCUTS:
            if not self.app.feature_enabled(feature):
                continue

            def select_library(widget=None, *, library=title, **kwargs):
                return self.app.show_documents_hub(collection='Libraries', library=library)

            button = toga.Button(title, on_press=select_library,
                style=Pack(height=TOUCH_TARGET + 12, flex=1, font_size=13,
                           font_weight='bold', margin_left=8 if shortcuts.children else 0))
            button_icons(button, [(glyph, '')])
            shortcuts.add(surface(button, outlined=True, foreground='text'))
        if shortcuts.children:
            secondary.add(heading('Your libraries'), shortcuts)
        notice = getattr(getattr(self.app, 'recovery_notice', None), 'text', '')
        if notice:
            box.add(toga.Label(notice, style=Pack(font_size=13, margin_top=12)))
        if self.workspace.error:
            box.add(toga.Label(self.workspace.error, style=Pack(font_size=13, margin_top=12)))
        self.register_transfer_status(box)
        box.add(self._home_recents, secondary)
        from features.images.mobile.burst_camera import available, present
        if available(self.app):
            secondary.add(surface(toga.Button('Burst camera', on_press=lambda widget: present(self.app),
                style=Pack(height=TOUCH_TARGET)), background='transparent', foreground='accent',
                eink_outlined=False))
        self.home_sections = HubSections(box, secondary)
        self.home_sections._destination_body_heading = self._home_title
        self.home_sections._home_prefer_native = self.app.routes.apple
        self.home_sections._home_primary_actions = self.home_actions
        self.home_sections._home_primary_buttons = primary
        self.reflow_home()
        return self.home_sections

    def _populate_home_overview(self, box, overview):
        retire_document_actions(box)
        box.clear()
        previews = box._document_thumbnails = DocumentThumbnails(self.app)
        box.add(self._home_section_header('Recent', see_all=bool(overview)))
        self._home_recent_buttons = []
        for index, (session, summary) in enumerate(overview):
            featured = index == 0
            row = self.recent_row(session, summary, wrap_name=True, show_source=True,
                                  previews=previews, featured=featured)
            row.document_button.style.font_size = 18 if featured else 15
            row.document_button.style.font_weight = 'bold'
            self._home_recent_buttons.append(row.document_button)
            box.add(document_group([row], outlined=True))
        if not overview:
            box.add(empty_document_row('No recent items.'))
        previews.start()

    def _home_section_header(self, collection, *, see_all):
        title = heading(collection)
        title.style.margin_top = title.style.margin_bottom = 0
        header = toga.Box(children=[title, toga.Box(style=Pack(flex=1))],
                          style=Pack(direction=ROW, align_items=CENTER, height=TOUCH_TARGET))
        if see_all:
            def open_collection(widget=None, **kwargs):
                return self.app.show_documents_hub(collection=collection)

            button = surface(toga.Button('See all', on_press=open_collection,
                style=Pack(height=TOUCH_TARGET, margin_left=8)), radius=0, background='transparent',
                foreground='accent', eink_outlined=False)
            accessible_name(button, f'See all {collection.lower()} documents')
            header.add(button)
        return header

    def refresh_home_documents(self):
        if hasattr(self, 'home_sections'):
            overview = self._home_overview()
            self._populate_home_overview(self._home_recents, overview)
            self._home_content_state = None

    def reflow_home(self):
        sections = self.home_sections
        sections.reflow(self.app, 'home')
        top = 16
        if sections.paired and sections.style.direction == ROW:
            title = self._home_title.style
            top = sections.content.style.margin_top
            if self._home_title.parent is not None:
                top += title.height + title.margin_bottom
            if self.home_actions is not None and self.home_actions.parent is sections.content:
                top += max((button.style.height for button in self.home_actions.children), default=0)
                top += self.home_actions.style.margin_top + self.home_actions.style.margin_bottom
        sections.trailing_content.style.margin_top = top

    def new_hub_document(self, widget=None, **kwargs):
        return self.choose_document_type()

    async def open_hub_file(self, widget=None, **kwargs):
        destination = self.app.native_host.state.destination
        navigation = self.app.navigation_generation
        if (not self.app.active_host or self.app.native_host.state.destination != destination
                or self.app.navigation_generation != navigation):
            return False
        return await self.adaptive.browser(destination).show_main_browser('Local files', title='Browse files')
