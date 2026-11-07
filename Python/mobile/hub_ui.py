"""Shared session summaries and refresh coordination for Home and Documents."""
from pathlib import Path

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER

from .appearance import list_button
from .control_icons import icon_button, button_icons
from .documents_hub import DocumentsHub
from .home import HomeScreen, _home_state
from .hub_controls import (
    DOCUMENT_TYPES as DOCUMENT_TYPES,
    HubSections as HubSections,
    PanelGrid as PanelGrid,
    document_group as document_group,
    document_groups as document_groups,
    document_list as document_list,
    empty_document_row as empty_document_row,
    heading as heading,
    panel as panel,
    status_badges as status_badges,
    text_document_kind as text_document_kind,
)
from .recent_documents import MAX_RECENT


def session_identities(session, history):
    identities = {session.identity}
    source = getattr(session, 'history_source', None) or getattr(session, 'cache_source', None)
    if source is not None:
        identities.add(('file-reference', history.reference_id(source)))
    return identities


class HubUI(HomeScreen, DocumentsHub):
    def reflow_layout(self, frame):
        if hasattr(self, 'home_sections') and self.main_window.content is self.app.native_host.root:
            self.reflow_home()
        if hasattr(self, 'documents_sections'):
            self.reflow_documents_hub()
        if hasattr(self, 'document_launchers'):
            self.document_launchers.reflow(frame.width)
        for grid in getattr(self, 'document_grids', ()):
            grid.reflow(frame.width)

    def session_visible(self, session):
        from services.mobile_features import session_enabled
        if not session_enabled(self.app.preferences, session):
            return False
        if session.provider == 'credential-reference':
            return getattr(session, 'cache_id', None) in self.app.credential_document_lists.states
        if session.provider == 'provider-session':
            manager = getattr(self, 'private_sessions', None)
            return manager is not None and manager.available(session.id)
        return True

    def open_document_sessions(self):
        sessions = [session for session in self.workspace.sessions.values() if self.session_visible(session)]
        return sorted(sessions, key=lambda session: session.id != self.workspace.active)

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
        notes = getattr(self.app, 'vault_browser', None)
        if notes is not None and notes.valid():
            history = sorted([*getattr(notes, 'recent_notes', ()), *history],
                             key=lambda session: getattr(session, 'opened_at', 0), reverse=True)
        recorded = {session.identity for session in history}
        # Unrecorded session-only work is still discoverable without persisting it.
        missing = [session for session in reversed(list(self.workspace.sessions.values()))
                   if self.session_visible(session)
                   and not session_identities(session, self.recent_documents) & recorded]
        active_missing = [session for session in missing if session.id == self.workspace.active]
        other_missing = [session for session in missing if session.id != self.workspace.active]
        items, seen = [], set()
        for entry in [*active_missing, *history, *other_missing]:
            session = (entry if getattr(entry, 'history_opener', None) else live.get(entry.identity, entry))
            if session.id not in self.workspace.sessions and session.provider == 'file-reference':
                from .document_sources import local_reference_available
                if not local_reference_available(self.app, session.source):
                    continue
            from services.mobile_features import session_enabled
            if not session_enabled(self.app.preferences, session):
                continue
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
            opener = getattr(session, 'history_opener', None)
            if opener is not None and opener.get('kind') == 'notes':
                from .favourites import reopen as reopen_reference
                return await reopen_reference(self.app, dict(source=session.source, opener=opener,
                                                            title=session.title), error_title='Open recent note')
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
                    if session.kind == 'video':
                        await reopen_file(self.app, source, kind='video')
                    else:
                        await reopen_file(self.app, source)
                except (OSError, ValueError, KeyError) as error:
                    await self.main_window.dialog(toga.InfoDialog('Could not open file', str(error)))
                    self.refresh_document_list()
                    self.refresh_hub(self.app.native_host.state.destination)
            elif session.provider == 'notebook':
                from features.notebooks.mobile.documents import open_notebook
                await open_notebook(self.app, key=session.resource)
            elif session.provider == 'library':
                await self.open_book(session.resource)
            elif self.open_document(session.resource):
                self.show_documents(resume=True)
        return reopen

    def document_row_menu(self, session):
        from .action_menu import FeatureCommands
        from .document_sources import folder_location, ordinary_browser_location, show_folder_location

        app = self.app
        try:
            location = folder_location(app, session)
        except (OSError, ValueError):
            return []
        if location is None:
            return []
        actions = [('Document location', lambda: show_folder_location(app, location))]
        path, provider = location.get('path'), location.get('provider')
        if path is None and provider is not None and not provider.private:
            path = Path(provider.root) / location['key']
        matching = ordinary_browser_location(app, path) if path is not None else None
        if matching:
            label, provider, row = matching
            for title, callback in app.file_item_commands(context=(provider, label, row)):
                async def invoke(target=callback):
                    import inspect

                    async def selected(browser, entry):
                        if browser is not app.file_browser or entry.payload['path'] != row['path']:
                            return False
                        if (target == app.delete_file
                                and app.file_provider.entry(row['path'])['revision'] != row['revision']):
                            await app.main_window.dialog(toga.InfoDialog(
                                'File changed', 'Review the current file before deleting it.'))
                            return False
                        result = target()
                        return await result if inspect.isawaitable(result) else result

                    return await show_folder_location(app, location, on_selected=selected)
                actions.append((title, invoke))
        elif 'remote' in location:
            async def remote_actions():
                async def selected(browser, entry):
                    if browser.on_item_actions is not None:
                        browser.on_item_actions(entry.payload)
                return await show_folder_location(app, location, on_selected=selected)
            actions.append(('File actions…', remote_actions))
        button = icon_button('overflow', 'Document actions')
        button.document_actions = FeatureCommands(button, app, actions, None, document=True)
        return [button]

    def recent_row(self, session, summary, *, show_kind=False):
        title, kind, details = summary
        if show_kind:
            details = [DOCUMENT_TYPES.get(kind, 'Document'), *details]
        row = toga.Box(style=Pack(direction=COLUMN, margin_bottom=8))
        opener = self.recent_opener(session)
        from .browser_ui import middle_filename
        name = list_button(toga.Button(title, on_press=opener, style=Pack(height=48, flex=1)))
        middle_filename(name)
        self.document_button_icons(name, session)
        row.document_button = name
        row.add(toga.Box(children=[name, *self.document_row_menu(session)],
            style=Pack(direction=ROW, align_items=CENTER)))
        currently_open = session.id in self.workspace.sessions
        if currently_open or details:
            row.add(status_badges(details, currently_open=currently_open,
                                  icon_count=len(getattr(name, 'leading_icons', ()))))
        return row

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
        elif session.provider == 'notebook' and not getattr(session, 'history_source', None):
            from features.notebooks.mobile.documents import repository
            names = dict(repository(self.app).list())
            title = names.get(session.resource, title)
            if session.resource not in names:
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
        buttons = [button, *self.document_row_menu(session)]
        if close:
            close_button = icon_button('close', 'Close ' + title, on_press=self.session_closer(session.id))
            box.close_button = close_button
            buttons.append(close_button)
        box.add(toga.Box(children=buttons, style=Pack(direction=ROW)))
        if details:
            box.add(status_badges(details, icon_count=len(getattr(button, 'leading_icons', ()))))
        return box

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
            overview = self._home_overview()
            if _home_state(self, overview) == getattr(self, '_home_content_state', None):
                _, opened, recent = overview
                for button, (session, _) in zip(
                        [*self._home_open_buttons, *self._home_recent_buttons], [*opened, *recent]):
                    self.document_button_icons(button, session)
                return
        root = self.routes.roots[destination]
        view = self.build_home() if destination == 'home' else self.build_documents_hub()
        view = self.adaptive.prepare(view, destination, root=True)
        for child in list(root.children):
            root.remove(child)
        root.add(view)
