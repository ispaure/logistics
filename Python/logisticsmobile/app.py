"""Mobile composition root, host navigation and managed document lifecycle."""
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
from commonUtils.ui.native.navigation import NativeNavigationHost
from .routes import MobileRoutes
from .navigation import DESTINATION_ITEMS
from .workspace import Workspace, MAX_SESSIONS
from features.text_editor.mobile.ui import TextEditorView
from .workspace_navigation import WorkspaceNavigation as AdaptiveWorkspace
from .hub_ui import text_document_kind
from .host_services import OwnedAttribute, composed_workflow
from .provider_ui import ProviderUI
from .reader_lifecycle import ReaderLifecycle

_active_hosts = weakref.WeakValueDictionary()


from features.comics.mobile.collection.workflows import ComicBatchController
from features.lm.mobile.controller import ChatController
from features.rclone.mobile.controller import CloudController
from features.rclone.transfers.mobile.controller import TransferController
from logisticsmobile.folder_controller import FolderController
from logisticsmobile.hub_controller import HubController
from logisticsmobile.locations_controller import LocationsController
from logisticsmobile.storage_controller import StorageController


@composed_workflow('comic_batch_controller', ComicBatchController)
@composed_workflow('chat_controller', ChatController)
@composed_workflow('cloud_controller', CloudController)
@composed_workflow('transfer_controller', TransferController)
@composed_workflow('folder_controller', FolderController)
@composed_workflow('hub_controller', HubController)
@composed_workflow('locations_controller', LocationsController)
@composed_workflow('storage_controller', StorageController)
class LogisticsMobile(ReaderLifecycle, ReaderWorkspace, ProviderUI, toga.App):
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

    def provider_book_controller(self):
        from features.books.mobile.provider_controller import ProviderBookController
        if not hasattr(self, '_provider_book_controller'):
            self._provider_book_controller = ProviderBookController(self)
        return self._provider_book_controller

    def provider_comic_controller(self):
        from features.comics.mobile.provider_controller import ProviderComicController
        if not hasattr(self, '_provider_comic_controller'):
            self._provider_comic_controller = ProviderComicController(self)
        return self._provider_comic_controller

    @property
    def format_services(self):
        from .feature_hosts import reading_presentation
        return reading_presentation(self)

    @property
    def speech_presentation(self):
        if not hasattr(self, '_speech_presentation'):
            from .feature_hosts import speech_presentation
            self._speech_presentation = speech_presentation(self)
        return self._speech_presentation

    @property
    def presentation(self):
        if not hasattr(self, '_presentation'):
            from .feature_hosts import mobile_presentation
            self._presentation = mobile_presentation(self)
        return self._presentation

    @property
    def rclone_ui(self):
        if not hasattr(self, '_rclone_ui'):
            from .feature_hosts import rclone_host_ui
            self._rclone_ui = rclone_host_ui(self)
        return self._rclone_ui

    def startup(self):
        if toga.Command.ABOUT in self.commands:
            del self.commands[toga.Command.ABOUT]
        from .appearance import install_appearance
        install_appearance(self)
        self._startup_in_progress = True
        native = type(self._impl).__module__.startswith(('toga_iOS.', 'toga_android.'))
        if native and getattr(self, 'window_id', 'primary') == 'primary':
            self._async_startup = True
            from .startup import begin_startup
            begin_startup(self)
        else:
            # Scene creation needs a fully constructed host before attaching its
            # native window. Non-native callers retain synchronous startup too.
            for _ in self._startup_steps():
                pass
            self._startup_in_progress = False

    async def _prepare_startup_phase(self, index):
        if index != 1:
            return
        from .startup import load_startup_models
        root = self.private_root
        previous = _active_hosts.get(str(root.resolve()) + ':' + getattr(self, 'window_id', 'primary'))
        if previous is not None and previous is not self:
            pending = getattr(previous, 'startup_task', None)
            if pending is not None and not pending.done():
                pending.cancel()
            store = getattr(previous, 'store', None)
            if store is not None:
                store.flush_checkpoints()
            lists = getattr(previous, 'credential_document_lists', None)
            if lists is not None:
                lists.flush_writes()
            if hasattr(previous, 'chat_current') and not previous.checkpoint_chat():
                raise OSError('Could not preserve the previous conversation.')
            previous.active_host = False
        self._startup_models = await asyncio.to_thread(load_startup_models, root,
            getattr(self, 'workspace_root', root))

    def _start_background_cloud(self):
        from .startup import restore_cloud_in_background
        self.cloud_startup_task = self.loop.create_task(restore_cloud_in_background(self))

    def _startup_steps(self):
        from .startup import STEPS
        yield STEPS[0]
        root = Path(self.storage_root or self.paths.data)
        if type(self._impl).__module__.startswith('toga_iOS.') and self.storage_root is None:
            from .app_reset import finish_ios_reset
            finish_ios_reset(self, Path(self.paths.config).parent / 'Logistics')
            from .ios_storage import prepare_for_app
            root = prepare_for_app(self)
        self.private_root = root
        yield STEPS[1]
        host_identity = str(root.resolve()) + ':' + getattr(self, 'window_id', 'primary')
        previous_host = _active_hosts.get(host_identity)
        if previous_host is not None:
            store = getattr(previous_host, 'store', None)
            if store is not None:
                store.flush_checkpoints()
            lists = getattr(previous_host, 'credential_document_lists', None)
            if lists is not None:
                lists.flush_writes()
            if hasattr(previous_host, 'chat_current') and not previous_host.checkpoint_chat():
                raise OSError('Could not preserve the previous conversation.')
            pending = getattr(previous_host, 'startup_task', None)
            if pending is not None and not pending.done():
                pending.cancel()
            from .markdown_speech import stop_markdown_speech
            stop_markdown_speech(previous_host)
            from features.books.mobile.media_controls import stop_media
            stop_media(previous_host)
            vault = getattr(previous_host, 'vault_browser', None)
            if vault is not None:
                vault.dispose()
            memory = getattr(previous_host, 'memory_pressure', None)
            if memory is not None:
                memory.dispose()
            privacy = getattr(previous_host, 'screen_privacy', None)
            if privacy is not None:
                privacy.dispose()
            previous_host.active_host = False
            background = getattr(previous_host, 'cloud_startup_task', None)
            if background is not None:
                background.cancel()
            if getattr(previous_host, 'cloud_client', None) is not None:
                previous_host.cancel_cloud()
            picker = getattr(previous_host, '_editor_picker', None)
            if picker is not None:
                picker.clear()
            previous_workspace = getattr(previous_host, 'workspace', None)
            for session in getattr(previous_workspace, 'sessions', {}).values():
                previous_workspace.invalidate(session.id)
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
        models = self.__dict__.pop('_startup_models', None)
        self.preferences = models['preferences'] if models is not None else Preferences(workspace_root)
        from .appearance import configure_android_eink
        configure_android_eink(self)
        yield STEPS[2]
        self.store = models['store'] if models is not None else DocumentStore(root / 'Documents')
        from .recent_documents import RecentDocuments, MAX_RECENT
        self.recent_documents = models['recent'] if models is not None else RecentDocuments(workspace_root)
        self.workspace = models['workspace'] if models is not None else Workspace(workspace_root)
        self._startup_display = models['display'] if models is not None else {}
        from features.rclone.mobile.document_lists import CredentialDocumentLists
        async def reopen_reference(source):
            from .document_sources import reopen_file
            return await reopen_file(self, source)
        self.credential_document_lists = CredentialDocumentLists(self,
            references=self.recent_documents, max_recent=MAX_RECENT, reopen=reopen_reference)
        if models is None and self.preferences.values['clear_unmodified_documents_on_restart'] == 'true':
            self.clear_restored_documents()
        restored_document = self.workspace.sessions.get(self.workspace.active)
        self.pending_reader_restore = None
        if hasattr(self, 'scene_manager'):
            self.scene_manager.owners.attach(self.window_id, self)
            self.scene_manager.bind_workspace(self.window_id, self)
        yield STEPS[3]
        self.text_views = {}
        self.current = None
        self.loading = True
        self.labels = {}
        self.editor_view = TextEditorView(self)
        self.editor_view.bind()
        yield STEPS[4]
        self.native_host = NativeNavigationHost(DESTINATION_ITEMS, on_select=self.select_destination)
        self.routes = MobileRoutes(self, self.native_host, guard=self.checkpoint, changed=self.route_changed,
                             intent=self.mark_navigation)
        self.adaptive = AdaptiveWorkspace(self)
        self.routes.on_render = self.adaptive.render
        self.navigation = self.native_host.root
        self.body = self.routes.body()
        if not hasattr(self, '_startup_window'):
            self.main_window = getattr(self, 'window_class', toga.MainWindow)(title='Logistics', content=self.navigation)
        self.main_window.on_lose_focus = self.checkpoint
        self.main_window.on_resize = self.resize_workspace
        if not hasattr(self, 'scene_manager'):
            from .window_scenes import install_scenes
            install_scenes(self)
        self.scene_manager.activate()
        self.on_exit = self.exit_app
        yield STEPS[5]
        self.refresh_documents()
        self.loading = False
        if self.preferences.values['clear_unmodified_documents_on_restart'] == 'true':
            active = self.workspace.sessions.get(self.workspace.active)
            if active is not None and active.provider == 'managed-text':
                if getattr(self, '_async_startup', False):
                    self._pending_managed_restore = active.resource
                else:
                    self.open_document(active.resource)
        elif self.labels and (restored_document is None or restored_document.provider == 'managed-text'):
            key = self.preferences.values['last_document']
            active = self.workspace.sessions.get(self.workspace.active)
            if active is not None and active.provider == 'managed-text':
                key = active.resource
            if self.preferences.values['restore_last_document'] != 'true' or key not in self.labels.values():
                key = next(iter(self.labels.values()))
            if getattr(self, '_async_startup', False):
                self._pending_managed_restore = key
            else:
                self.open_document(key)
        yield STEPS[6]
        if not getattr(self, '_async_startup', False):
            self.show_documents_hub()
            self.show_folder_picker(initialize=False)
        self.show_home()
        self.save_workspace(capture=False)
        yield STEPS[7]
        if hasattr(self, 'startup_screen'):
            self.startup_screen.cover_workspace(self)
            self.startup_screen.restore_chrome(self)
        self.main_window.content = self.navigation
        self.main_window.show()
        from .keyboard import install as install_keyboard
        install_keyboard(self)
        from .screen_privacy import ScreenPrivacy
        self.screen_privacy = ScreenPrivacy(self)
        self.native_host.install(self.main_window)
        from .navigation import install_destination_icons, install_apple_selection
        install_destination_icons(self.native_host)
        install_apple_selection(self)
        self.routes.install()
        self.refresh_native_theme()
        self.adaptive.install()
        from .snow import SeasonalSnow
        self.seasonal_snow = SeasonalSnow(self)
        from .fold_layout import install as install_fold_layout
        install_fold_layout(self)
        from commonUtils.ui.native.memory import MemoryPressure
        self.memory_pressure = MemoryPressure(self, on_pressure=self.release_disposable_resources,
                                              on_configuration=self.native_configuration_changed)
        if self.preferences.values['restore_last_document'] == 'true':
            if restored_document is not None and not restored_document.transient:
                if restored_document.provider == 'library':
                    self.workspace.active = restored_document.id
                    self.show_documents_hub()
                    self.startup_document_task = self.loop.create_task(self.resume_library_session(restored_document))
                elif restored_document.provider == 'managed-text':
                    self.show_documents(resume=True, destination='documents')
        elif restored_document is not None and restored_document.provider == 'library':
            self.workspace.active = None
        self.save_workspace()

        # Explicit local developer launch only; ordinary launches do no capture.
        import os
        if os.environ.get('LOGISTICS_COMIC_LAYOUT_CHECK') == '1' and type(self.main_window._impl).__module__.startswith('toga_iOS.'):
            from .comic_layout_check import run
            self.loop.create_task(run(self))

    def select_destination(self, destination):
        if not self.checkpoint(save_workspace=False):
            return False
        if destination != 'files':
            self.retire_private_comic_batch()
        if destination != self.native_host.state.destination:
            self.mark_navigation()
        self.save_workspace()
        adaptive = getattr(self, 'adaptive', None)
        if (destination == 'documents' and destination == self.native_host.state.destination
                and (self.routes.screens['documents']
                     or (adaptive is not None and adaptive.in_detail and adaptive.detail_routes))):
            # A second tap means "show the list"; switching back from another
            # destination still resumes the retained document.
            self.pending_reader_restore = None
            self.show_documents_hub()
            return True
        if destination == 'chat' and not self.routes.screens['chat']:
            self.show_chat(present=False)
        if destination == 'settings':
            if not hasattr(self, 'settings_navigation'):
                self.show_settings(present=False)
            else:
                self.settings_navigation.reflow()
        self.refresh_hub(destination)
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
        sync_comic_chrome(self, self.body, destination=destination)
        # Material selection is reported before the shared destination commits.
        self.routes.sync_back(destination)
        key = self.pending_reader_restore
        if destination == 'documents' and key is not None:
            self.pending_reader_restore = None
            session = self.workspace.sessions.get(key)
            if session is not None and self.workspace.active == key:
                self.loop.create_task(self.resume_library_session(session))
        return True

    def mark_navigation(self):
        from .markdown_speech import stop_markdown_speech
        stop_markdown_speech(self)
        self.navigation_generation += 1

    def route_changed(self, body):
        from .markdown_speech import stop_markdown_speech
        stop_markdown_speech(self)
        self.body = body
        from .browser_ui import sync_browser_population
        sync_browser_population(self, body)
        if self.native_host.state.destination == 'settings' and hasattr(self, 'settings_navigation'):
            self.settings_navigation.reflow()
        batch = getattr(self, 'private_comic_batch', None)
        if batch is not None and batch.view is not None and batch.view not in body.children:
            self.retire_private_comic_batch()
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
        if (getattr(self, '_startup_in_progress', False)
                and not getattr(self, '_startup_layout_ready', False)):
            return
        from .layout_events import native_resize_changed
        if not native_resize_changed(self, widget):
            return
        from .keyboard import fit_editors
        fit_editors(self)
        from .settings_ui import fit_section
        if getattr(self, '_reset_scheduled', False):
            content = self.main_window.content
            fit_section(content.content if isinstance(content, toga.ScrollContainer) else content,
                        self.main_window.size.width)
            return
        for overlay in tuple(getattr(self, '_speech_overlays', ())):
            overlay.reposition()
        self.adaptive.render()
        if self.native_host.state.destination == 'settings' and hasattr(self, 'settings_navigation'):
            self.settings_navigation.reflow()
        for name in ('collection_storage_page', 'reset_page'):
            page = getattr(self, name, None)
            if page is not None:
                fit_section(page, max(280, self.adaptive.content_width('settings')))
        for name in ('cloud_connections_view', 'cloud_import_view', 'smb_view'):
            page = getattr(self, name, None)
            if page is not None:
                page.reflow()
        if hasattr(self, 'home_sections') and self.main_window.content is self.native_host.root:
            self.reflow_home()
        if hasattr(self, 'documents_sections'):
            self.reflow_documents_hub()
        if hasattr(self, 'document_launchers'):
            self.document_launchers.reflow(self.main_window.size.width)
        for grid in getattr(self, 'document_grids', []):
            grid.reflow(self.main_window.size.width)
        if hasattr(self, 'documentation'):
            self.documentation.reflow(self.adaptive.content_width('settings', margin=0))
        if hasattr(self, 'vault_browser'):
            owner = self.vault_browser
            owner.reflow(self.adaptive.content_width(owner.destination, margin=0))
        for owner in self.text_views.values():
            owner.apply_split(self.main_window.size.width)
        from .layout_events import notify_layout
        self.loop.call_soon(notify_layout, self)

    def refresh_native_theme(self):
        from .appearance import refresh_appearance
        refresh_appearance(self)
        enabled = self.preferences.values.get('android_eink') != 'true'
        editors = [owner.editor for owner in self.text_views.values()]
        private = getattr(self, 'private_sessions', None)
        if private is not None:
            editors.extend(owner.crypt_text for owner in private.controllers.values() if hasattr(owner, 'crypt_text'))
        for editor in editors:
            if hasattr(editor, 'highlighting'):
                editor.highlighting = enabled
                editor.changed(notify=False)

    def show_view(self, view, *, checkpoint=True, destination=None, route=None, title='', root=False):
        target = destination or self.native_host.state.destination
        if target == 'settings' and not root and not hasattr(self, 'settings_navigation'):
            self.show_settings(present=False)
        self.retire_private_comic_batch(view=view)
        privacy = getattr(self, 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()
        if checkpoint and not self.checkpoint():
            return False
        self.mark_navigation()
        target = destination or self.native_host.state.destination
        self.bind_reader_exit(view, route, target)
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
            if privacy is not None:
                privacy.refresh()
            return True
        self.routes.show(view, destination=destination, route=route, title=title, root=root)
        if root and target == 'documents':
            self.adaptive.show_list()
        if privacy is not None:
            privacy.refresh()
        return True

    def show_home(self, widget=None, **kwargs):
        self.show_view(self.build_home(), destination='home', root=True)

    def show_locations(self, widget=None, **kwargs):
        self.show_folder_picker()

    async def show_local_location(self, widget=None, **kwargs):
        await self.show_files()

    async def show_home_files(self, widget=None, **kwargs):
        # A local shortcut must not wait for credentials or reuse a previous
        # remote/private location and its search filter.
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
                if session.provider == 'notes-library':
                    owner = getattr(self, 'vault_browser', None)
                    if owner is not None and owner.session is session:
                        owner.present()
                    else:
                        self.show_unavailable_session(key)
                    return
                self.adaptive.focus_session(key)
                if session.provider == 'library':
                    self.loop.create_task(self.resume_library_session(session))
                elif session.provider == 'credential-reference':
                    self.loop.create_task(self.credential_document_lists.open(session))
                elif session.provider == 'provider-session':
                    self.provider_sessions().activate(session.id)
                else:
                    if self.open_document(session.resource):
                        self.show_documents(resume=True)
                    else:
                        self.show_unavailable_session(key)
        return activate

    async def resume_library_session(self, session):
        destination = self.native_host.state.destination
        try:
            await self.open_book(session.resource)
        except (OSError, ValueError, KeyError, TypeError):
            if (session.id in self.workspace.sessions and self.workspace.active == session.id
                    and self.native_host.state.destination == destination):
                self.show_unavailable_session(session.id)

    def show_unavailable_session(self, key):
        box = toga.Box(style=Pack(direction=COLUMN, margin=16, flex=1))
        box.add(toga.Label('Document unavailable', style=Pack(font_size=18)))
        box.add(toga.Label('Its stored data could not be opened.\nExisting files have been preserved.'))
        box.add(toga.Button('Try again', on_press=self.session_opener(key), style=Pack(height=48)))
        box.add(toga.Button('Remove from open documents', on_press=self.session_closer(key), style=Pack(height=48)))
        box.add(toga.Button('All documents', on_press=self.show_documents_hub, style=Pack(height=48)))
        self.show_view(box, route='unavailable:' + key, title='Unavailable document')

    def session_closer(self, key):
        def close(widget=None, **kwargs):
            self.request_close_session(key)
        return close

    def request_close_session(self, key):
        if self.visible_reader() == key:
            self.__dict__.setdefault('_reader_closing', set()).add(key)
        readers = getattr(self, 'readers', None)
        book = readers.controllers.get(key) if readers is not None else None
        if book is not None and self.book_edits_dirty(book):
            return self.request_book_close(book)
        private = self.provider_sessions().controllers.get(key)
        if private is not None and private.private_dirty():
            return self.request_provider_close(private)
        owner = self.text_views.get(key)
        if owner is None or not owner.document.modified:
            return self.close_session(key)
        return self.document_close_dialog(key, owner.document.name,
            lambda: self.close_session(key, choice='save'),
            lambda: self.close_session(key, choice='discard'))

    def cancel_close_session(self, key):
        self.__dict__.setdefault('_reader_closing', set()).discard(key)
        owner = self.text_views.get(key)
        if owner is not None:
            owner.bind()
            self.workspace.activate(key)
            self.show_documents(resume=True)

    async def request_delete_document(self, key):
        owner = self.text_views.get(key)
        if owner is None or key not in self.workspace.sessions:
            return False
        try:
            if len(self.scene_manager.owners.hosts) > 1:
                raise ValueError('Close other app windows before deleting a document.')
            warning = ('Are you sure you want to close and delete this document? '
                       'Its saved content and recovery copy will be permanently removed from this device.')
            if owner.document.modified:
                warning += ' Your unsaved changes will be lost.'
            from .document_dialogs import DocumentDialog
            if await self.main_window.dialog(DocumentDialog(
                    'Delete ' + owner.document.name + '?', warning, delete=True)) != 'delete':
                return False
            if not self.active_host or self.text_views.get(key) is not owner or key not in self.workspace.sessions:
                return False
            if len(self.scene_manager.owners.hosts) > 1:
                raise ValueError('Close other app windows before deleting a document.')
            return self.close_session(key, choice='delete')
        except (OSError, ValueError) as error:
            owner.status.text = 'Could not delete; document retained: ' + str(error)
            return False

    def close_session(self, key, *, choice='keep'):
        leaving_reader = key in self.__dict__.get('_reader_closing', ())
        if key not in self.workspace.sessions:
            return False
        if choice == 'cancel':
            return False
        if choice not in ('keep', 'save', 'discard', 'delete'):
            raise ValueError('Unsupported close action.')
        if choice == 'delete' and (self.workspace.sessions[key].provider != 'managed-text'
                                   or key not in self.text_views):
            return False
        if self.workspace.sessions[key].provider == 'notes-library':
            owner = getattr(self, 'vault_browser', None)
            if owner is not None and owner.session is self.workspace.sessions[key]:
                owner.dispose()
            else:
                self.workspace.close(key, guard=lambda session: True)
            self.reader_closed(key)
            return True
        if self.workspace.sessions[key].provider == 'credential-reference':
            self.credential_document_lists.closed(self.workspace.sessions[key])
            self.workspace.close(key, guard=lambda session: True)
            self.save_workspace()
            self.reader_closed(key)
            return True
        if self.workspace.sessions[key].provider == 'provider-session':
            if not self.provider_sessions().close(key, discard=choice == 'discard'):
                return False
            self.reader_closed(key)
            return True
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
                if choice == 'delete':
                    self.recent_documents.forget(session.provider, session.resource)
                    from .resource_imports import ResourceImports
                    imports = getattr(self, 'resource_imports', None) or ResourceImports(self.private_root)
                    imports.forget(session.provider, session.resource)
                    self.store.delete(owner.document)
                elif choice == 'save':
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
            from .reader_lifecycle import scroll_position
            owner.capture()
            positions = self.__dict__.setdefault('_closed_text_positions', {})
            positions.pop(owner.session.resource, None)
            positions[owner.session.resource] = (dict(owner.session.view), scroll_position(owner.preview))
            while len(positions) > 256:
                del positions[next(iter(positions))]
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
        self.reader_closed(key)
        if was_current and self.adaptive.split is not None and not leaving_reader:
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
            self.credential_document_lists.refresh()
            self.workspace.save()
            active = self.workspace.sessions.get(self.workspace.active)
            self.recent_documents.remember(active)
            if active is not None and getattr(active, 'history_source', None):
                self.recent_documents.remember_file(active, active.history_source)
            self.scene_manager.save_destination(self)
        except (OSError, ValueError) as error:
            self.recovery_notice.text = str(error)

    def show_documents(self, widget=None, *, resume=False, edit=False, destination=None, **kwargs):
        if self.current is None:
            pending = self.__dict__.pop('_pending_managed_restore', None)
            if pending is None or not self.open_document(pending):
                self.new_document()
        if self.current is None:
            return False
        self.pending_reader_restore = None
        self.workspace.activate(self.editor_view.session.id)
        mode = self.editor_view.session.view.get('markdown_mode',
            'preview' if self.editor_view.session.kind == 'markdown' else 'edit')
        preview = not edit and ((resume and mode == 'preview')
            or (self.editor_view.session.kind == 'markdown' and not resume))
        if preview:
            return self.show_preview(destination=destination)
        self.editor_view.session.view['markdown_mode'] = 'edit'
        return self.show_view(self.document_view, destination=destination, route='editor', title=self.current.name if self.current else 'New document')

    def show_editor_actions(self, owner, *, menu=None):
        menu = menu or owner.actions
        box = toga.Box(style=Pack(direction=COLUMN, margin=12))
        from .action_menu import command_groups
        for index, group in enumerate(command_groups(menu.actions)):
            if index:
                box.add(toga.Divider(style=Pack(margin_top=8, margin_bottom=8)))
            for title, action in group:
                def command(widget=None, target=action, **kwargs):
                    menu.invoke(target)
                box.add(toga.Button(title, on_press=command, style=Pack(height=48)))
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)), route='actions', title='Document actions')

    def show_settings(self, widget=None, *, present=True, rebuild=False, **kwargs):
        from .settings_ui import SettingsNavigation, settings_sections
        from .appearance import batch_surfaces
        # Native controls receive several default/intermediate styles while
        # building. Paint only their final appearance, before presenting them.
        with batch_surfaces():
            if rebuild or not hasattr(self, 'settings_navigation'):
                for name in ('font_choice', 'markdown_font_size_choice', 'text_font_size_choice', 'epub_font_size_choice', 'markdown_justify_choice', 'epub_justify_choice', 'restore_choice', 'clear_documents_choice'):
                    self.__dict__.pop(name, None)
                self.settings_navigation = SettingsNavigation(self, settings_sections(self))
            # Fit before mounting to avoid repeatedly laying out visible rows.
            self.settings_navigation.reflow()
        if present:
            self.show_view(self.settings_navigation, destination='settings', root=True)
        else:
            # Native tab-selection callbacks must not activate another tab or
            # recursively dispatch selection while its adapter is committing it.
            view = self.adaptive.prepare(self.settings_navigation, 'settings', root=True)
            root = self.routes.roots['settings']
            for child in list(root.children):
                root.remove(child)
            root.add(view)

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

    def change_seasonal_snow(self, widget, **kwargs):
        try:
            self.preferences.save(seasonal_snow='true' if widget.value else 'false')
        except (OSError, ValueError) as error:
            widget.on_change = None
            widget.value = self.preferences.values['seasonal_snow'] == 'true'
            widget.on_change = self.change_seasonal_snow
            self.settings_status.text = str(error)
            return
        self.seasonal_snow.refresh()
        self.settings_status.text = 'Seasonal snow saved on this device.'

    def change_android_eink(self, widget, **kwargs):
        try:
            self.preferences.save(android_eink='true' if widget.value else 'false')
        except (OSError, ValueError) as error:
            widget.on_change = None
            widget.value = self.preferences.values['android_eink'] == 'true'
            widget.on_change = self.change_android_eink
            self.settings_status.text = str(error)
            return
        from .appearance import configure_android_eink
        configure_android_eink(self)
        self.refresh_native_theme()
        self.seasonal_snow.refresh()
        self.settings_status.text = 'High contrast / E Ink saved on this device.'

    def change_session_speech(self, widget, **kwargs):
        try:
            self.preferences.save(session_speech_when_locked='true' if widget.value else 'false')
        except (OSError, ValueError) as error:
            widget.on_change = None
            widget.value = self.preferences.values['session_speech_when_locked'] == 'true'
            widget.on_change = self.change_session_speech
            self.settings_status.text = str(error)
            return
        from features.books.mobile.media_controls import settings_changed
        settings_changed(self)
        self.settings_status.text = 'Lock-screen speech preference saved on this device.'

    def save_preferences(self, widget=None, **kwargs):
        try:
            from .font_scaling import FONT_KEYS, refresh
            previous_fonts = tuple(self.preferences.values[key] for key in FONT_KEYS)
            alignment_keys = ('markdown_justify', 'epub_justify')
            previous_alignment = tuple(self.preferences.values[key] for key in alignment_keys)
            changes = {}
            for key in FONT_KEYS:
                choice = getattr(self, key + '_choice', None)
                if choice is not None:
                    changes[key] = choice.value
            for key in alignment_keys:
                choice = getattr(self, key + '_choice', None)
                if choice is not None:
                    changes[key] = 'true' if choice.value else 'false'
            for name, key in (('clear_documents_choice', 'clear_unmodified_documents_on_restart'),
                              ('restore_choice', 'restore_last_document')):
                if hasattr(self, name):
                    changes[key] = 'true' if getattr(self, name).value else 'false'
            self.preferences.save(**changes)
            if (tuple(self.preferences.values[key] for key in FONT_KEYS) != previous_fonts
                    or tuple(self.preferences.values[key] for key in alignment_keys) != previous_alignment):
                refresh(self)
            self.settings_status.text = 'Preferences saved on this device.'
        except (OSError, ValueError) as error:
            self.settings_status.text = str(error)

    def reload_preferences(self, widget=None, **kwargs):
        self.preferences.reload()
        from .magnifier import refresh
        refresh(self.preferences)
        from .appearance import configure_android_eink
        configure_android_eink(self)
        if type(self._impl).__module__.startswith('toga_android.'):
            self.refresh_native_theme()
        self.refresh_folder_visibility()
        from .font_scaling import refresh
        refresh(self)
        self.refresh_document_overview()
        self.show_settings(rebuild=True)

    def show_preview(self, widget=None, **kwargs):
        if self.current is None or not self.checkpoint():
            return
        try:
            from .font_scaling import font_size
            content = markdown_preview(self.current.text, font_size(self, self.editor_view.session.kind))
        except ValueError as error:
            self.status.text = str(error)
            return
        owner = self.editor_view
        if owner.preview is None:
            owner.preview = toga.WebView(on_navigation_starting=lambda widget, url, **kw: False,
                                         style=Pack(flex=1))
        from .font_scaling import bind
        bind(self, owner.preview, lambda: owner.session.kind, web=True)
        self.preview = owner.preview
        owner.session.view['markdown_mode'] = 'preview'
        token = self.workspace.token(owner.session.id)
        def back_to_editor(widget=None, **kwargs):
            if self.active_host and self.workspace.accepts(token):
                if not self.checkpoint():
                    return
                owner.bind()
                self.workspace.activate(owner.session.id)
                self.show_documents(edit=True)
        if owner.preview_box is None:
            from .control_icons import icon_button
            owner.preview_edit = icon_button('edit', 'Edit Markdown', on_press=back_to_editor)
            owner.preview_actions_button = icon_button('more', 'Document actions')
            owner.preview_toolbar = toga.Box(children=[owner.preview_edit,
                toga.Box(style=Pack(flex=1)), owner.preview_actions_button], style=Pack(direction=ROW))
            owner.preview_box = toga.Box(children=[
                owner.preview_toolbar,
                owner.preview], style=Pack(direction=COLUMN, flex=1))
            from commonUtils.ui.native.markdown_search import MarkdownPageSearch
            owner.preview_search = MarkdownPageSearch(owner.preview, owner.preview_box, insertion_index=1,
                valid=lambda: self.active_host and owner.session.id in self.workspace.sessions)
            owner.preview.on_webview_load = owner.preview_search.loaded
            owner.preview_box._workspace_toolbar = owner.preview_toolbar
            owner.preview_box._native_reader_toolbar = owner.preview_toolbar
            owner.preview_box._native_reader_buttons = lambda: [owner.preview_edit, owner.preview_actions_button]
            owner.preview_box._native_reader_title = lambda: owner.document.name
        bind(self, owner.preview, lambda: owner.session.kind, web=True)
        owner.preview_search.loading()
        saved = self.__dict__.get('_closed_text_positions', {}).get(owner.session.resource)
        if saved is not None:
            from .reader_lifecycle import restore_loaded_scroll
            restore_loaded_scroll(owner.preview, saved[1], lambda: self.workspace.accepts(token))
        self.preview.set_content('https://logistics.invalid/' + uuid4().hex + '/', content)
        from .action_menu import ActionMenu
        from .document_sources import folder_action
        if hasattr(owner, 'preview_actions'):
            owner.preview_actions.dispose()
        owner.preview_actions = ActionMenu(owner.preview_actions_button, owner,
            folder_action(self, owner.session) + [
                ('Find in this page…', owner.preview_search.show),
                ('Read aloud…', lambda: owner.markdown_speech.show()),
                ('Close document', lambda: self.request_close_session(owner.session.id)),
                ('Delete document…', lambda: self.request_delete_document(owner.session.id))])
        from .markdown_speech import MarkdownSpeech
        speech = getattr(owner, 'markdown_speech', None)
        if speech is None:
            owner.markdown_speech = speech = MarkdownSpeech(self, owner.preview, owner.preview_box,
                document_title=lambda: owner.document.name)
            owner.preview_toolbar.insert(len(owner.preview_toolbar.children) - 1, speech.button)
        speech.close()
        self.preview_box = owner.preview_box
        shown = self.show_view(self.preview_box, destination=kwargs.get('destination'),
                               route='preview', title=owner.document.name)
        self.save_workspace()
        return shown

    def refresh_documents(self):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            documents, failures = self.store.summaries()
            self._publish_document_summaries(documents, failures)
            return
        if getattr(self, '_startup_in_progress', False):
            documents, failures = ((self.store.cached_summaries(), [])
                if getattr(self, '_async_startup', False) else self.store.summaries())
            self._publish_document_summaries(documents, failures)
            return
        self._publish_document_summaries(self.store.cached_summaries(), [])
        self._document_refresh_again = True
        task = getattr(self, '_document_refresh_task', None)
        if task is None or task.done():
            async def refresh():
                while self.active_host and self._document_refresh_again:
                    self._document_refresh_again = False
                    records, warnings = await asyncio.to_thread(self.store.summaries)
                    if self.active_host and not self._document_refresh_again:
                        self._publish_document_summaries(records, warnings)
            self._document_refresh_task = self.loop.create_task(refresh())

    def _publish_document_summaries(self, documents, failures):
        previous = self.loading
        self.loading = True
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
            selected = next((label for label, key in self.labels.items()
                             if key == self.current.id), None)
            if selected is not None:
                self.selector.value = selected
        self.loading = previous
        self.recovery_notice.text = (f'{len(failures)} recovery record(s) could not be opened; they were preserved.'
                                     if failures else '')
        self.refresh_document_list()

    def open_document(self, key):
        self.__dict__.pop('_pending_managed_restore', None)
        opened = False
        previous_view = self.document_view
        displaying = (hasattr(self, 'routes') and previous_view in self.routes.body().children)
        self.editor_view.capture()
        self.loading = True
        try:
            doc = self.store.open(key)
            session = self.workspace.open('managed-text', key,
                'markdown' if doc.name.lower().endswith(('.md', '.markdown')) else 'text', doc.name)
            view = self.text_views.get(session.id)
            if view is None:
                saved = self.__dict__.get('_closed_text_positions', {}).get(key)
                if saved is not None:
                    session.view.update(saved[0])
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
            if (self.preferences.values['restore_last_document'] == 'true'
                    and session.id == self.workspace.active):
                continue
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

    def create_chosen_document(self, extension, *, name=None, content=''):
        previous = self.current
        self.new_document(extension=extension, name=name, content=content)
        if self.current is not previous:
            self.show_documents(edit=True)
            return True
        return False

    def new_document(self, widget=None, *, extension='txt', name=None, content='', **kwargs):
        if not self.checkpoint():
            return
        try:
            if len(self.workspace.sessions) >= MAX_SESSIONS:
                raise ValueError('Close an open document before creating another (limit: 32).')
            if extension not in ('txt', 'md'):
                raise ValueError('Choose TXT or Markdown.')
            created = self.store.create(name if name is not None else 'Untitled.' + extension,
                                        content=content.encode('utf-8'))
            self.refresh_documents()
            self.open_document(created.id)
            self.editor_view.session.view['markdown_mode'] = 'edit'
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
            self.editor_view.refresh_status()

    def checkpoint(self, *args, save_workspace=True, **kwargs):
        readers = getattr(self, 'readers', None)
        if readers is not None:
            for owner in readers.controllers.values():
                owner.request_position_flush()
        if getattr(self, '_startup_in_progress', False) and not hasattr(self, 'current'):
            return True
        if getattr(self, '_reset_scheduled', False):
            return True
        if not self.active_host:
            return False
        if hasattr(self, 'chat_current') and not self.checkpoint_chat():
            return False
        try:
            self.store.flush_checkpoints()
            self.credential_document_lists.flush_writes()
        except (OSError, ValueError) as error:
            self.status.text = 'Could not preserve edits: ' + str(error)
            return False
        if self.current is None or self.loading:
            return True
        if getattr(self.current, 'private', False):
            self.status.text = 'This draft is session-only. Save it before leaving.'
            return not self.current.modified
        try:
            self.store.checkpoint(self.current)
            if save_workspace:
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
            self.editor_view.refresh_status()
        except (OSError, ValueError) as error:
            self.editor_view.refresh_status()
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
        from .application_lifecycle import exit_app
        return exit_app(self, app, **kwargs)

    def native_configuration_changed(self):
        if self.active_host:
            self.refresh_native_theme()

    def release_disposable_resources(self):
        from .application_lifecycle import release_disposable_resources
        return release_disposable_resources(self)

    def cancel_cloud(self, widget=None, **kwargs):
        picker = getattr(self, '_editor_picker', None)
        if picker is not None:
            picker.cancel()
        transfer = getattr(self, '_transfer_controller', None)
        if transfer is not None:
            review = getattr(transfer, '_cancel_transfer_review', None)
            if review is not None:
                review()
            cancelled = getattr(transfer, '_transfer_cancel', None)
            if cancelled is not None:
                cancelled.set()
        return self.cloud_controller().cancel_cloud(widget, **kwargs)

    saved_files_message = OwnedAttribute('saved_files', 'saved_files_message')
    saved_files_status = OwnedAttribute('saved_files', 'saved_files_status')
    saved_files_summary = OwnedAttribute('saved_files', 'saved_files_summary')

    def saved_files(self):
        from .saved_files_ui import SavedFilesController
        if not hasattr(self, '_saved_files'):
            self._saved_files = SavedFilesController(self)
        return self._saved_files

    def show_saved_files(self, widget=None, **kwargs):
        return self.saved_files().show_saved_files(widget, **kwargs)

    async def delete_saved_file(self, key):
        return await self.saved_files().delete_saved_file(key)

    async def delete_all_saved_files(self, widget=None, **kwargs):
        return await self.saved_files().delete_all_saved_files(widget, **kwargs)

    def editor_picker(self):
        from .editor_picker import EditorPicker
        if not hasattr(self, '_editor_picker'):
            self._editor_picker = EditorPicker(self)
        return self._editor_picker

    def finish_save_as_source(self, source_document):
        if self.current is source_document:
            self.loading = True
            try:
                self.editor.value = source_document.text
            finally:
                self.loading = False
        source_document.private = False
        self.store.checkpoint(source_document)

    def provider_sessions(self):
        from .private_sessions import PrivateSessions
        if not hasattr(self, 'private_sessions'):
            self.private_sessions = PrivateSessions(self)
        return self.private_sessions

    async def open_crypt(self, widget=None, *, copies=None, key=None, prepared=None, destination=None, privacy_gate=None, edit=False, **kwargs):
        copies = copies or self.crypt_copies
        key = key if key is not None else self.crypt_labels.get(self.crypt_selector.value)
        if key is None:
            return False
        from .document_sources import opening_status, opening_ready
        with opening_status(self, dict(key=key), destination=destination):
            if not await opening_ready(self):
                return False
            return await self.provider_sessions().open(copies, key, prepared=prepared, destination=destination, privacy_gate=privacy_gate, edit=edit)

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
        async def save():
            if owner.session.id not in self.workspace.sessions or self.cloud_busy:
                return
            if owner.crypt_metadata_fields:
                await owner.save_crypt_metadata()
            else:
                await owner.save_crypt()
            if not owner.private_dirty():
                self.close_session(owner.session.id)
        return self.document_close_dialog(owner.session.id, owner.session.title,
            save, lambda: self.close_session(owner.session.id, choice='discard'))


def main():
    return LogisticsMobile('Logistics Mobile', 'io.github.ispaure.logisticsmobile')
