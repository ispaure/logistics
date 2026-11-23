"""Owned Open/Save As workflow; picker state never falls back to app attributes."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

import asyncio
from pathlib import Path
import threading
from dataclasses import dataclass, replace

import toga
from commonUtils.runtime.operations import MutationIncomplete, OperationCancelled
from commonUtils.runtime.resources.selection import ResourceSelection
from commonUtils.runtime.resources.paths import resource_name
from commonUtils.runtime.resources.provider import capabilities
from .document_destination_form import DestinationForm, PickerMessage as PickerMessage
from .local_sources import destination_location_labels
from .archive_operations import ACTION_KINDS, ordinary
from services.documents.storage import DocumentPolicy
from services.workflow_host import HostService, StateAttribute

MOVE_ACTIONS = ('move', 'move-selection')


@dataclass(frozen=True)
class PickerOrigin:
    token: tuple
    owner: object
    destination: str
    managed: bool


@dataclass
class PickerOperation:
    """One presentation's source, draft, origin and operation-specific owners.

    Native probe compatibility fields point here. Workers capture a detached
    copy before I/O; replacing a presentation invalidates its operation identity.
    """
    data: bytes | None = None
    source_document: object = None
    source_policy: DocumentPolicy | None = None
    privacy_gate: object = None
    origin: PickerOrigin | None = None
    creation: tuple | None = None
    binary_owner: object = None
    destination_action: object = None
    filename: str = ''
    mode: str = ''
    notebook_template: str = 'Blank'
    notebook_format: str = 'pro'


@dataclass
class PickerWork:
    cancel: threading.Event
    epoch: int
    client: object
    credential_generation: object
    navigation: int
    gate: object
    gate_revision: object
    location: tuple
    operation: PickerOperation
    presentation: PickerOperation
    mutation: bool = False
    interrupted: bool = False
    committed: bool = False
    awake: object = None
    progress: object = None


class EditorPicker(DestinationForm):
    cloud_busy = HostService('cloud_busy')
    cloud_view = HostService('cloud_view')
    cloud_restore_task = HostService('cloud_restore_task')
    current = HostService('current')
    store = HostService('store')
    active_host = HostService('active_host')
    existing_crypt_locations = HostService('existing_crypt_locations')
    linked_crypt_locations = HostService('linked_crypt_locations')
    folder_path_visible = HostService('folder_path_visible')
    storage_provider = HostService('storage_provider')
    set_cloud_busy = HostService('set_cloud_busy')
    provider_sessions = HostService('provider_sessions')
    show_cloud = HostService('show_cloud')
    show_documents = HostService('show_documents')
    show_view = HostService('show_view')
    open_crypt = HostService('open_crypt')
    resume_crypt = HostService('resume_crypt')

    save_as_data = StateAttribute('operation', 'data')
    save_as_source_document = StateAttribute('operation', 'source_document')
    save_as_privacy_gate = StateAttribute('operation', 'privacy_gate')
    origin = StateAttribute('operation', 'origin')
    creation = StateAttribute('operation', 'creation')
    binary_owner = StateAttribute('operation', 'binary_owner')
    destination_action = StateAttribute('operation', 'destination_action')
    source_filename = StateAttribute('operation', 'filename')
    editor_picker_mode = StateAttribute('operation', 'mode')

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.operation = PickerOperation()
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        self.editor_storage_roots = {}
        self.editor_storage_folders = {}
        self.editor_locked_roots = {}
        self.editor_linked_roots = {}
        self._work = None
        self._epoch = 0
        self._restore_when_idle = None
        self._listed_provider = None
        self._listed_credentials = None
        from .protection import for_app
        for_app(app).register(self, self.privacy_gates)

    def privacy_gates(self):
        return (self.operation.privacy_gate,) if self.operation.data is not None else ()

    def cancel(self, *, interrupted=False):
        if self._work is not None:
            self._work.interrupted = interrupted or self._work.interrupted
            self._work.cancel.set()

    def moving(self):
        return self._work is not None and self._work.mutation

    def clear(self):
        """Invalidate late results and forget picker-owned private material."""
        self.fit_keyboard(False)
        notice = getattr(self, 'move_notice', None)
        if notice is not None and notice.parent is not None:
            notice.parent.remove(notice)
        self._epoch += 1
        self.cancel()
        self.reset_creation_steps()
        self.panel = self._restore_when_idle = None
        pending = getattr(self, '_storage_refresh', None)
        if pending is not None and not pending.done():
            pending.cancel()
        self._storage_refresh = None
        self._listed_provider = None
        self._listed_credentials = None
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        self.editor_storage_roots = {}
        self.editor_storage_folders = {}
        self.editor_locked_roots = {}
        self.editor_linked_roots = {}
        self.clear_destination_fields()
        self.operation = PickerOperation()
        from .protection import for_app
        for_app(self.app).changed()

    def _begin_work(self):
        client = getattr(self.app, 'cloud_client', None)
        gate = self.operation.privacy_gate
        work = PickerWork(threading.Event(), self._epoch, client,
                          getattr(client, 'generation', None), self.app.navigation_generation,
                          gate, getattr(gate, 'revision', None),
                          (self.save_as_storage.value, self.picker_folder.value), self.operation, replace(self.operation))
        if gate is not None and gate.locked:
            work.cancel.set()
        self._work = work
        self.set_cloud_busy(True)
        self.disable_picker_actions()
        return work

    def _accepts(self, work):
        client = getattr(self.app, 'cloud_client', None)
        return (self._work is work and work.operation is self.operation and work.epoch == self._epoch and self.active_host
                and not work.cancel.is_set() and client is work.client
                and getattr(client, 'generation', None) == work.credential_generation
                and self.app.navigation_generation == work.navigation
                and work.location == (self.save_as_storage.value, self.picker_folder.value)
                and (work.gate is None or (not work.gate.locked
                     and work.gate.revision == work.gate_revision)))

    def _finish_work(self, work):
        if self._work is work:
            self._work = None
            if work.progress is not None:
                work.progress.close()
            if work.awake is not None:
                work.awake.close()
            if hasattr(self, 'move_progress'):
                self.move_progress.stop()
                if self.move_progress.parent is not None:
                    self.move_progress.parent.remove(self.move_progress)
            self.set_cloud_busy(False)
            self.update_picker_actions()
            restore, self._restore_when_idle = self._restore_when_idle, None
            if restore is not None and self.active_host and self.app.navigation_generation == restore[0]:
                self.app.loop.call_soon(lambda: self.cancel_text_destination(dismissed=restore[1]))

    def _capture_origin(self, owner, *, managed):
        session = getattr(owner, 'session', None)
        if session is None or session.id not in self.app.workspace.sessions:
            return None
        return PickerOrigin(self.app.workspace.token(session.id), owner,
                            self.app.native_host.state.destination, managed)

    def visible(self, body=None):
        from .routes import contains
        return self.panel is not None and contains(body or self.app.body, self.panel)

    def _restore_origin(self, origin):
        app = self.app
        if not self.active_host:
            return False
        if origin is not None and app.workspace.accepts(origin.token):
            key = origin.token[0]
            if origin.managed and app.text_views.get(key) is origin.owner:
                origin.owner.bind()
                app.workspace.activate(key)
                return app.show_documents(resume=True, destination=origin.destination)
            if getattr(app, '_notebook_views', {}).get(key) is origin.owner:
                from features.notebooks.mobile.documents import present
                present(app, origin.owner, destination=origin.destination)
                return True
            if not origin.managed and app.provider_sessions().controllers.get(key) is origin.owner:
                origin.owner.resume_crypt()
                return True
        app.show_documents_hub()
        return False

    async def show_crypt_save_as(self, widget=None, *, owner=None, **kwargs):
        owner = owner or self.provider_sessions().active
        if getattr(getattr(owner, 'crypt_reader', None), 'read_only', False):
            return
        if self.cloud_busy or owner is None or owner.crypt_reader is None or not owner.crypt_reader.editable:
            return
        source = getattr(owner.crypt_reader, 'source', None)
        provider = getattr(source, 'provider', owner._crypt_reader_store)
        operation = PickerOperation(origin=self._capture_origin(owner, managed=False),
                                    source_policy=DocumentPolicy.for_provider(provider))
        await self.show_text_destination(owner.crypt_reader.name, owner.crypt_reader.text_snapshot.encode(owner.crypt_text.value),
            privacy_gate=getattr(owner, 'privacy_gate', None), operation=operation)

    async def show_document_save_as(self, widget=None, **kwargs):
        if self.current is None:
            return
        source_document = self.current
        origin = self._capture_origin(self.app.editor_view, managed=True)
        name, data = source_document.name, source_document.snapshot.encode(source_document.text)
        if self.cloud_busy:
            return
        if not self.active_host:
            return
        if self.current is not source_document or origin is None or not self.app.workspace.accepts(origin.token):
            return
        await self.show_text_destination(name, data,
            operation=PickerOperation(origin=origin, source_document=source_document))

    async def show_editor_open(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        await self.show_editor_browser('open')

    async def show_text_destination(self, name, data, *, privacy_gate=None, operation=None):
        operation = replace(operation or PickerOperation(), privacy_gate=privacy_gate)
        await self.show_editor_browser('save', name, data, operation=operation)

    async def show_notebook_destination(self, panel):
        epoch, navigation = self._epoch, self.app.navigation_generation
        source = getattr(getattr(panel, 'document', None), 'resource', None)
        operation = PickerOperation(origin=self._capture_origin(panel, managed=False),
                                    source_policy=source.policy if source is not None else None,
                                    binary_owner=panel, privacy_gate=panel.privacy_gate)
        name = panel.editor.notebook.name + '.rmdoc'
        data = await asyncio.to_thread(panel.editor.notebook.to_bytes)
        if epoch != self._epoch or navigation != self.app.navigation_generation or not self.active_host:
            return
        await self.show_editor_browser('save', name, data, operation=operation)

    async def show_document_creation(self, name, origin, *, data=None):
        from .document_choices import available_choices
        if not available_choices(self.app):
            self.app.require_feature('text_editor')
            return
        await self.show_editor_browser('save', name, data if data is not None else b'', creation=origin)

    async def show_destination(self, name, action, *, start_folder=None):
        if not self.cloud_busy and self.active_host and getattr(action, 'kind', '') == 'download':
            # An older picker can sit below the current cloud folder. Reusing
            # its route would trim away that newer source before downloading.
            self.app.routes.retire_destination_picker(self.app.native_host.state.destination)
        await self.show_editor_browser('destination', name, destination_action=action, start_folder=start_folder)

    async def show_editor_browser(self, mode, name='', data=None, *, creation=None, destination_action=None,
                                  operation=None, start_folder=None):
        if self.cloud_busy or not self.active_host:
            return
        self._epoch += 1
        epoch = self._epoch
        operation = replace(operation or PickerOperation(), mode=mode, filename=name,
                            data=data, creation=creation, destination_action=destination_action)
        if hasattr(self, 'editor_browser'):
            await self.editor_browser.close()
        if not self.active_host or epoch != self._epoch:
            return
        self.reset_creation_steps()
        self.editor_picker_location = self._listed_provider = self._listed_credentials = None
        self.operation = operation
        self.discard_notebook_templates()
        from .protection import for_app
        for_app(self.app).changed()
        action = getattr(destination_action, 'kind', '')
        if action in ACTION_KINDS:
            self.creation_storage(include_encrypted=False)
            self.editor_storage_roots = {label: provider for label, provider in self.editor_storage_roots.items()
                                         if ordinary(provider) or provider is None}
        elif creation is not None or mode == 'folder':
            self.creation_storage()
        else:
            self.destination_storage(destination_action)
        source_store = getattr(getattr(self.operation.origin, 'owner', None), '_crypt_reader_store', None)
        source_provider = getattr(source_store, 'provider', None)
        source_reader = getattr(getattr(self.operation.origin, 'owner', None), 'crypt_reader', None)
        if self.operation.binary_owner is not None and self.operation.binary_owner.document is not None:
            source_provider = getattr(self.operation.binary_owner.document.resource, 'provider', None)
        source_folder = ''
        source_label = None
        if action in ACTION_KINDS:
            item = destination_action.item
            source_label = 'Source location'
            self.editor_storage_roots[source_label] = item.provider
            source_folder = item.path.rpartition('/')[0]
        elif action in MOVE_ACTIONS:
            provider = destination_action.provider
            source_label = self.move_source_label(provider)
            if start_folder is None:
                start_folder = destination_action.path.rpartition('/')[0] if action == 'move' else ''
            source_folder = start_folder
        if mode == 'save' and creation is None and source_provider is not None and not getattr(source_provider, 'remote_storage', False):
            source_label = 'Source location'
            self.editor_storage_roots[source_label] = source_provider
            source_folder = (self.operation.binary_owner.document.resource.path if self.operation.binary_owner is not None
                             else getattr(source_reader, 'key', '') or '').rpartition('/')[0]
        self.editor_picker_rows = {}
        roots = [*self.editor_storage_roots, *self.editor_locked_roots]
        panel, title = self.build_destination_form(roots, source_label=source_label, source_folder=source_folder)
        if creation is not None:
            self.show_creation_name()
            if self.creation_layout.paired:
                # Both panes are usable immediately on large allocations.
                await self.load_picker_location()
            return
        self.show_view(panel, route='text-destination', title=title)
        await self.load_picker_location()

    def destination_storage(self, destination_action, *, include_encrypted=True):
        action = getattr(destination_action, 'kind', '')
        roots = (self.app.file_roots if destination_action is not None and action != 'download'
                 else self.app.ordinary_file_roots(include_collections=action != 'download'))
        if not include_encrypted:
            from commonUtils.runtime.resources.local import LocalFiles
            roots = {label: provider for label, provider in roots.items()
                     if provider is None or isinstance(provider, LocalFiles) and not provider.private}
        self.editor_storage_roots = destination_location_labels(self.app, roots)
        self.editor_storage_folders = {}
        self.editor_locked_roots = {}
        self.editor_linked_roots = {}
        if not self.app.feature_enabled('rclone'):
            return
        from services.documents.mobile_locations import enabled
        if enabled(self.app.private_root):
            self.add_local_copy_destinations(roots)
        if not include_encrypted:
            return
        if action == 'download':
            unlocked = {}
            existing = self.existing_crypt_locations(roots=unlocked)
            # Downloads can initialize unlocked LocalCrypt storage.
            self.editor_storage_roots.update({label: location[0] for label, location in unlocked.items()})
        else:
            existing = self.existing_crypt_locations()
        self.editor_storage_roots.update(existing)
        if action in MOVE_ACTIONS:
            self.editor_linked_roots = self.linked_crypt_locations(
                folders=self.editor_storage_folders, locked=self.editor_locked_roots, include_missing_credentials=True)
        else:
            self.editor_linked_roots = self.linked_crypt_locations()
        self.editor_storage_roots.update(self.editor_linked_roots)

    def move_source_label(self, provider):
        from services.documents.locations import CollectionFiles

        location = getattr(provider, 'location', None)
        for label, root in self.editor_storage_roots.items():
            if root is provider or (location is not None and root == location):
                return label
        if (isinstance(provider, CollectionFiles) and provider.private_root == self.app.private_root
                and 'Local' in self.editor_storage_roots and self.editor_storage_roots['Local'] is None):
            return 'Local'
        label, suffix = 'Source location', 1
        while label in self.editor_storage_roots or label in self.editor_locked_roots:
            suffix += 1
            label = f'Source location ({suffix})'
        self.editor_storage_roots[label] = provider
        return label

    def creation_storage(self, *, include_encrypted=True):
        """Use the same on-device destination inventory for both creation forms."""
        roots = self.app.ordinary_file_roots()
        self.editor_storage_roots = destination_location_labels(self.app, {'Shared files': roots['Shared files'], **roots})
        self.editor_storage_folders = {}
        self.editor_locked_roots = {}
        self.editor_linked_roots = {}
        if not self.app.feature_enabled('rclone'):
            return
        self.add_local_copy_destinations(roots)
        if include_encrypted:
            self.editor_storage_roots.update({
                label: remote for label, remote in self.existing_crypt_locations().items()
                if self.folder_path_visible(getattr(remote, 'remote', remote))})
            self.editor_linked_roots = self.linked_crypt_locations(
                folders=self.editor_storage_folders, locked=self.editor_locked_roots)
            self.editor_storage_roots.update(self.editor_linked_roots)

    def add_local_copy_destinations(self, roots):
        from .local_sources import synced_local_folders
        folders = synced_local_folders(self.app.mirror_store(), visible=self.folder_path_visible)
        self.editor_storage_folders.update(folders)
        self.editor_storage_roots.update(dict.fromkeys(folders, roots['Local files']))

    def refresh_unlock_storage(self, *, include_encrypted):
        label, locked = self.save_as_storage.value, self.editor_locked_roots
        if getattr(self.operation.destination_action, 'kind', '') in MOVE_ACTIONS:
            self.destination_storage(self.operation.destination_action, include_encrypted=include_encrypted)
        else:
            self.creation_storage(include_encrypted=include_encrypted)
        if not include_encrypted:
            # A wrong password must still allow another attempt after Back.
            self.editor_locked_roots = locked
        self._changing_location = True
        try:
            self.save_as_storage.items = [*self.editor_storage_roots, *self.editor_locked_roots]
            self.save_as_storage.value = label if label in self.editor_storage_roots else next(iter(self.editor_storage_roots))
        finally:
            self._changing_location = False

    def preserve_for_destination_unlock(self):
        if (self.panel is None or self.editor_picker_location is None or not ordinary(self._listed_provider)
                or self.save_as_storage.value != self.editor_picker_location[0]):
            return False
        if (getattr(self.operation.destination_action, 'kind', '') not in MOVE_ACTIONS
                and self.operation.creation is None and self.operation.mode != 'folder'):
            return False
        self.refresh_unlock_storage(include_encrypted=False)
        return True

    async def rebind_move_source(self, operation):
        action = operation.destination_action
        source = action.provider
        if not source.private:
            return True
        from features.rclone.localcrypt.mobile.locations import LocalCryptLocation
        from features.rclone.mobile.service import native_service
        if not isinstance(getattr(source, 'location', None), LocalCryptLocation):
            raise ValueError('The encrypted source could not be reopened.')
        client = self.app.cloud_client
        generation = client.generation
        remote = client.resolve_remote(source.location.remote, source.location.cipher_identity, cipher=True)
        provider = await asyncio.to_thread(native_service(client).localcrypt.open, replace(source.location, remote=remote))
        if (self.operation is not operation or not self.visible() or self.app.cloud_client is not client
                or client.generation != generation):
            provider.close()
            return False
        operation.destination_action = replace(action, provider=provider)
        return True

    async def unlock_picker_storage(self, label):
        key, remote, identity, unlocked = self.editor_locked_roots[label]
        from services.documents.mobile_locations import enabled
        from .local_sources import device_files_label
        label_on_device = device_files_label(self.app) if enabled(self.app.private_root) else 'Local'
        moving = getattr(self.operation.destination_action, 'kind', '') in MOVE_ACTIONS
        previous = (self.editor_picker_location if moving and ordinary(self._listed_provider)
                    else (label_on_device, ''))
        if not await self.browser_editor_location(previous):
            return False
        operation = self.operation
        if key is None:
            await self.app.main_window.dialog(toga.InfoDialog(
                'Unlock required', 'Load the matching credential ZIP in Workspaces to unlock this copy.'))
            return False

        async def resume():
            if self.operation is not operation or not self.visible():
                return
            self.refresh_unlock_storage(include_encrypted=True)
            if unlocked in self.editor_storage_roots:
                if moving:
                    try:
                        if not await self.rebind_move_source(operation):
                            return
                    except (OSError, ValueError):
                        if self.operation is operation and self.visible():
                            self.save_as_status.value = 'The source copy is locked. Unlock it and start the move again.'
                            self.update_picker_actions()
                        return
                await self.browser_editor_location((unlocked, self.editor_storage_folders.get(unlocked, '')))
            else:
                self.save_as_status.value = 'The encrypted copy is no longer available.'

        self.app.show_cloud(present=False)
        self.app.show_retained_unlock(key, remote, identity=identity, resume=resume,
            destination=self.app.native_host.state.destination, preserve_destination_picker=True)
        return False

    def show_creation_name(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        returning = self.visible()
        self.show_naming_step()
        if not returning:
            self.show_view(self.creation_layout, route='text-destination', title='New document')
            self.app.loop.call_soon(self.creation_layout.on_resize, None)

    async def choose_creation_location(self, widget=None, **kwargs):
        if self.cloud_busy or self.name_panel is None or not self.visible():
            return
        if self.panel is self.location_panel and self.creation_layout.paired:
            from .keyboard import dismiss_picker_keyboard
            dismiss_picker_keyboard(self)
            return
        if self.panel is not self.name_panel:
            return
        # Native field notifications can arrive after Return or the toolbar tap.
        self.update_effective_name()
        if not self._creation_name_valid:
            return
        self.show_location_step()
        await self.load_picker_location()

    async def load_picker_location(self):
        panel = self.panel
        # Cold-start credential restoration can replace the client and then
        # advance its generation during the first local directory read. Retry
        # discarded results using fresh tokens without waiting for cloud setup.
        for _ in range(3):
            if await self.refresh_editor_browser():
                break
            if (not self.active_host or self.panel is not panel or not self.visible()
                    or self.save_as_status.value != 'Loading folder…'):
                break
        else:
            self.save_as_status.value = 'Locations changed while loading. Select a location to refresh.'

    def creating_notebook(self):
        return (self.operation.creation is not None or self.operation.binary_owner is not None) and Path(self.operation.filename).suffix.lower() == '.rmdoc'

    def select_creation_format(self, extension):
        self.operation.filename = 'Untitled.' + extension

    def select_notebook_template(self, operation, template, paper_format):
        if self.operation is operation and self._work is None:
            operation.notebook_template, operation.notebook_format = template, paper_format

    def picker_extensions(self):
        if self.operation.destination_action is not None:
            return ()
        # Creation keeps all supported document types visible while the user
        # switches format; Save As retains its existing format-specific filter.
        if self.operation.creation is not None:
            return ('.txt', '.md', '.markdown', '.rmdoc')
        return ('.rmdoc',) if self.creating_notebook() else SOURCE_EXTENSIONS

    def has_parent_folder(self):
        label = self.save_as_storage.value
        return self.picker_folder.value != self.editor_storage_folders.get(label, '') or (
            self.operation.creation is not None and label in ('Local', 'Received Files'))

    def update_picker_actions(self):
        from .local_sources import DeviceFiles
        busy = self.cloud_busy
        ready = (not busy and self.editor_picker_location ==
                 (self.save_as_storage.value, self.picker_folder.value))
        client = getattr(self.app, 'cloud_client', None)
        ready = ready and self._listed_credentials == (client, getattr(client, 'generation', None))
        provider = self._listed_provider if ready else None
        virtual_root = isinstance(provider, DeviceFiles) and not self.picker_folder.value
        writable = provider is not None and not getattr(provider, 'remote_storage', False) and not virtual_root
        mode = self.operation.mode
        can_create_folder = mode != 'open' and writable and capabilities(provider).create
        action = getattr(self.operation.destination_action, 'kind', '')
        if action in ACTION_KINDS:
            can_submit = ready and ordinary(provider) and (action == 'archive-add' or can_create_folder)
            can_create_folder = can_create_folder and action != 'archive-add'
        elif mode == 'open':
            can_submit = ready
        elif mode == 'folder':
            can_submit = can_create_folder and capabilities(provider).delete
        else:
            can_submit = writable and all(getattr(capabilities(provider), key) for key in ('create', 'rename', 'delete'))
        self.present_picker_actions(ready=ready, has_parent=ready and self.has_parent_folder(),
                                    busy=busy, working=self._work is not None, can_create_folder=can_create_folder,
                                    can_submit=can_submit, virtual_root=virtual_root)

    async def create_picker_folder(self, widget=None, **kwargs):
        from commonUtils.runtime.resources.mutations import create_resource_folder
        if self.cloud_busy or not self.picker_new_folder.enabled:
            return
        work = self._begin_work()
        try:
            name = resource_name(self.new_folder_name.value)
            provider = self.editor_provider(self.save_as_storage.value)
            path = '/'.join(p for p in (self.picker_folder.value, name) if p)
            await asyncio.to_thread(create_resource_folder, provider, path, cancelled=work.cancel.is_set)
            if not self._accepts(work):
                return
            self._finish_work(work)
            self.hide_new_folder()
            self.picker_folder.value = path
            await self.refresh_editor_browser()
        except Exception as error:
            if self._accepts(work):
                self.save_as_status.value = 'Folder creation failed: ' + str(error)[:200]
        finally:
            self._finish_work(work)

    async def complete_destination(self):
        if self.cloud_busy or self.editor_picker_location != (self.save_as_storage.value, self.picker_folder.value):
            return
        action = getattr(self.operation.destination_action, 'kind', '')
        if action in ACTION_KINDS:
            return await self.complete_archive_action()
        if action == 'download':
            return await self.complete_download()
        self.close_destination_search()
        if action == 'move-selection':
            return await self.complete_selected_move()
        work = self._begin_work()
        work.mutation = True
        self.save_as_name.enabled = False
        self.save_as_status.value = 'Moving… Keep this screen open, or use Cancel to stop.'
        plan = None
        try:
            from commonUtils.runtime.progress import CoalescedProgress
            work.awake = self.app.acquire_awake_lease()
            work.progress = CoalescedProgress(self.app.loop,
                lambda values, unused: self.update_move_progress(values),
                active=lambda: self._accepts(work), interval=.2)
            # Keep progress visible above the list on the Duo cover screen.
            if self.save_as_status.parent is not self.move_notice:
                self.save_as_status.parent.remove(self.save_as_status)
                self.move_notice.add(self.save_as_status)
            if self.move_progress.parent is None:
                self.move_notice.add(self.move_progress)
            if self.move_notice.parent is None:
                self.panel.insert(0, self.move_notice)
            self.move_progress.max = None
            self.move_progress.start()
            action = self.operation.destination_action
            name = action.path.rpartition('/')[2]
            provider = self.editor_provider(self.save_as_storage.value)
            target = '/'.join(p for p in (self.picker_folder.value, name) if p)
            source = action.provider
            if source.private and not provider.private:
                confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                    'Move to unencrypted storage?',
                    'The destination will contain a decrypted copy. Continue?'))
                if not confirmed or not self._accepts(work):
                    if not confirmed and self._accepts(work):
                        self.save_as_status.value = 'Move cancelled.'
                    return
            from .file_operations import FileOperationRequest, FileDestination
            destination = FileDestination(self.app.private_root, work.client, provider, work.credential_generation)
            request = FileOperationRequest('move', source, action.path, target, destination,
                                           plaintext_approved=source.private and not provider.private,
                                           expected_revision=action.expected_revision)
            # Use the same guarded, verified mutation as other file commands.
            from .document_mutations import prepare_document_mutation
            from .file_operations import retiring_work
            plan = await prepare_document_mutation(self.app, request,
                progress=lambda **values: work.progress.publish(values))
            def completed(result):
                work.committed = True
                plan.apply(result)
            result = await retiring_work(plan.execute, work.cancel, completed=completed)
            if not self._accepts(work):
                return
            self._finish_work(work)
            self.clear()
            await self.app.show_files()
            await self.app.browse_files()
            self.app.file_status.value = result.notice or 'Move finished. Destination verified before removing the source.'
        except Exception as error:
            if work.operation is self.operation and self.active_host and work.cancel.is_set():
                self.save_as_status.value = ('Move stopped after leaving the app or locking the device.'
                    if work.interrupted else 'Move cancelled.') + '\nInspect both locations before retrying.'
            elif self._accepts(work):
                self.save_as_status.value = 'Move failed: ' + str(error)[:250] + '\nRefresh before retrying; inspect both locations.'
        finally:
            try:
                if work.operation is self.operation and self.active_host and work.cancel.is_set():
                    if work.committed:
                        self.save_as_status.value = 'Move completed before it could stop. Refresh to see the destination.'
                    else:
                        self.save_as_status.value = ('Move stopped after leaving the app or locking the device.'
                            if work.interrupted else 'Move cancelled.') + '\nInspect both locations before retrying.'
                if plan is not None:
                    plan.release()
            finally:
                self._finish_work(work)

    async def complete_selected_move(self):
        from .document_mutations import prepare_document_mutation
        from .file_operations import FileDestination, FileOperationRequest, retiring_work

        action = self.operation.destination_action
        work = self._begin_work()
        work.mutation = True
        failures = []
        moved = set()
        try:
            label, folder = work.location
            provider = self.editor_provider(label)
            plaintext = action.provider.private and not provider.private
            if plaintext:
                confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                    'Move to unencrypted storage?', 'The destination will contain decrypted files. Continue?'))
                if not confirmed or not self._accepts(work):
                    return
            destination = FileDestination(self.app.private_root, work.client, provider, work.credential_generation)
            work.awake = self.app.acquire_awake_lease()
            for index, (source, revision) in enumerate(action.entries, 1):
                if not self._accepts(work) or work.cancel.is_set():
                    break
                self.save_as_status.value = f'Moving item {index} of {len(action.entries)}…'
                name = source.rpartition('/')[2]
                request = FileOperationRequest('move', action.provider, source,
                    '/'.join(filter(None, (folder, name))), destination,
                    plaintext_approved=plaintext, expected_revision=revision)
                plan = None
                try:
                    plan = await prepare_document_mutation(self.app, request)

                    def completed(result):
                        work.committed = True
                        moved.add(source)
                        plan.apply(result)

                    await retiring_work(plan.execute, work.cancel, completed=completed)
                except OperationCancelled:
                    break
                except (OSError, ValueError) as error:
                    failures.append(f'{name}: {error}')
                finally:
                    if plan is not None:
                        plan.release()
            if work.operation is self.operation and self.active_host:
                if work.cancel.is_set():
                    self.save_as_status.value = 'Move stopped. Inspect both folders.'
                elif self._accepts(work) and failures:
                    self.save_as_status.value = '\n'.join(failures)
                    if moved:
                        remaining = tuple(entry for entry in action.entries if entry[0] not in moved)
                        self.operation = replace(self.operation, destination_action=replace(action, entries=remaining))
                elif self._accepts(work):
                    self._finish_work(work)
                    self.clear()
                    await self.app.show_files()
                    await self.app.browse_files()
                    self.app.file_status.value = 'Move finished.'
        except (OSError, ValueError) as error:
            if self._accepts(work):
                self.save_as_status.value = str(error)[:250]
        finally:
            self._finish_work(work)

    async def complete_archive_action(self):
        from .file_operations import retiring_work
        if not self.app.feature_enabled('archives') or not self.picker_primary.enabled:
            return
        work = self._begin_work()
        work.mutation = True
        action = work.presentation.destination_action
        label, folder = work.location
        self.save_as_status.value = 'Working… Use Cancel to stop.'
        try:
            provider = self.editor_provider(label)
            name = self.save_as_name.value
            format = self.archive_format.value if action.kind == 'archive-create' else None
            work.awake = self.app.acquire_awake_lease()

            def completed(result):
                work.committed = True
                if action.kind == 'archive-add':
                    action.workspace.rewritten(result)

            result = await retiring_work(lambda cancelled: action.execute(
                provider, folder, name, format, self.app.private_root, cancelled), work.cancel, completed=completed)
            if not self._accepts(work):
                return
            self._finish_work(work)
            self.clear()
            self.return_from_archive_picker()
            if action.kind == 'archive-add':
                action.workspace.status.text = action.workspace.message
            elif action.kind == 'archive-extract':
                action.workspace.status.text = 'Extracted to ' + result.name
            else:
                await self.app.browse_files()
                self.app.file_status.value = 'Created ' + result.name
        except Exception as error:
            if work.operation is self.operation and self.active_host:
                self.save_as_status.value = ('Archive operation cancelled.' if work.cancel.is_set()
                                             else str(error)[:300])
        finally:
            self._finish_work(work)

    def return_from_archive_picker(self):
        adaptive = self.app.adaptive
        if self.app.native_host.state.destination == 'documents' and adaptive.split is not None:
            adaptive.trim_details(max(0, len(adaptive.detail_routes) - 1))
            if adaptive.detail_routes:
                self.app.route_changed(adaptive.detail_routes[-1][1])
                adaptive.render()
            else:
                adaptive.show_list()
            return
        self.app.routes.back()

    def update_move_progress(self, values):
        done, total = values['done'], values['total']
        phase = values['phase']
        if total is not None and total > 0:
            self.move_progress.stop()
            self.move_progress.max = 100
            self.move_progress.value = min(99, done * 100 / total)
            phase += f' · {min(99, done * 100 // total)}% · {done / 1_000_000:,.1f} / {total / 1_000_000:,.1f} MB'
        else:
            if self.move_progress.max is not None:
                self.move_progress.max = None
                self.move_progress.start()
            if done:
                phase += f' · {done / 1_000_000:,.1f} MB written'
        if values['total_files']:
            phase += f" · {values['files']} / {values['total_files']} files verified"
        self.save_as_status.value = phase + '\nKeep this screen open. Cancel stops the move safely.'

    async def complete_download(self):
        operation = self.operation
        work = self._begin_work()
        destination = None
        owned = False
        try:
            name = resource_name(self.save_as_name.value)
            target = '/'.join(p for p in (self.picker_folder.value, name) if p)
            provider = self.editor_provider(self.save_as_storage.value)
            if not provider.private:
                confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                    'Download to unencrypted storage?',
                    'The selected item will remain readable locally after the connection locks. Continue?'))
                if not confirmed:
                    return False
            if not self._accepts(work):
                return False
            destination = provider.reopen() if hasattr(provider, 'reopen') else provider
            owned = destination is not provider
            self._finish_work(work)
            # The transfer owns the next screen. Retire the completed form so
            # native Back returns to the retained source folder and viewport.
            route_destination = self.app.native_host.state.destination
            screens = self.app.routes.screens[route_destination]
            picker_index = next((i for i, screen in enumerate(screens)
                                 if screen[0] == 'text-destination'), None)
            if picker_index is not None:
                self.app.routes.trim(route_destination, picker_index)
                self.app.routes.render(route_destination)
            self.clear()
            completed = await operation.destination_action.complete(self.app, destination, target)
            if completed:
                from .browser_ui import refresh_download_directory
                await refresh_download_directory(self.app, destination, target)
            return completed
        except Exception as error:
            if operation is self.operation:
                self.save_as_status.value = 'Download failed: ' + str(error)[:250]
            else:
                self.app.cloud_status.value = 'Download failed: ' + str(error)[:250]
            return False
        finally:
            self._finish_work(work)
            if owned:
                destination.close()

    def browser_editor_selected(self, row):
        if row is None:
            self.picker_entries.items = ['Select an item…', *self.editor_picker_rows]
            picker = getattr(self.picker_entries._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            self.picker_entries.value = 'Select an item…'
            return
        label = next((label for label, value in self.editor_picker_rows.items() if value['path'] == row['path']), None)
        if label is None:
            label = 'Search: ' + row['path']
            self.editor_picker_rows[label] = row
            self.browser_editor_selected(None)
        self.picker_entries.value = label
        if getattr(self.operation.destination_action, 'kind', '') == 'archive-add':
            self.save_as_name.value = row['name']
        elif (not row['directory'] and self.operation.mode != 'folder'
                and self.operation.creation is None and self.operation.destination_action is None):
            self.save_as_name.value = row['name']

    async def browser_editor_file(self, row):
        """A search hit names a file in its own containing folder."""
        if self.cloud_busy:
            return
        folder = row['path'].rpartition('/')[0]
        if folder != self.picker_folder.value:
            await self.browser_editor_location((self.save_as_storage.value, folder))

    async def create_editor_folder(self, widget=None, **kwargs):
        return await self.create_picker_folder()

    def close_destination_search(self):
        browser = self.editor_browser
        if browser.search_open:
            if type(browser.search._impl).__module__.startswith('toga_android.'):
                from .keyboard import dismiss_picker_keyboard
                dismiss_picker_keyboard(self, browser.search)
            browser.close_search()

    async def browser_editor_folder(self, row):
        if self.cloud_busy:
            return False
        browser = self.editor_browser
        loaded = await self.browser_editor_location((self.save_as_storage.value, row['path']))
        if loaded and browser is self.editor_browser:
            self.close_destination_search()
        return loaded

    async def browser_editor_location(self, location):
        if self.cloud_busy or self.entering_creation_folder():
            return False
        label, folder = location
        start = self.editor_storage_folders.get(label, '')
        if start and folder != start and not folder.startswith(start + '/'):
            location = label, start
        if label == 'Shared Files':
            # Collection roots have their own providers, just as in Workspaces.
            # In particular, iOS protects the shared Local directory itself.
            from services.documents.locations import collection_path
            from .incoming_files import inbox_path
            for name, root in (('Local', collection_path(self.app.private_root)),
                               ('Received Files', inbox_path(self.app.private_root))):
                if folder == root.name or folder.startswith(root.name + '/'):
                    location = name, folder.removeprefix(root.name).lstrip('/')
                    break
        self._changing_location = True
        try:
            self.save_as_storage.value, self.picker_folder.value = location
        finally:
            self._changing_location = False
        return await self.refresh_editor_browser()

    def change_editor_storage(self, widget=None, **kwargs):
        if (self.panel is None or (self.panel is self.name_panel and not self.creation_layout.paired)
                or getattr(self, '_changing_location', False)):
            return
        if (self.creation is not None or self.operation.mode == 'folder'
                or getattr(self.operation.destination_action, 'kind', '') in MOVE_ACTIONS):
            # Native selectors may echo a programmatic change after navigation
            # has already started (or completed) the matching directory read.
            location = self.save_as_storage.value, self.picker_folder.value
            if location == self.editor_picker_location or self._work is not None and location == self._work.location:
                return
        if self.cloud_busy:
            if self.editor_picker_location is not None:
                self._changing_location = True
                try:
                    self.save_as_storage.value = self.editor_picker_location[0]
                finally:
                    self._changing_location = False
            return
        self.hide_new_folder()
        self.picker_folder.value = self.editor_storage_folders.get(self.save_as_storage.value, '')
        pending = getattr(self, '_storage_refresh', None)
        if pending is not None and not pending.done():
            pending.cancel()
        self._storage_refresh = self.app.loop.create_task(self.refresh_editor_browser())

    def editor_provider(self, label):
        return self.storage_provider(label, self.editor_storage_roots)

    async def refresh_editor_browser(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        label, folder = self.save_as_storage.value, self.picker_folder.value
        if label in self.editor_locked_roots:
            return await self.unlock_picker_storage(label)
        work = self._begin_work()
        previous_destination = self.picker_destination.text
        if self.creation is not None:
            self.picker_destination.text = ''
        self.save_as_status.value = 'Loading folder…'
        try:
            model = ResourceSelection(self.editor_provider(label), mode=self.operation.mode,
                                      extensions=self.picker_extensions())
            rows = await asyncio.to_thread(model.list, folder, cancelled=work.cancel.is_set)
            if self.operation.mode == 'folder':
                rows = [row for row in rows if row['directory'] and not row['name'].startswith('.')]
            if not self._accepts(work):
                return False
            self.editor_picker_rows = {f'{i+1}. {"Folder" if row["directory"] else "File"}: {row["name"]}': row for i,row in enumerate(rows)}
            self.editor_picker_location = label, folder
            self._listed_provider = model.provider
            self._listed_credentials = work.client, work.credential_generation
            self.picker_entries.items = list(self.editor_picker_rows)
            picker = getattr(self.picker_entries._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            if self.editor_picker_rows:
                self.picker_entries.value = next(iter(self.editor_picker_rows))
            self.editor_browser.set_entries(model, folder, rows, location=(label, folder))
            self.picker_header.update_provider(folder, model.provider)
            self.present_picker_location(label, folder, has_parent=self.has_parent_folder(),
                                         private=model.provider.private, suggest_creation=(
                                             self.creation is not None and not rows and capabilities(model.provider).create))
            return True
        except Exception as error:
            if not self._accepts(work):
                return False
            if self.editor_browser.tree is not None:
                self._changing_location = True
                try:
                    self.save_as_storage.value, self.picker_folder.value = self.editor_picker_location
                    self.picker_destination.text = previous_destination
                finally:
                    self._changing_location = False
            else:
                self.editor_picker_rows = {}
                self.picker_entries.items = []
                self.editor_browser.stop()
            self.save_as_status.value = str(error)
            return False
        finally:
            self._finish_work(work)

    async def parent_editor_folder(self, widget=None, **kwargs):
        if not self.cloud_busy and not self.entering_creation_folder() and self.has_parent_folder():
            if (not self.picker_folder.value and self.operation.creation is not None
                    and self.save_as_storage.value in ('Local', 'Received Files')):
                return await self.browser_editor_location(('Shared Files', ''))
            self.picker_folder.value = self.picker_folder.value.rpartition('/')[0]
            await self.refresh_editor_browser()

    async def select_editor_item(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        if getattr(self, 'editor_picker_location', None) != (self.save_as_storage.value, self.picker_folder.value):
            await self.refresh_editor_browser()
            return
        row = self.editor_picker_rows.get(self.picker_entries.value)
        if row:
            if row['directory']:
                self.picker_folder.value = row['path']
                await self.refresh_editor_browser()
            elif self.operation.creation is None and self.operation.mode != 'folder':
                self.save_as_name.value = row['name']

    async def confirm_editor_file(self, widget=None, **kwargs):
        if (self.name_panel is not None and self.panel is self.name_panel
                and not self.creation_layout.paired):
            return await self.choose_creation_location()
        pending = getattr(self, '_storage_refresh', None)
        if pending is not None:
            await pending
        if self.operation.destination_action is not None:
            return await self.complete_destination()
        if self.operation.mode == 'folder':
            return await self.create_notes_library()
        if self.operation.mode == 'save':
            return await self.save_text_destination()
        if self.cloud_busy:
            return
        from services.documents.mobile_storage import document_copies
        label, folder, name = self.save_as_storage.value, self.picker_folder.value, self.save_as_name.value
        work = self._begin_work()
        try:
            provider = self.editor_provider(label)
            model = ResourceSelection(provider, extensions=SOURCE_EXTENSIONS)
            path = await asyncio.to_thread(model.resolve, folder, name, cancelled=work.cancel.is_set)
            if not self._accepts(work):
                return
        except Exception as error:
            if self._accepts(work):
                self.save_as_status.value = str(error)
            return
        finally:
            self._finish_work(work)
        await self.open_crypt(copies=document_copies(provider), key=path, edit=True)

    def cancel_text_destination(self, widget=None, *, dismissed=False, **kwargs):
        visible = dismissed or self.visible()
        if self._work is not None:
            self.cancel()
            if (self.operation.origin is not None or self.operation.destination_action is not None
                    or self.operation.creation is not None or self.operation.mode == 'folder'):
                self._restore_when_idle = (self.app.navigation_generation, dismissed)
            self.save_as_status.value = ('Stopping the move… Waiting for file cleanup.' if self.moving()
                else 'Cancelling the operation. Your draft remains available.')
            return
        if not self.cloud_busy:
            origin = self.operation.origin
            creation = self.operation.creation
            destination_action = self.operation.destination_action
            self.clear()
            if visible:
                if destination_action is not None:
                    if destination_action.kind in ACTION_KINDS:
                        return None if dismissed else self.return_from_archive_picker()
                    if getattr(destination_action, 'kind', '') == 'download':
                        # UIKit may already have popped this form; direct Back
                        # and Cancel still need to retire it exactly once.
                        return None if dismissed else self.app.routes.back()
                    return self.app.loop.create_task(self.app.show_files())
                if creation is not None:
                    if dismissed:
                        return
                    destination, _, details = creation
                    adaptive = self.app.adaptive
                    if destination == 'documents' and adaptive.split is not None:
                        adaptive.trim_details(details)
                        if adaptive.detail_routes:
                            self.app.body = adaptive.detail_routes[-1][1]
                            self.app.route_changed(self.app.body)
                        else:
                            adaptive.show_list()
                        return
                    return self.app.routes.back()
                return self._restore_origin(origin)


    async def create_notes_library(self):
        from features.notes_library.notes import create_library
        from .obsidian import open_vault

        app = self.app
        if self.cloud_busy or not self.picker_primary.enabled or not app.feature_enabled('notes_library'):
            return
        provider = self._listed_provider
        parent, name = self.picker_folder.value, self.save_as_name.value
        work = self._begin_work()
        self.save_as_name.enabled = False
        try:
            root = await asyncio.to_thread(create_library, provider, parent, name,
                                           cancelled=work.cancel.is_set)
            if not self._accepts(work) or not app.feature_enabled('notes_library'):
                return
        except OperationCancelled:
            return
        except (OSError, ValueError) as error:
            if self._accepts(work):
                self.save_as_status.value = 'Library creation failed: ' + str(error)[:200]
            return
        finally:
            self._finish_work(work)

        self.clear()
        app.show_documents_hub()
        try:
            await open_vault(app, provider, root, 'documents')
        except (OSError, ValueError) as error:
            await app.main_window.dialog(toga.ErrorDialog(
                'Library created', 'The library could not be opened. ' + str(error)[:160]))


    async def save_text_destination(self, widget=None, **kwargs):
        if self.cloud_busy or self.operation.data is None or self.entering_creation_folder():
            return
        label, folder = self.save_as_storage.value, self.picker_folder.value
        if not self.app.require_document_feature(self.operation.filename):
            return
        work = self._begin_work()
        origin = work.presentation.origin
        creating = work.presentation.creation is not None
        try:
            if not self._accepts(work) or (origin is not None and not self.app.workspace.accepts(origin.token)):
                return
            request = self._capture_save_request(work.presentation, label, folder)
            if request is None:
                return
            resolved = await self._confirm_save_destination(work, request, label)
            if resolved is None:
                return
            if origin is not None and not self.app.workspace.accepts(origin.token):
                return
            destination, revision = resolved
            publication = await asyncio.to_thread(request.publish, destination, revision,
                                                   cancelled=work.cancel.is_set)
            if not self._accepts(work):
                return
            await self._open_saved_destination(work, request, publication)
        except MutationIncomplete as error:
            if not self._accepts(work):
                return
            self.save_as_status.value = str(error) + ('\nRefresh the folder before retrying.' if creating
                else '\nRefresh before retrying; your draft remains available.')
        except Exception as error:
            if not self.active_host or work.epoch != self._epoch or work.cancel.is_set():
                return
            self.save_as_status.value = ('Creation failed: ' if creating else 'Save As failed; draft retained: ') + str(error)[:200]
        finally:
            self._finish_work(work)

    def _capture_save_request(self, operation, label, folder):
        from services.documents.destinations import DestinationRequest
        from .workspace import MAX_SESSIONS

        creating = operation.creation is not None
        notebook = self.creating_notebook()
        if creating and notebook and self.notebook_templates is not None:
            operation.notebook_template, operation.notebook_format = self.notebook_templates.selection()
        extensions = self.picker_extensions()
        target = self.destination_filename()
        self.save_as_name.value = target
        provider = self.editor_provider(label)
        if (provider.private or getattr(provider, 'remote_storage', False)) and not self.app.require_feature('rclone'):
            return None
        return DestinationRequest.capture(
            provider, folder, target, operation.data, extensions,
            notebook=notebook, creating=creating, session_count=len(self.app.workspace.sessions),
            session_limit=MAX_SESSIONS, store=self.store, source_document=operation.source_document,
            notebook_template=operation.notebook_template, notebook_format=operation.notebook_format,
        )

    async def _confirm_save_destination(self, work, request, label):
        source_policy = work.presentation.source_policy
        confirm_plaintext = source_policy is not None and source_policy.confirm_plaintext(
            DocumentPolicy.for_provider(request.provider))
        if confirm_plaintext:
            confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                'Save to unencrypted storage?', 'The destination will contain a decrypted copy. Continue?'))
            if not self._accepts(work) or not confirmed:
                return None

        destination, revision = await asyncio.to_thread(request.resolve, cancelled=work.cancel.is_set)
        if not self._accepts(work):
            return None
        if revision is not None:
            confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                f'Replace “{Path(request.filename).name}”?',
                f'A file with this name already exists in {request.folder or label}. '
                'Replacing it will overwrite its contents.'))
            if not self._accepts(work) or not confirmed:
                return None

        if (confirm_plaintext or revision is not None) and request.filename != self.save_as_name.value:
            self.save_as_status.value = 'Destination changed. Save again to confirm the new destination.'
            return None
        return destination, revision

    async def _open_saved_destination(self, work, request, publication):
        from services.documents.storage import DocumentResource

        copies, destination, prepared = publication.require_reopened()
        operation = work.presentation
        creation = operation.creation
        epoch = self._epoch
        # Release the busy state before opening the editor. The epoch still guards the draft.
        self._finish_work(work)
        if creation is not None:
            route_destination, count, details = creation
            if route_destination == 'documents' and self.app.adaptive.split is not None:
                self.app.adaptive.trim_details(details)
            else:
                self.app.routes.trim(route_destination, count)
        if request.notebook:
            from features.notebooks.mobile.documents import open_notebook, retarget_notebook
            resource = DocumentResource(request.provider, destination, max_bytes=request.max_bytes)
            if operation.binary_owner is not None:
                opened = await retarget_notebook(self.app, operation.binary_owner, resource)
            else:
                opened = await open_notebook(self.app, resource=resource)
        else:
            opened = await self.open_crypt(copies=copies, key=destination, prepared=prepared,
                                           privacy_gate=operation.privacy_gate, edit=creation is not None)
        if not self.active_host or epoch != self._epoch:
            return
        if not opened:
            if creation is not None:
                self.save_as_status.value = 'The file was created in the chosen folder, but its editor could not be opened.'
                self.show_view(self.creation_layout, route='text-destination', title='New document')
            else:
                self.save_as_status.value = ('The file was saved, but its editor could not be opened. '
                                             'The Save As draft is retained.')
                self.show_view(self.panel, route='text-destination', title='Save As')
            return

        self.operation.origin = self.panel = None
        self.operation.binary_owner = None
        self.operation.creation = None
        self.operation.data = None
        self.operation.privacy_gate = None
        source_document = operation.source_document
        if source_document is not None and getattr(source_document, 'private', False):
            source_document.text = source_document.snapshot.text
            self.app.finish_save_as_source(source_document)
        self.operation.source_document = None
        self.operation.source_policy = None

