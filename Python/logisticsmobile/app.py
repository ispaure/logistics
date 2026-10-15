"""Small native mobile text/Markdown prototype with app-private recovery."""
import asyncio
from pathlib import Path
from uuid import uuid4
import weakref
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import DocumentStore, document_name
from .preferences import Preferences
from .preview import markdown_preview
from .reader_sessions import ReaderWorkspace
from .chat_ui import ChatUI
from .cloud_ui import CloudUI
from commonUtils.ui.native.navigation import NativeNavigationHost
from commonUtils.ui.native.routes import Routes
from .navigation import DESTINATION_ITEMS
from .workspace import Workspace, MAX_SESSIONS
from .mirror_ui import MirrorUI
from .editors import TextEditorView
from .workspace_navigation import WorkspaceNavigation as AdaptiveWorkspace
from .pull_jobs_ui import PullJobsUI
from .locations_ui import LocationsUI
from .folder_hub_ui import FolderHubUI
from .hub_ui import HubUI, text_document_kind

_active_hosts = weakref.WeakValueDictionary()


class LogisticsMobile(HubUI, FolderHubUI, LocationsUI, MirrorUI, PullJobsUI, ReaderWorkspace, ChatUI, CloudUI, toga.App):
    storage_root = None  # Host tests may supply a private fixture directory.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            from .window_scenes import SceneManager
            self.window_id = 'primary'
            self.scene_manager = SceneManager(self, prepare_only=True)
        # Install before Android starts cooperative dispatch or registers Java
        # wake-up callbacks. Desktop/iOS loops lack this method and are unchanged.
        from commonUtils.ui.native.event_loop import bind_cooperative_loop
        bind_cooperative_loop(self.loop)

    def startup(self):
        from .appearance import install_appearance
        install_appearance(self)
        root = Path(self.storage_root or self.paths.data)
        self.private_root = root
        host_identity = str(root.resolve()) + ':' + getattr(self, 'window_id', 'primary')
        previous_host = _active_hosts.get(host_identity)
        if previous_host is not None:
            memory = getattr(previous_host, 'memory_pressure', None)
            if memory is not None:
                memory.dispose()
            previous_host.active_host = False
            for session in previous_host.workspace.sessions.values():
                previous_host.workspace.invalidate(session.id)
            cancelled = getattr(previous_host, '_crypt_cancel', None)
            if cancelled is not None:
                cancelled.set()
                client = getattr(previous_host, 'cloud_client', None)
                if client is not None:
                    client.cancel()
        self.active_host = True
        self.navigation_generation = 0
        _active_hosts[host_identity] = self
        workspace_root = getattr(self, 'workspace_root', root)
        self.preferences = Preferences(workspace_root)
        self.store = DocumentStore(root / 'Documents')
        from .recent_documents import RecentDocuments
        self.recent_documents = RecentDocuments(workspace_root)
        self.workspace = Workspace(workspace_root)
        if self.preferences.values['clear_unmodified_documents_on_restart'] == 'true':
            self.clear_restored_documents()
        restored_reader = self.workspace.sessions.get(self.workspace.active)
        self.pending_reader_restore = None
        if hasattr(self, 'scene_manager'):
            self.scene_manager.owners.attach(self.window_id, self)
            self.scene_manager.bind_workspace(self.window_id, self)
        self.text_views = {}
        self.current = None
        self.loading = True
        self.labels = {}
        self.editor_view = TextEditorView(self)
        self.editor_view.bind()
        self.native_host = NativeNavigationHost(DESTINATION_ITEMS, on_select=self.select_destination)
        self.routes = Routes(self.native_host, guard=self.checkpoint, changed=self.route_changed,
                             intent=self.mark_navigation)
        self.adaptive = AdaptiveWorkspace(self)
        self.routes.on_render = self.adaptive.render
        self.navigation = self.native_host.root
        self.body = self.routes.body()
        self.main_window = getattr(self, 'window_class', toga.MainWindow)(title='Logistics', content=self.navigation,
                                           on_lose_focus=self.checkpoint, on_resize=self.resize_workspace)
        if not hasattr(self, 'scene_manager'):
            from .window_scenes import install_scenes
            install_scenes(self)
        self.scene_manager.activate()
        self.on_exit = self.exit_app
        self.refresh_documents()
        self.loading = False
        if self.preferences.values['clear_unmodified_documents_on_restart'] == 'true':
            active = self.workspace.sessions.get(self.workspace.active)
            if active is not None and active.provider == 'managed-text':
                self.open_document(active.resource)
        elif self.labels:
            key = self.preferences.values['last_document']
            active = self.workspace.sessions.get(self.workspace.active)
            if active is not None and active.provider == 'managed-text':
                key = active.resource
            if self.preferences.values['restore_last_document'] != 'true' or key not in self.labels.values():
                key = next(iter(self.labels.values()))
            self.open_document(key)
        self.show_documents_hub()
        self.show_settings()
        self.show_folder_picker(initialize=False)
        self.show_home()
        self.save_workspace(capture=False)
        self.main_window.show()
        self.native_host.install(self.main_window)
        from .navigation import install_folder_hub_icon, install_apple_selection
        install_folder_hub_icon(self.native_host)
        install_apple_selection(self)
        self.routes.install()
        self.refresh_native_theme()
        self.adaptive.install()
        from commonUtils.ui.native.memory import MemoryPressure
        self.memory_pressure = MemoryPressure(self, on_pressure=self.release_disposable_resources,
                                              on_configuration=self.native_configuration_changed)
        if restored_reader is not None and restored_reader.provider == 'library':
            if self.preferences.values['restore_last_document'] == 'true':
                self.pending_reader_restore = restored_reader.id
                self.workspace.active = restored_reader.id
            elif self.workspace.active == restored_reader.id:
                self.workspace.active = None
            self.save_workspace()

        # Explicit local developer launch only; ordinary launches do no capture.
        import os
        if os.environ.get('LOGISTICS_COMIC_LAYOUT_CHECK') == '1' and type(self.main_window._impl).__module__.startswith('toga_iOS.'):
            from .comic_layout_check import run
            self.loop.create_task(run(self))

    def select_destination(self, destination):
        if not self.checkpoint():
            return False
        if destination != self.native_host.state.destination:
            self.mark_navigation()
        self.save_workspace()
        if destination == 'chat' and not self.routes.screens['chat']:
            self.show_chat(present=False)
        self.refresh_hub(destination)
        adaptive = getattr(self, 'adaptive', None)
        if (destination == 'documents' and adaptive is not None and adaptive.split is not None
                and adaptive.in_detail and adaptive.detail_routes):
            self.body = adaptive.detail_routes[-1][1]
        else:
            self.body = self.routes.body(destination)
        if adaptive is not None:
            # Tab selection callbacks run before the host commits destination.
            # Render the new root and its toolbar against the selected tab.
            adaptive.render(destination=destination)
        from .reader_chrome import sync_comic_chrome
        sync_comic_chrome(self, self.body)
        # Material selection is reported before the shared destination commits.
        if self.routes.back_callback is not None:
            self.routes.back_callback.setEnabled(bool(self.routes.screens[destination]))
        key = self.pending_reader_restore
        if destination == 'documents' and key is not None:
            self.pending_reader_restore = None
            session = self.workspace.sessions.get(key)
            if session is not None and self.workspace.active == key:
                self.loop.create_task(self.resume_library_session(session))
        return True

    def mark_navigation(self):
        self.navigation_generation += 1

    def route_changed(self, body):
        self.body = body
        # UIKit Back/swipe callbacks also need to restore the retained toolbar.
        self.loop.call_soon(self.adaptive.render)
        private = getattr(self, 'private_sessions', None)
        if private is not None and getattr(self, 'files_view', None) in body.children:
            # Native Back does not call show_view. Apply the same hidden private
            # preview/image cleanup while retaining drafts and their sessions.
            private.suspend()
        from .reader_chrome import sync_comic_chrome
        sync_comic_chrome(self, body)
        if (hasattr(self, 'editor_view') and self.editor_view.session is not None
                and self.document_view in body.children):
            self.editor_view.session.view['markdown_mode'] = 'edit'

    def resize_workspace(self, widget=None, *args, **kwargs):
        self.adaptive.render()
        if hasattr(self, 'home_panels') and self.main_window.content is self.native_host.root:
            self.home_panels.reflow(self.main_window.size.width)
        if hasattr(self, 'document_launchers'):
            self.document_launchers.reflow(self.main_window.size.width)
        for grid in getattr(self, 'document_grids', []):
            grid.reflow(self.main_window.size.width)
        for owner in self.text_views.values():
            owner.apply_split(self.main_window.size.width)

    def refresh_native_theme(self):
        from .appearance import refresh_appearance
        refresh_appearance(self)

    def show_view(self, view, *, checkpoint=True, destination=None, route=None, title='', root=False):
        if checkpoint and not self.checkpoint():
            return False
        self.mark_navigation()
        target = destination or self.native_host.state.destination
        view = self.adaptive.prepare(view, target, route=route, root=root)
        private = getattr(self, 'private_sessions', None)
        if private is not None:
            owner = private.active
            if owner is None or view not in (getattr(owner, 'crypt_view', None), getattr(owner, 'crypt_metadata_view', None)):
                private.suspend()
        if self.adaptive.split is not None and target == 'documents' and not root:
            self.native_host.activate('documents')
            self.adaptive.present(view, route=route, title=title)
            from .reader_chrome import sync_comic_chrome
            sync_comic_chrome(self, self.body)
            return True
        self.routes.show(view, destination=destination, route=route, title=title, root=root)
        if root and target == 'documents':
            self.adaptive.show_list()
        return True

    def show_home(self, widget=None, **kwargs):
        self.show_view(self.build_home(), destination='home', root=True)

    def show_locations(self, widget=None, **kwargs):
        self.show_folder_picker()

    async def show_local_location(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None and not restore.done():
            await restore
        await self.show_files()

    async def show_home_files(self, widget=None, **kwargs):
        # A local shortcut must not wait for credentials or reuse a previous
        # remote/private location and its search filter.
        self.show_cloud(present=False)
        self.show_locations()

    def show_documents_hub(self, widget=None, **kwargs):
        self.show_view(self.build_documents_hub(), destination='documents', root=True)

    def stored_document_opener(self, resource):
        def activate(widget=None, **kwargs):
            if self.checkpoint():
                if self.open_document(resource):
                    self.show_documents(resume=True)
        return activate

    def session_opener(self, key):
        def activate(widget=None, **kwargs):
            session = self.workspace.sessions.get(key)
            if session is not None and self.checkpoint():
                self.adaptive.focus_session(key)
                if session.provider == 'library':
                    self.loop.create_task(self.resume_library_session(session))
                elif session.provider == 'provider-session':
                    self.provider_sessions().activate(session.id)
                else:
                    if self.open_document(session.resource):
                        self.show_documents(resume=True)
                    else:
                        self.show_unavailable_session(key)
        return activate

    async def resume_library_session(self, session):
        try:
            await self.open_book(session.resource)
        except (OSError, ValueError, KeyError, TypeError):
            if (session.id in self.workspace.sessions and self.workspace.active == session.id
                    and self.native_host.state.destination == 'documents'):
                self.show_unavailable_session(session.id)

    def show_unavailable_session(self, key):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        box.add(toga.Label('Document unavailable', style=Pack(font_size=18)))
        box.add(toga.Label('Its stored data could not be opened.\nExisting files have been preserved.'))
        box.add(toga.Button('Try again', on_press=self.session_opener(key), style=Pack(height=44)))
        box.add(toga.Button('Remove from open documents', on_press=self.session_closer(key), style=Pack(height=44)))
        box.add(toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=44)))
        self.show_view(box, destination='documents', route='unavailable:' + key, title='Unavailable document')

    def session_closer(self, key):
        def close(widget=None, **kwargs):
            self.request_close_session(key)
        return close

    def request_close_session(self, key):
        private = self.provider_sessions().controllers.get(key)
        if private is not None and private.private_dirty():
            return self.request_provider_close(private)
        owner = self.text_views.get(key)
        if owner is None or not owner.document.modified:
            return self.close_session(key)
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        from .cloud_ui import import_hint
        box.add(toga.Label(import_hint('Close ' + owner.document.name), style=Pack(font_size=18)))
        box.add(toga.Label('Choose what to do with\nyour unsaved changes.', style=Pack(margin_bottom=12)))
        def choose(choice):
            def action(widget=None, **kwargs):
                self.close_session(key, choice=choice)
            return action
        box.add(toga.Button('Save and close', on_press=choose('save'), style=Pack(height=44)))
        if not getattr(owner.document, 'private', False):
            box.add(toga.Button('Keep draft and close', on_press=choose('keep'), style=Pack(height=44)))
        box.add(toga.Button('Discard changes and close', on_press=choose('discard'), style=Pack(height=44)))
        box.add(toga.Button('Cancel', on_press=lambda widget, **kw: self.cancel_close_session(key), style=Pack(height=44)))
        self.close_notice = toga.Label('', style=Pack(margin_top=8))
        box.add(self.close_notice)
        return self.show_view(box, checkpoint=False, route='close:' + key, destination='documents', title='Close document')

    def cancel_close_session(self, key):
        owner = self.text_views.get(key)
        if owner is not None:
            owner.bind()
            self.workspace.activate(key)
            self.show_documents()

    def close_session(self, key, *, choice='keep'):
        if key not in self.workspace.sessions:
            return False
        if choice == 'cancel':
            return False
        if choice not in ('keep', 'save', 'discard'):
            raise ValueError('Unsupported close action.')
        if self.workspace.sessions[key].provider == 'provider-session':
            return self.provider_sessions().close(key, discard=choice == 'discard')
        if self.workspace.sessions[key].provider == 'library':
            return self.reader_manager().close(key)
        owner = self.text_views.get(key)
        def guard(session):
            if owner is None:
                return True
            if choice == 'keep' and getattr(owner.document, 'private', False) and owner.document.modified:
                owner.status.text = 'Save this session-only draft before closing.'
                return False
            try:
                if choice == 'save':
                    self.store.save(owner.document)
                elif choice == 'discard':
                    self.store.discard(owner.document)
                else:
                    self.store.checkpoint(owner.document)
                return True
            except (OSError, ValueError) as error:
                owner.status.text = 'Could not close; edits retained: ' + str(error)
                if hasattr(self, 'close_notice'):
                    self.close_notice.text = owner.status.text
                return False
        was_current = owner is self.editor_view
        if not self.workspace.close(key, guard=guard):
            return False
        self.text_views.pop(key, None)
        if owner is not None:
            owner.dispose()
        if was_current:
            self.current = None
            remaining = self.workspace.sessions.get(self.workspace.active)
            if remaining is not None and remaining.provider == 'managed-text':
                self.open_document(remaining.resource)
            else:
                self.editor_view = TextEditorView(self)
                self.editor_view.bind()
        self.save_workspace()
        self.refresh_documents()
        self.show_documents_hub()
        if was_current and self.adaptive.split is not None:
            if self.current is not None:
                self.adaptive.present(self.document_view, route='editor', title=self.current.name if self.current else 'New document')
                self.adaptive.show_list()
            else:
                self.adaptive.clear_details()
        return True

    def save_workspace(self, *, capture=True):
        if not self.active_host:
            return
        if capture:
            self.editor_view.capture()
        for view in self.text_views.values():
            view.session.transient = bool(getattr(view.document, 'private', False))
        try:
            self.workspace.save()
            self.recent_documents.remember(self.workspace.sessions.get(self.workspace.active))
            self.scene_manager.save_destination(self)
        except (OSError, ValueError) as error:
            self.recovery_notice.text = str(error)

    def show_documents(self, widget=None, *, resume=False, destination='documents', **kwargs):
        if self.current is None:
            self.new_document()
        if self.current is None:
            return False
        self.pending_reader_restore = None
        self.workspace.activate(self.editor_view.session.id)
        preview = resume and self.editor_view.session.view.get('markdown_mode') == 'preview'
        self.editor_view.session.view['markdown_mode'] = 'edit'
        self.show_view(self.document_view, destination=destination, route='editor', title=self.current.name if self.current else 'New document')
        if preview:
            return self.show_preview()

    def show_editor_actions(self, owner):
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        for title, action in owner.actions.actions:
            def command(widget=None, target=action, **kwargs):
                owner.actions.invoke(target)
            box.add(toga.Button(title, on_press=command, style=Pack(height=44)))
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)), route='actions', title='Document actions')

    def show_settings(self, widget=None, **kwargs):
        from .hub_ui import heading
        box = toga.Box(style=Pack(direction=COLUMN, margin=16))
        box.add(heading('App'))
        self.document_cards_choice = toga.Switch('Document card overview',
            value=self.preferences.values['document_card_overview'] == 'true', style=Pack(height=44))
        box.add(self.document_cards_choice)
        box.add(toga.Label('Show open documents as preview cards.\nTurn off to use the grouped list.', style=Pack(font_size=12)))
        self.font_choice = toga.Selection(items=['12', '14', '16', '18', '20', '24', '28', '32'],
            value=self.preferences.values['font_size'], style=Pack(height=44))
        self.restore_choice = toga.Switch('Restore last document',
            value=self.preferences.values['restore_last_document'] == 'true', style=Pack(height=44))
        self.clear_documents_choice = toga.Switch('Clear documents with no pending changes on restart',
            value=self.preferences.values['clear_unmodified_documents_on_restart'] == 'true',
            style=Pack(height=44))
        self.settings_status = toga.Label(self.preferences.error, style=Pack(margin_top=12))
        box.add(self.restore_choice)
        # A wrapping label keeps the full preference readable on narrow phones.
        self.clear_documents_choice.text = 'Clear on restart'
        box.add(toga.Label('Clear documents with no pending\nchanges on restart'))
        box.add(self.clear_documents_choice)
        box.add(toga.Label('Closes saved items in Open documents.\nStored documents and unsaved drafts are kept.',
                           style=Pack(font_size=12)))
        box.add(heading('Text & Markdown'))
        box.add(toga.Label('Editor and preview font size'))
        box.add(self.font_choice)
        box.add(heading('Books & Comics'))
        box.add(toga.Label('Use Appearance in an open reader\nto adjust its pages.', style=Pack(font_size=12)))
        box.add(heading('LM Chat'))
        box.add(toga.Button('Server & generation settings…', on_press=self.show_chat_configuration, style=Pack(height=44)))
        box.add(heading('Folder Hub'))
        box.add(toga.Button('Remote connections…', on_press=self.show_cloud_connections, style=Pack(height=44)))
        box.add(heading('Apply preferences'))
        box.add(toga.Button('Save preferences', on_press=self.save_preferences, style=Pack(height=44)))
        box.add(toga.Button('Reload preferences', on_press=self.reload_preferences, style=Pack(height=44)))
        box.add(self.settings_status)
        if self.scene_manager.supported:
            box.add(toga.Button('New window', on_press=self.scene_manager.new_window, style=Pack(height=44)))
            if self.window_id != 'primary':
                box.add(toga.Button('Close window', on_press=lambda widget, **kw:
                    self.scene_manager.close_window(self), style=Pack(height=44)))
        self.document_cards_choice.on_change = self.change_document_overview
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)), destination='settings', root=True)

    def refresh_document_overview(self):
        # Replace only the retained root, including when a detail is open.
        # Presenting a new root route would discard the editor's navigation.
        self.refresh_documents()
        root = self.routes.roots['documents']
        view = self.build_documents_hub()
        view = self.adaptive.prepare(view, 'documents', root=True)
        for child in list(root.children):
            root.remove(child)
        root.add(view)

    def change_document_overview(self, widget, **kwargs):
        value = 'true' if widget.value else 'false'
        if value == self.preferences.values['document_card_overview']:
            return
        try:
            self.preferences.save(document_card_overview=value)
        except (OSError, ValueError) as error:
            widget.value = self.preferences.values['document_card_overview'] == 'true'
            self.settings_status.text = str(error)
            return
        self.refresh_document_overview()
        self.settings_status.text = 'Document view saved on this device.'

    def save_preferences(self, widget=None, **kwargs):
        try:
            self.preferences.save(font_size=self.font_choice.value,
                document_card_overview='true' if self.document_cards_choice.value else 'false',
                clear_unmodified_documents_on_restart='true' if self.clear_documents_choice.value else 'false',
                restore_last_document='true' if self.restore_choice.value else 'false')
            self.editor.style.font_size = int(self.preferences.values['font_size'])
            self.refresh_document_overview()
            self.settings_status.text = 'Preferences saved on this device.'
        except (OSError, ValueError) as error:
            self.settings_status.text = str(error)

    def reload_preferences(self, widget=None, **kwargs):
        self.preferences.reload()
        self.editor.style.font_size = int(self.preferences.values['font_size'])
        self.refresh_document_overview()
        self.show_settings()

    def show_preview(self, widget=None, **kwargs):
        if self.current is None or not self.checkpoint():
            return
        try:
            content = markdown_preview(self.current.text, int(self.preferences.values['font_size']))
        except ValueError as error:
            self.status.text = str(error)
            return
        if not hasattr(self, 'preview'):
            self.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                       style=Pack(flex=1))
        # A fresh WebView may still be navigating to its initial about:blank.
        # Give the HTML load a distinct local-document origin so that blank
        # navigation cannot consume Toga's one approved content navigation.
        self.preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        self.editor_view.session.view['markdown_mode'] = 'preview'
        previous = getattr(self, 'preview_box', None)
        if previous is not None:
            previous.remove(self.preview)
        owner = self.editor_view
        token = self.workspace.token(owner.session.id)
        def back_to_editor(widget=None, **kwargs):
            if self.active_host and self.workspace.accepts(token):
                if not self.checkpoint():
                    return
                owner.bind()
                self.workspace.activate(owner.session.id)
                self.show_documents()
        self.preview_box = toga.Box(children=[
            toga.Button('Back to editor', on_press=back_to_editor, style=Pack(height=44)),
            self.preview], style=Pack(direction=COLUMN, flex=1))
        self.show_view(self.preview_box, route='preview', title='Markdown preview')
        self.save_workspace()

    def refresh_documents(self):
        previous = self.loading
        self.loading = True
        documents, failures = self.store.documents()
        self.stored_document_kinds = {doc.id: text_document_kind(doc.name) for doc in documents}
        counts, self.labels = {}, {}
        for doc in documents:
            counts[doc.name] = counts.get(doc.name, 0) + 1
            label = doc.name + (f' ({counts[doc.name]})' if counts[doc.name] > 1 else '')
            while label in self.labels:
                label += ' (copy)'
            self.labels[label] = doc.id
        self.selector.items = list(self.labels)
        if self.current:
            self.selector.value = next((label for label, key in self.labels.items()
                                        if key == self.current.id), None)
        self.loading = previous
        self.recovery_notice.text = (f'{len(failures)} recovery record(s) could not be opened; they were preserved.'
                                     if failures else '')

    def open_document(self, key):
        opened = False
        previous_view = self.document_view
        displaying = (hasattr(self, 'routes') and previous_view in self.routes.body('documents').children)
        self.editor_view.capture()
        self.loading = True
        try:
            doc = self.store.open(key)
            session = self.workspace.open('managed-text', key,
                'markdown' if doc.name.lower().endswith(('.md', '.markdown')) else 'text', doc.name)
            view = self.text_views.get(session.id)
            if view is None:
                view = self.editor_view if self.editor_view.document is None else TextEditorView(self)
                view.load(doc, session)
                self.text_views[session.id] = view
            elif doc.conflict:
                view.document.conflict = True
                view.status.text = 'Stored file changed. Save a copy to keep recovered edits.'
            view.bind()
            self.pending_reader_restore = None
            opened = True
            session.title = self.current.name
            self.selector.items = list(self.labels)
            self.selector.value = next((label for label, identity in self.labels.items() if identity == key), None)
            try:
                self.preferences.save(last_document=key)
            except (OSError, ValueError) as error:
                self.status.text += ' · ' + str(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.status.text = str(error)
        finally:
            self.loading = False
        self.save_workspace(capture=False)
        if displaying:
            self.show_documents(resume=True)
        self.editor_view.restore()
        return opened

    def select_document(self, widget, **kwargs):
        if not self.loading and widget.value in self.labels:
            if self.checkpoint():
                self.open_document(self.labels[widget.value])

    def clear_restored_documents(self):
        """Prune only proven clean sessions; preserve unreadable recovery records."""
        for session in list(self.workspace.sessions.values()):
            if session.provider == 'managed-text':
                try:
                    document = self.store.open(session.resource)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
                if document.modified or document.conflict:
                    continue
            self.workspace.close(session.id, guard=lambda value: True)

    def choose_document_type(self, widget=None, **kwargs):
        if not self.checkpoint():
            return
        from .document_choices import choose_document_type
        choose_document_type(self)

    def create_chosen_document(self, extension):
        previous = self.current
        self.new_document(extension=extension)
        if self.current is not previous:
            self.show_documents()

    def new_document(self, widget=None, *, extension='txt', **kwargs):
        if not self.checkpoint():
            return
        try:
            if len(self.workspace.sessions) >= MAX_SESSIONS:
                raise ValueError('Close an open document before creating another (limit: 32).')
            if extension not in ('txt', 'md'):
                raise ValueError('Choose TXT or Markdown.')
            created = self.store.create('Untitled.' + extension)
            self.refresh_documents()
            self.open_document(created.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def name_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        try:
            self.current.name = document_name(widget.value)
            self.checkpoint()
        except ValueError:
            pass  # Allow an empty field while the user replaces its name.

    def text_changed(self, widget, **kwargs):
        if self.loading or self.current is None:
            return
        self.current.text = widget.value
        if self.checkpoint():
            self.status.text = 'Draft preserved' if self.current.modified else 'Saved'

    def checkpoint(self, *args, **kwargs):
        if not self.active_host:
            return False
        if self.current is None or self.loading:
            return True
        if getattr(self.current, 'private', False):
            self.status.text = 'This draft is session-only. Save it before leaving.'
            return not self.current.modified
        try:
            self.store.checkpoint(self.current)
            self.save_workspace()
            return True
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)
            return False

    def save_document(self, widget=None, **kwargs):
        if self.current is None:
            return
        try:
            self.current.name = document_name(self.name.value)
            self.store.save(self.current)
            self.refresh_documents()
            self.status.text = 'Saved'
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    def save_copy(self, widget=None, **kwargs):
        if self.current is None:
            return
        try:
            copy = self.store.save_copy(self.current, document_name(self.name.value))
            self.refresh_documents()
            self.open_document(copy.id)
        except (OSError, ValueError) as error:
            self.status.text = str(error)

    async def import_document(self, widget=None, *, origin=None, **kwargs):
        from .pickers import pick_document
        origin = origin or self.editor_view
        if origin.session is None or origin.session.id not in self.workspace.sessions or not origin.import_button.enabled:
            return
        if not self.checkpoint():
            return
        token = self.workspace.token(origin.session.id)
        origin.import_button.enabled = False
        try:
            selected = await pick_document(self)
            if selected:
                imported = await asyncio.to_thread(self.store.import_document, *selected)
                if not self.active_host or not self.workspace.accepts(token):
                    return  # The stored import remains available; never reopen a closed screen.
                if self.editor_view is not origin:
                    active = self.workspace.active
                    session = self.workspace.open('managed-text', imported.id,
                        'markdown' if imported.name.lower().endswith(('.md', '.markdown')) else 'text', imported.name)
                    view = TextEditorView(self)
                    view.load(imported, session)
                    self.text_views[session.id] = view
                    self.workspace.active = active
                    origin.status.text = 'Imported document is available in Open documents.'
                    self.refresh_documents()
                    self.save_workspace()
                    return
                self.refresh_documents()
                self.open_document(imported.id)
        except Exception as error:
            # Native bridge errors are not necessarily OSError subclasses.
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Import failed: ' + str(error)[:500]
        finally:
            origin.import_button.enabled = True

    async def export_document(self, widget=None, *, origin=None, **kwargs):
        from .pickers import export_document
        origin = origin or self.editor_view
        if origin.session is None or origin.session.id not in self.workspace.sessions or not origin.export_button.enabled:
            return
        if self.current is None or not self.checkpoint():
            return
        token = self.workspace.token(origin.session.id)
        origin.export_button.enabled = False
        try:
            document = origin.document
            done = await export_document(self, document_name(origin.name.value),
                                        document.snapshot.encode(document.text))
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Document copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            if self.active_host and self.workspace.accepts(token):
                origin.status.text = 'Export failed: ' + str(error)[:500]
        finally:
            origin.export_button.enabled = True

    def exit_app(self, app, **kwargs):
        if getattr(self, 'cloud_busy', False):
            self.cancel_cloud()
            return False
        if getattr(self, 'private_sessions', None) is not None:
            if not self.clear_private_reader():
                return False
        if getattr(self, 'cloud_client', None):
            self.cloud_client.cancel()
        if getattr(self, 'chat_client', None):
            self.chat_client.cancel()
        if hasattr(self, 'chat_current') and not self.checkpoint_chat():
            return False
        saved = self.checkpoint()
        if saved:
            self.memory_pressure.dispose()
        return saved

    def native_configuration_changed(self):
        if self.active_host:
            self.refresh_native_theme()

    def release_disposable_resources(self):
        if not self.active_host:
            return
        private = getattr(self, 'private_sessions', None)
        if private is not None:
            private.suspend()
        readers = getattr(self, 'readers', None)
        if readers is not None:
            for owner in readers.controllers.values():
                owner.suspend()
        for name in ('file_browser', 'remote_browser', 'editor_browser'):
            browser = getattr(self, name, None)
            if browser is not None:
                browser.icons.clear()

    def provider_sessions(self):
        from .private_sessions import PrivateSessions
        if not hasattr(self, 'private_sessions'):
            self.private_sessions = PrivateSessions(self)
        return self.private_sessions

    async def open_crypt(self, widget=None, *, copies=None, key=None, prepared=None, destination='documents', **kwargs):
        copies = copies or self.crypt_copies
        key = key if key is not None else self.crypt_labels.get(self.crypt_selector.value)
        if key is None:
            return False
        return await self.provider_sessions().open(copies, key, prepared=prepared, destination=destination)

    def private_dirty(self):
        return self.provider_sessions().dirty()

    def clear_private_reader(self, *, discard=False):
        return self.provider_sessions().clear(discard=discard)

    def resume_crypt(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return owner.resume_crypt()

    async def save_crypt(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return await owner.save_crypt()

    def edit_crypt_metadata(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return owner.edit_crypt_metadata()

    async def save_crypt_metadata(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return await owner.save_crypt_metadata()

    async def read_crypt_page(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return await owner.read_crypt_page()

    def close_crypt(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return owner.close_crypt()

    def discard_crypt(self, widget=None, **kwargs):
        owner = self.provider_sessions().active
        if owner is not None:
            return owner.discard_crypt()

    def request_provider_close(self, owner):
        import textwrap
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        box.add(toga.Label(textwrap.fill('Close ' + owner.session.title, 30), style=Pack(font_size=18)))
        box.add(toga.Label('Private edits stay in memory.\nSave or discard before closing.'))
        async def save(widget=None, **kwargs):
            if owner.session.id not in self.workspace.sessions or self.cloud_busy:
                return
            if owner.crypt_metadata_fields:
                await owner.save_crypt_metadata()
            else:
                await owner.save_crypt()
            if self.provider_sessions().close(owner.session.id):
                self.show_documents_hub()
        box.add(toga.Button('Save and close', on_press=save, style=Pack(height=44)))
        box.add(toga.Button('Discard and close', on_press=owner.discard_crypt, style=Pack(height=44)))
        box.add(toga.Button('Cancel', on_press=owner.resume_crypt, style=Pack(height=44)))
        self.show_view(box, destination='documents', route='private-close:' + owner.session.id, title='Close private document')


def main():
    return LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
