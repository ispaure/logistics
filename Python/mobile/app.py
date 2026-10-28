"""Mobile composition root, host navigation and aggregate lifecycle guards."""
import asyncio
from pathlib import Path
import weakref
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .documents import DocumentStore
from .preferences import Preferences
from .reader_sessions import ReaderWorkspace
from commonUtils.ui.native.navigation import NativeNavigationHost
from .routes import MobileRoutes
from .navigation import DESTINATION_ITEMS
from .workspace import Workspace
from features.text_editor.mobile.ui import TextEditorView
from .workspace_navigation import WorkspaceNavigation as AdaptiveWorkspace
from .managed_documents import ManagedDocumentWorkflows
from services.workflow_host import OwnedAttribute
from .composition.assembly import composed_workflow
from .provider_ui import ProviderUI
from .reader_lifecycle import ReaderLifecycle

_active_hosts = weakref.WeakValueDictionary()


from features.comics.mobile.collection.workflows import ComicBatchController
from features.lm.mobile.controller import ChatController
from features.rclone.mobile.controller import CloudController
from features.rclone.transfers.mobile.controller import TransferController
from mobile.folder_controller import FolderController
from mobile.hub_controller import HubController
from mobile.locations_controller import LocationsController
from mobile.storage_controller import StorageController


@composed_workflow('comic_batch_controller', ComicBatchController)
@composed_workflow('chat_controller', ChatController)
@composed_workflow('cloud_controller', CloudController)
@composed_workflow('transfer_controller', TransferController)
@composed_workflow('folder_controller', FolderController)
@composed_workflow('hub_controller', HubController)
@composed_workflow('locations_controller', LocationsController)
@composed_workflow('storage_controller', StorageController)
class LogisticsMobile(ManagedDocumentWorkflows, ReaderLifecycle, ReaderWorkspace, ProviderUI, toga.App):
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

    def comic_batch_controller(self) -> ComicBatchController:
        """Return the retained owner of this workflow."""
        if "_comic_batch_controller" not in self.__dict__:
            self._comic_batch_controller = ComicBatchController(self)
        return self._comic_batch_controller

    def chat_controller(self) -> ChatController:
        """Return the retained owner of this workflow."""
        if "_chat_controller" not in self.__dict__:
            self._chat_controller = ChatController(self)
        return self._chat_controller

    def cloud_controller(self) -> CloudController:
        """Return the retained owner of this workflow."""
        if "_cloud_controller" not in self.__dict__:
            self._cloud_controller = CloudController(self)
        return self._cloud_controller

    def transfer_controller(self) -> TransferController:
        """Return the retained owner of this workflow."""
        if "_transfer_controller" not in self.__dict__:
            self._transfer_controller = TransferController(self)
        return self._transfer_controller

    def folder_controller(self) -> FolderController:
        """Return the retained owner of this workflow."""
        if "_folder_controller" not in self.__dict__:
            self._folder_controller = FolderController(self)
        return self._folder_controller

    def hub_controller(self) -> HubController:
        """Return the retained owner of this workflow."""
        if "_hub_controller" not in self.__dict__:
            self._hub_controller = HubController(self)
        return self._hub_controller

    def locations_controller(self) -> LocationsController:
        """Return the retained owner of this workflow."""
        if "_locations_controller" not in self.__dict__:
            self._locations_controller = LocationsController(self)
        return self._locations_controller

    def storage_controller(self) -> StorageController:
        """Return the retained owner of this workflow."""
        if "_storage_controller" not in self.__dict__:
            self._storage_controller = StorageController(self)
        return self._storage_controller

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
        from .composition.presentation import reading_presentation
        return reading_presentation(self)

    @property
    def speech_presentation(self):
        if not hasattr(self, '_speech_presentation'):
            from .composition.presentation import speech_presentation
            self._speech_presentation = speech_presentation(self)
        return self._speech_presentation

    @property
    def presentation(self):
        if not hasattr(self, '_presentation'):
            from .composition.presentation import mobile_presentation
            self._presentation = mobile_presentation(self)
        return self._presentation

    @property
    def rclone_ui(self):
        if not hasattr(self, '_rclone_ui'):
            from .composition.presentation import rclone_host_ui
            self._rclone_ui = rclone_host_ui(self)
        return self._rclone_ui

    def startup(self):
        if type(self._impl).__module__.startswith('toga_iOS.'):
            from .cycle_collection import bind_ui_cycle_collection
            bind_ui_cycle_collection(self.loop)
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
        from .startup import StartupPhase
        if index != StartupPhase.PREFERENCES:
            return
        from .startup import load_startup_models
        root = self.private_root
        previous = _active_hosts.get(str(root.resolve()) + ':' + getattr(self, 'window_id', 'primary'))
        if previous is not None and previous is not self:
            from .application_lifecycle import lifecycle
            lifecycle(previous).prepare_replacement()
        self._startup_models = await asyncio.to_thread(load_startup_models, root,
            getattr(self, 'workspace_root', root))

    def _start_background_cloud(self):
        from .startup import restore_cloud_in_background
        self.cloud_startup_task = self.loop.create_task(restore_cloud_in_background(self))

    def _startup_steps(self):
        """Yield before each phase, preserving native draw and worker boundaries."""
        from .startup import STEPS, StartupPhase
        yield STEPS[StartupPhase.STORAGE]
        root = self._prepare_startup_storage()
        yield STEPS[StartupPhase.PREFERENCES]
        models, workspace_root = self._prepare_startup_preferences(root)
        yield STEPS[StartupPhase.DOCUMENTS]
        restored_document = self._prepare_startup_documents(root, models, workspace_root)
        yield STEPS[StartupPhase.EDITOR]
        self._prepare_startup_editor()
        yield STEPS[StartupPhase.NAVIGATION]
        self._prepare_startup_navigation()
        yield STEPS[StartupPhase.RESTORE]
        self._restore_startup_documents(restored_document)
        yield STEPS[StartupPhase.WORKSPACE]
        self._prepare_startup_workspace()
        yield STEPS[StartupPhase.WINDOW]
        self._attach_startup_window(restored_document)

    def _prepare_startup_storage(self):
        root = Path(self.storage_root or self.paths.data)
        if type(self._impl).__module__.startswith('toga_iOS.') and self.storage_root is None:
            from .app_reset import finish_ios_reset
            finish_ios_reset(self, Path(self.paths.config).parent / 'Logistics')
            from .ios_storage import prepare_for_app
            root = prepare_for_app(self)
        self.private_root = root
        return root

    def _prepare_startup_preferences(self, root):
        host_identity = str(root.resolve()) + ':' + getattr(self, 'window_id', 'primary')
        previous_host = _active_hosts.get(host_identity)
        if previous_host is not None and previous_host is not self:
            from .application_lifecycle import lifecycle
            lifecycle(previous_host).retire_for_replacement()
        self.active_host = True
        self.navigation_generation = 0
        _active_hosts[host_identity] = self
        workspace_root = getattr(self, 'workspace_root', root)
        models = self.__dict__.pop('_startup_models', None)
        self.preferences = models['preferences'] if models is not None else Preferences(workspace_root)
        manager = getattr(self, 'scene_manager', None)
        if manager is not None and manager.app is not self:
            self.preferences.feature_preferences = manager.app.preferences
        from .appearance import configure_android_eink
        configure_android_eink(self)
        return models, workspace_root

    def _prepare_startup_documents(self, root, models, workspace_root):
        from .browser_ui import BrowserStatusLabel
        from commonUtils.ui.native.password_input import PasswordInput
        self.document_status = BrowserStatusLabel(value='')
        self.document_password = PasswordInput()
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
        return restored_document

    def _prepare_startup_editor(self):
        self.text_views = {}
        from .layout_participants import participants
        from .managed_documents import reflow_text_views
        participants(self).register('text-readers', self, reflow_text_views, order=60)
        self.current = None
        self.loading = True
        self.labels = {}
        self.editor_view = TextEditorView(self)
        self.editor_view.bind()

    def _prepare_startup_navigation(self):
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

    def _restore_startup_documents(self, restored_document):
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

    def _prepare_startup_workspace(self):
        if not getattr(self, '_async_startup', False):
            self.show_documents_hub()
            self.show_folder_picker(initialize=False)
        self.show_home()
        self.save_workspace(capture=False)

    def _attach_startup_window(self, restored_document):
        if hasattr(self, 'startup_screen'):
            self.startup_screen.cover_workspace(self)
            self.startup_screen.restore_chrome(self)
        self.main_window.content = self.navigation
        self.main_window.show()
        from .keyboard import install as install_keyboard
        install_keyboard(self)
        from .screen_privacy import ScreenPrivacy
        self.screen_privacy = ScreenPrivacy(self)
        from .audio_output import for_app
        for_app(self)
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
                elif restored_document.provider == 'notebook':
                    from features.notebooks.mobile.documents import open_notebook
                    self.show_documents_hub()
                    self.startup_document_task = self.loop.create_task(open_notebook(self, key=restored_document.resource, destination='documents'))
                elif restored_document.provider == 'managed-text':
                    self.show_documents(resume=True, destination='documents')
        elif restored_document is not None and restored_document.provider == 'library':
            self.workspace.active = None
        self.save_workspace()

        from .incoming_files import start_receiving
        start_receiving(self)

        # Explicit local developer launch only; ordinary launches do no capture.
        import os
        if os.environ.get('LOGISTICS_COMIC_LAYOUT_CHECK') == '1' and type(self.main_window._impl).__module__.startswith('toga_iOS.'):
            from .comic_layout_check import run
            self.loop.create_task(run(self))

    def feature_enabled(self, name):
        from services.mobile_features import enabled
        return enabled(self.preferences, name)

    def require_feature(self, name, *, destination=None, present=True):
        from .feature_settings import require
        return require(self, name, destination=destination, present=present)

    def set_feature_enabled(self, name, value, *, refresh=True):
        from .feature_settings import set_enabled
        return set_enabled(self, name, value, refresh=refresh)

    def require_document_feature(self, name, *, kind=None, copies=None):
        from services.mobile_features import document_feature
        feature = document_feature(name, kind)
        if feature is not None and not self.require_feature(feature):
            return False
        if copies is not None:
            from services.documents.mobile_reading import reading_capabilities
            required = reading_capabilities(copies).required_feature
            if required is not None and not self.require_feature(required):
                return False
        return True

    def select_destination(self, destination):
        if not self.checkpoint(save_workspace=False):
            return False
        if destination != 'files':
            self.retire_private_comic_batch()
        self.mark_navigation()
        self.save_workspace()
        adaptive = getattr(self, 'adaptive', None)
        if destination == self.native_host.state.destination:
            # Reselecting any tab returns to its root without closing retained
            # document/chat sessions or asking for a reader-close decision.
            if adaptive is not None and destination in adaptive.menu_open:
                adaptive.menu_open[destination] = False
            if destination == 'documents':
                self.pending_reader_restore = None
                self.show_documents_hub()
                return True
            cancel = getattr(self, '_cancel_transfer_review', None)
            if destination == 'files' and cancel is not None:
                cancel()
            if (destination == 'chat' and getattr(self, 'chat_drawer_open', False)
                    and adaptive is not None and adaptive.width() < 640):
                self.toggle_chat_conversations()
            if destination == 'settings' and hasattr(self, 'settings_navigation'):
                self.settings_navigation.detail_requested = False
                for child in list(self.settings_navigation.detail.children):
                    self.settings_navigation.detail.remove(child)
            self.routes.trim(destination, 0)
            self.routes.render(destination)
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
        from .routes import contains
        for overlay in tuple(getattr(self, '_speech_overlays', ())):
            owner = getattr(overlay, 'chapter_owner', None)
            if owner is not None and not contains(body, owner):
                overlay.panel.hide()
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
        if not getattr(self, 'active_host', True) and not getattr(self, '_reset_scheduled', False):
            return
        if (getattr(self, '_startup_in_progress', False)
                and not getattr(self, '_startup_layout_ready', False)):
            return
        from .layout_events import native_resize_changed
        if not native_resize_changed(self, widget):
            return
        from .keyboard import fit_editors
        fit_editors(self)
        from .settings.forms import fit_section
        if getattr(self, '_reset_scheduled', False):
            content = self.main_window.content
            fit_section(content.content if isinstance(content, toga.ScrollContainer) else content,
                        self.main_window.size.width)
            return
        for overlay in tuple(getattr(self, '_speech_overlays', ())):
            overlay.reposition()
        self.adaptive.render()
        from .fold_layout import sync_epub_geometry
        sync_epub_geometry(self)
        if self.native_host.state.destination == 'settings' and hasattr(self, 'settings_navigation'):
            self.settings_navigation.reflow()
        from .layout_participants import LayoutFrame, participants
        participants(self).reflow(LayoutFrame(self.main_window.size.width, self.adaptive.content_width))
        from .layout_events import notify_layout
        self.loop.call_soon(notify_layout, self)

    def refresh_native_theme(self):
        from .appearance import refresh_appearance, native_theme_configuration
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
        self._native_theme_configuration = native_theme_configuration(self)

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
        if self.routes.apple:
            from .ios_toolbar import prepare_form
            form_actions = {
                'chat-settings': dict(primary='Save & return to chat', back='Back to conversation'),
                'transfer-settings': dict(primary='Save settings', cancel='Cancel'),
                'unlock-credential': dict(primary='Unlock', cancel='Cancel'),
                'transfers': dict(back='Back'),
                'saved-files': dict(back='Back to Settings'),
                'local-push': dict(cancel='Cancel'),
            }
            if route in form_actions:
                prepare_form(view, **form_actions[route])
            elif route and route.endswith(':metadata'):
                prepare_form(view, primary='Save metadata', back='Return to reading')
            elif route and route.endswith((':layout', ':appearance')):
                prepare_form(view, primary='Apply and return')
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
                if session.provider == 'notebook':
                    from features.notebooks.mobile.documents import open_notebook
                    self.loop.create_task(open_notebook(self, key=session.resource))
                elif session.provider == 'library':
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
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).request_close_session(key)

    def cancel_close_session(self, key):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).cancel_close_session(key)

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
            from features.text_editor.mobile.document_dialogs import DocumentDialog
            if await self.main_window.dialog(DocumentDialog(
                    'Delete ' + owner.document.name + '?', warning, delete=True)) != 'delete':
                return False
            if not self.active_host or self.text_views.get(key) is not owner or key not in self.workspace.sessions:
                return False
            if len(self.scene_manager.owners.hosts) > 1:
                raise ValueError('Close other app windows before deleting a document.')
            closing = self.__dict__.setdefault('_reader_closing', set())
            if self.visible_reader() == key:
                closing.add(key)
            try:
                return self.close_session(key, choice='delete')
            finally:
                closing.discard(key)
        except (OSError, ValueError) as error:
            owner.status.text = 'Could not delete; document retained: ' + str(error)
            return False

    def close_session(self, key, *, choice='keep'):
        from .session_workflows.transitions import transitions_for
        return transitions_for(self).close(key, choice=choice).committed

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
        if not self.require_feature('text_editor'):
            return False
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
        from .settings.navigation import SettingsNavigation
        from .settings.categories import settings_sections
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
        from .settings.forms import save_boolean_switch
        if not save_boolean_switch(self.preferences, widget, 'seasonal_snow', self.change_seasonal_snow, self.settings_status):
            return
        self.seasonal_snow.refresh()
        self.settings_status.text = 'Seasonal snow saved on this device.'

    def change_android_eink(self, widget, **kwargs):
        from .settings.forms import save_boolean_switch
        if not save_boolean_switch(self.preferences, widget, 'android_eink', self.change_android_eink, self.settings_status):
            return
        from .appearance import configure_android_eink
        configure_android_eink(self)
        self.refresh_native_theme()
        self.seasonal_snow.refresh()
        self.settings_status.text = 'High contrast / E Ink saved on this device.'

    def change_session_speech(self, widget, **kwargs):
        from .settings.forms import save_boolean_switch
        if not save_boolean_switch(self.preferences, widget, 'session_speech_when_locked', self.change_session_speech, self.settings_status):
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

    def exit_app(self, app, **kwargs):
        from .application_lifecycle import exit_app
        return exit_app(self, app, **kwargs)

    def native_configuration_changed(self):
        if self.active_host:
            from .appearance import native_theme_configuration
            configuration = native_theme_configuration(self)
            # Android sends this callback for rotation as well as theme changes.
            # Layout has its own native notifications; avoid repainting every
            # retained control and editor when the palette is unchanged.
            if (configuration is not None
                    and configuration == getattr(self, '_native_theme_configuration', None)):
                return
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

    async def open_local_document(self, path, *, destination=None):
        from .document_imports import open_local_document
        return await open_local_document(self, path, destination=destination)

    async def open_download(self, widget=None, *, path=None, destination=None, **kwargs):
        if path is None:
            return await self.cloud_controller().open_download(widget, destination=destination, **kwargs)
        if not self.require_document_feature(str(path)):
            return False
        from .document_sources import opening_status
        from .document_imports import open_local_document
        with opening_status(self, dict(path=str(path)), destination=destination):
            await asyncio.sleep(0)
            return await open_local_document(self, path, destination=destination)

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
        from features.notebooks.mobile.documents import prepare_notebook_lock
        if not prepare_notebook_lock(self, discard=discard):
            return False
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
