"""Owned Open/Save As workflow; picker state never falls back to app attributes."""
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

import asyncio
from pathlib import Path
import threading
from dataclasses import dataclass

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, NONE
from commonUtils.runtime.operations import MutationIncomplete
from commonUtils.runtime.resources.selection import ResourceSelection
from commonUtils.runtime.resources.paths import resource_name
from commonUtils.runtime.resources.provider import capabilities
from features.rclone.localcrypt.mobile.resources import encrypted_copies
from .control_icons import icon_button
from services.workflow_host import HostService


@dataclass(frozen=True)
class PickerOrigin:
    token: tuple
    owner: object
    destination: str
    managed: bool


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


class EditorPicker:
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

    def __init__(self, app):
        self.app = app
        self.save_as_data = None
        self.save_as_source_document = None
        self.save_as_privacy_gate = None
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        self.editor_storage_roots = {}
        self.editor_linked_roots = {}
        self._work = None
        self._epoch = 0
        self.origin = None
        self.panel = None
        self._restore_when_idle = None
        self.creation = None
        self.destination_action = None
        self._listed_provider = None
        self._listed_credentials = None

    def cancel(self):
        if self._work is not None:
            self._work.cancel.set()

    def clear(self):
        """Invalidate late results and forget picker-owned private material."""
        self.fit_keyboard(False)
        self._epoch += 1
        self.cancel()
        self.origin = self.panel = self._restore_when_idle = None
        pending = getattr(self, '_storage_refresh', None)
        if pending is not None and not pending.done():
            pending.cancel()
        self._storage_refresh = None
        self.creation = None
        self.destination_action = None
        self._listed_provider = None
        self._listed_credentials = None
        self.save_as_data = self.save_as_source_document = self.save_as_privacy_gate = None
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        self.editor_storage_roots = {}
        self.editor_linked_roots = {}
        if hasattr(self, 'editor_browser'):
            self.editor_browser.stop()
        if hasattr(self, 'picker_entries'):
            self.picker_entries.items = []
            self.picker_folder.value = ''
            self.save_as_name.value = ''
            self.new_folder_name.value = ''
            self.save_as_storage.items = []
            self.save_as_status.value = ''

    def _begin_work(self):
        client = getattr(self.app, 'cloud_client', None)
        gate = self.save_as_privacy_gate
        work = PickerWork(threading.Event(), self._epoch, client,
                          getattr(client, 'generation', None), self.app.navigation_generation,
                          gate, getattr(gate, 'revision', None),
                          (self.save_as_storage.value, self.picker_folder.value))
        if gate is not None and gate.locked:
            work.cancel.set()
        self._work = work
        self.set_cloud_busy(True)
        self.save_as_storage.enabled = False
        self.picker_parent.enabled = False
        self.picker_primary.enabled = False
        self.picker_new_folder.enabled = False
        return work

    def _accepts(self, work):
        client = getattr(self.app, 'cloud_client', None)
        return (self._work is work and work.epoch == self._epoch and self.active_host
                and not work.cancel.is_set() and client is work.client
                and getattr(client, 'generation', None) == work.credential_generation
                and self.app.navigation_generation == work.navigation
                and work.location == (self.save_as_storage.value, self.picker_folder.value)
                and (work.gate is None or (not work.gate.locked
                     and work.gate.revision == work.gate_revision)))

    def _finish_work(self, work):
        if self._work is work:
            self._work = None
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
        self.origin = self._capture_origin(owner, managed=False)
        self.save_as_source_document = None
        await self.show_text_destination(owner.crypt_reader.name, owner.crypt_reader.text_snapshot.encode(owner.crypt_text.value),
                                         privacy_gate=getattr(owner, 'privacy_gate', None))

    async def show_document_save_as(self, widget=None, **kwargs):
        if self.current is None:
            return
        source_document = self.current
        origin = self._capture_origin(self.app.editor_view, managed=True)
        name, data = source_document.name, source_document.snapshot.encode(source_document.text)
        if not hasattr(self, 'cloud_view'):
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
        if self.cloud_busy:
            return
        if not self.active_host:
            return
        if self.current is not source_document or origin is None or not self.app.workspace.accepts(origin.token):
            return
        self.origin = origin
        self.save_as_source_document = source_document
        await self.show_text_destination(name, data)

    async def show_editor_open(self, widget=None, **kwargs):
        if not hasattr(self, 'cloud_view'):
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
        if self.cloud_busy:
            return
        await self.show_editor_browser('open')

    async def show_text_destination(self, name, data, *, privacy_gate=None):
        self.save_as_privacy_gate = privacy_gate
        await self.show_editor_browser('save', name, data)

    async def show_document_creation(self, name, origin):
        self.origin = self.save_as_source_document = self.save_as_privacy_gate = None
        await self.show_editor_browser('save', name, b'', creation=origin)

    async def show_destination(self, name, action):
        self.origin = self.save_as_source_document = self.save_as_privacy_gate = None
        await self.show_editor_browser('destination', name, destination_action=action)

    async def show_editor_browser(self, mode, name='', data=None, *, creation=None, destination_action=None):
        if self.cloud_busy or not self.active_host:
            return
        self._epoch += 1
        if hasattr(self, 'editor_browser'):
            await self.editor_browser.close()
        if not self.active_host:
            return
        self.editor_picker_mode = mode
        self.creation = creation
        self.destination_action = destination_action
        self.save_as_data = data
        self.source_filename = name
        if mode == 'open':
            self.origin = None
            self.save_as_source_document = None
            self.save_as_privacy_gate = None
        ordinary = self.app.ordinary_file_roots()
        self.editor_storage_roots = ({'Local': None, 'All files': ordinary['Shared files'],
            'Received Files': ordinary['Received Files']} if creation is not None else {'Local files': None})
        if destination_action is not None:
            self.editor_storage_roots = dict(self.app.file_roots)
        self.editor_storage_roots.update(self.existing_crypt_locations())
        if creation is not None:
            # An unlocked encrypted root is also a valid destination before its
            # first offline file exists. Resolution still validates credentials.
            for remote in self.app.rclone_ui.visible_remotes(getattr(self.app, 'cloud_crypt_remotes', ())):
                self.editor_storage_roots.setdefault('LocalCrypt: ' + remote, remote)
        self.editor_linked_roots = self.linked_crypt_locations()
        self.editor_storage_roots.update(self.editor_linked_roots)
        source_store = getattr(getattr(self.origin, 'owner', None), '_crypt_reader_store', None)
        source_provider = getattr(source_store, 'provider', None)
        source_reader = getattr(getattr(self.origin, 'owner', None), 'crypt_reader', None)
        source_folder = ''
        source_label = None
        if mode == 'save' and creation is None and source_provider is not None and not getattr(source_provider, 'remote_storage', False):
            source_label = 'Source location'
            self.editor_storage_roots[source_label] = source_provider
            source_folder = (getattr(source_reader, 'key', '') or '').rpartition('/')[0]
        roots = list(self.editor_storage_roots)
        self.editor_picker_rows = {}
        self.save_as_storage = toga.Selection(items=roots, style=Pack(height=48))
        self.picker_folder = toga.TextInput(placeholder='Folder within storage', style=Pack(height=48))
        if source_label is not None:
            self.save_as_storage.value = source_label
            self.picker_folder.value = source_folder
        self.picker_entries = toga.Selection(style=Pack(height=48))
        from .browser_ui import FileBrowser as NativeBrowser
        self.editor_browser = NativeBrowser(folder_visible=self.folder_path_visible, selected=self.browser_editor_selected, open_folder=self.browser_editor_folder, navigate=self.browser_editor_location, open_file=self.browser_editor_file, contextual_selection=False, preview=False)
        self.save_as_name = toga.TextInput(value=name, placeholder='File name', style=Pack(height=48))
        self.effective_name = self.editor_browser.status_label('')
        self.save_as_name.on_change = self.update_effective_name
        self.update_effective_name()
        self.save_as_status = self.editor_browser.status_label('')
        title = 'Move' if destination_action is not None else 'New document' if creation is not None else 'Open file' if mode == 'open' else 'Save As'
        primary = 'Move here' if destination_action is not None else 'Create document' if creation is not None else 'Open file' if mode == 'open' else 'Save here'
        self.picker_parent = icon_button('up', 'Parent folder', on_press=self.parent_editor_folder)
        self.picker_header = self.editor_browser.attach_location_header(
            self.editor_browser.status_label(''), self.picker_parent)
        self.picker_destination = self.editor_browser.status_label('')
        self.picker_primary = toga.Button(primary, on_press=self.confirm_editor_file, style=Pack(height=48, flex=1))
        self.picker_new_folder = toga.Button('New folder', on_press=self.toggle_editor_new_folder, style=Pack(height=48))
        self.picker_header.add(self.picker_new_folder)
        self.new_folder_name = toga.TextInput(placeholder='New folder name', style=Pack(height=48, flex=1))
        from .keyboard import prepare_picker_input
        for control in (self.save_as_name, self.new_folder_name):
            prepare_picker_input(control)
        self.new_folder_form = toga.Box(children=[self.new_folder_name,
            toga.Button('Create', on_press=self.create_picker_folder, style=Pack(height=48)),
            toga.Button('Cancel', on_press=self.hide_new_folder, style=Pack(height=48))], style=Pack(direction=ROW))
        self.save_as_view = toga.Box(children=[toga.Label('Name' if destination_action is not None else 'File name'), self.save_as_name, self.effective_name,
            self.picker_destination, self.save_as_status], style=Pack(direction=COLUMN, margin=12))
        self.picker_actions = toga.Box(children=[
                toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)),
                self.picker_primary],
                style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
        self.picker_form = toga.ScrollContainer(content=self.save_as_view, horizontal=False,
                                                style=Pack(height=180))
        self._browse_controls = (self.save_as_storage, self.picker_header, self.editor_browser.scroll_container())
        panel = toga.Box(children=[*self._browse_controls, self.picker_form, self.picker_actions],
            style=Pack(direction=COLUMN, flex=1))
        from .ios_toolbar import prepare_form
        prepare_form(panel, primary=primary, cancel='Cancel')
        self.panel = panel
        self._compact_keyboard = False
        self.show_view(panel, route='text-destination', title=title)
        self.save_as_storage.on_change = self.change_editor_storage
        await self.refresh_editor_browser()

    def fit_keyboard(self, compact):
        """Keep naming and completion usable without reparenting the focused input."""
        if self.panel is None or not hasattr(self, 'picker_form') or getattr(self, '_fitting_keyboard', False):
            return
        from .keyboard import _tuck_control
        self._fitting_keyboard = True
        try:
            self._compact_keyboard = compact
            controls = self._browse_controls if compact else reversed(self._browse_controls)
            for control in controls:
                _tuck_control(control, compact)
            # A landscape Android IME can leave only ~100 logical pixels.
            # Put full-size completion buttons beside the scrollable form;
            # stacking both areas would squash the native buttons to a sliver.
            tight = compact and self.app.main_window.size.height < 220
            changes = ((self.panel, 'direction', ROW if tight else COLUMN),
                       (self.picker_actions, 'direction', COLUMN if tight else ROW),
                       (self.picker_actions, 'width', 112 if tight else NONE),
                       (self.picker_actions, 'margin_bottom', 0 if tight else 12))
            for control, field, value in changes:
                if getattr(control.style, field) != value:
                    setattr(control.style, field, value)
            flex = 1 if compact else 0
            if self.picker_form.style.flex != flex:
                self.picker_form.style.flex = flex
            scale = getattr(self.save_as_view._impl, 'scale_out', lambda value: value)
            natural = scale(self.save_as_view.layout.min_height) or 180
            height = NONE if compact else min(max(120, natural), max(120, self.app.main_window.size.height / 2))
            if self.picker_form.style.height != height:
                self.picker_form.style.height = height
        finally:
            self._fitting_keyboard = False

    def update_effective_name(self, widget=None, **kwargs):
        if self.editor_picker_mode != 'save':
            self.effective_name.text = ''
            return
        from .destination_names import save_filename
        try:
            self.effective_name.text = 'Save as: ' + save_filename(self.save_as_name.value, self.source_filename)
        except ValueError as error:
            self.effective_name.text = str(error)

    def update_picker_actions(self):
        ready = (not self.cloud_busy and self.editor_picker_location ==
                 (self.save_as_storage.value, self.picker_folder.value))
        client = getattr(self.app, 'cloud_client', None)
        ready = ready and self._listed_credentials == (client, getattr(client, 'generation', None))
        self.save_as_storage.enabled = not self.cloud_busy
        self.picker_parent.enabled = ready and bool(self.picker_folder.value)
        self.picker_primary.enabled = ready
        provider = self._listed_provider if ready else None
        writable = provider is not None and not getattr(provider, 'remote_storage', False)
        self.picker_new_folder.enabled = (self.editor_picker_mode != 'open' and writable
                                          and capabilities(provider).create)
        if self.editor_picker_mode != 'open':
            self.picker_primary.enabled = writable and all(
                getattr(capabilities(provider), key) for key in ('create', 'rename', 'delete'))
        self.fit_keyboard(getattr(self, '_compact_keyboard', False))

    def show_new_folder(self, widget=None, **kwargs):
        if not self.picker_new_folder.enabled:
            return
        self.new_folder_name.value = ''
        if self.new_folder_form not in self.save_as_view.children:
            self.save_as_view.insert(1, self.new_folder_form)
        self.new_folder_name.focus()

    def hide_new_folder(self, widget=None, **kwargs):
        if hasattr(self, 'new_folder_form') and self.new_folder_form in self.save_as_view.children:
            self.save_as_view.remove(self.new_folder_form)

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
        work = self._begin_work()
        plan = None
        try:
            name = resource_name(self.save_as_name.value)
            provider = self.editor_provider(self.save_as_storage.value)
            target = '/'.join(p for p in (self.picker_folder.value, name) if p)
            action = self.destination_action
            source = action.provider
            if source.private and not provider.private:
                confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                    'Move to unencrypted storage?',
                    'The destination will contain a decrypted copy. Continue?'))
                if not confirmed or not self._accepts(work):
                    return
            from .file_operations import FileOperationRequest, FileDestination
            destination = FileDestination(self.app.private_root, work.client, provider, work.credential_generation)
            request = FileOperationRequest('move', source, action.path, target, destination,
                                           plaintext_approved=source.private and not provider.private)
            # Use the same guarded, verified mutation as other file commands.
            from .document_mutations import prepare_document_mutation
            from .file_operations import retiring_work
            plan = await prepare_document_mutation(self.app, request)
            await retiring_work(plan.execute, work.cancel, completed=plan.apply)
            if not self._accepts(work):
                return
            self._finish_work(work)
            self.clear()
            await self.app.show_files()
            await self.app.browse_files()
            self.app.file_status.value = 'Move finished. Destination verified before removing the source.'
        except Exception as error:
            if self._accepts(work):
                self.save_as_status.value = 'Move failed: ' + str(error)[:250] + '\nRefresh before retrying; inspect both locations.'
        finally:
            if plan is not None:
                plan.release()
            self._finish_work(work)

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
        if not row['directory'] and self.creation is None and self.destination_action is None:
            self.save_as_name.value = row['name']

    async def browser_editor_file(self, row):
        """A search hit names a file in its own containing folder."""
        if self.cloud_busy:
            return
        folder = row['path'].rpartition('/')[0]
        if folder != self.picker_folder.value:
            await self.browser_editor_location((self.save_as_storage.value, folder))

    def toggle_editor_new_folder(self, widget=None, **kwargs):
        if self.new_folder_form in self.save_as_view.children:
            self.hide_new_folder()
        else:
            self.show_new_folder()

    async def create_editor_folder(self, widget=None, **kwargs):
        return await self.create_picker_folder()

    async def browser_editor_folder(self, row):
        if self.cloud_busy:
            return False
        return await self.browser_editor_location((self.save_as_storage.value, row['path']))

    async def browser_editor_location(self, location):
        if self.cloud_busy:
            return False
        self._changing_location = True
        try:
            self.save_as_storage.value, self.picker_folder.value = location
        finally:
            self._changing_location = False
        return await self.refresh_editor_browser()

    def change_editor_storage(self, widget=None, **kwargs):
        if getattr(self, '_changing_location', False):
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
        self.picker_folder.value = ''
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
        work = self._begin_work()
        self.save_as_status.value = 'Loading folder…'
        try:
            model = ResourceSelection(self.editor_provider(label), mode=self.editor_picker_mode,
                                      extensions=() if self.destination_action is not None else SOURCE_EXTENSIONS)
            rows = await asyncio.to_thread(model.list, folder, cancelled=work.cancel.is_set)
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
            self.picker_parent.enabled = bool(folder)
            privacy = 'Encrypted' if model.provider.private else 'Plaintext'
            self.picker_destination.text = f'{label} / {folder or "Root"} · {privacy}'
            self.save_as_status.value = ''
            return True
        except Exception as error:
            if not self._accepts(work):
                return False
            if self.editor_browser.tree is not None:
                self._changing_location = True
                try:
                    self.save_as_storage.value, self.picker_folder.value = self.editor_picker_location
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
        if not self.cloud_busy:
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
            else:
                if self.creation is None:
                    self.save_as_name.value = row['name']

    async def confirm_editor_file(self, widget=None, **kwargs):
        pending = getattr(self, '_storage_refresh', None)
        if pending is not None:
            await pending
        if self.destination_action is not None:
            return await self.complete_destination()
        if self.editor_picker_mode == 'save':
            return await self.save_text_destination()
        if self.cloud_busy:
            return
        from features.text_editor.resources import LocalTextCopies
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
        await self.open_crypt(copies=encrypted_copies(provider) if provider.private else LocalTextCopies(provider), key=path, edit=True)

    def cancel_text_destination(self, widget=None, *, dismissed=False, **kwargs):
        visible = dismissed or self.visible()
        if self._work is not None:
            self.cancel()
            if self.origin is not None or self.destination_action is not None or self.creation is not None:
                self._restore_when_idle = (self.app.navigation_generation, dismissed)
            self.save_as_status.value = 'Cancelling the operation. Your draft remains available.'
            return
        if not self.cloud_busy:
            origin = self.origin
            creation = self.creation
            destination_action = self.destination_action
            self.clear()
            if visible:
                if destination_action is not None:
                    return self.app.loop.create_task(self.app.show_files())
                if creation is not None:
                    return self.app.routes.back()
                return self._restore_origin(origin)


    async def save_text_destination(self, widget=None, **kwargs):
        from commonUtils.runtime.resources.mutations import save_resource_and_reopen
        from features.text_editor.resources import LocalTextCopies
        if self.cloud_busy or self.save_as_data is None:
            return
        target, label, data = self.save_as_name.value, self.save_as_storage.value, self.save_as_data
        folder = self.picker_folder.value
        creation = self.creation
        work = self._begin_work()
        try:
            from .destination_names import save_filename
            target = save_filename(target, self.source_filename)
            self.save_as_name.value = target
            if Path(target).suffix.lower() not in SOURCE_EXTENSIONS or len(data) > 1024 * 1024:
                raise ValueError('Choose a text, source or configuration filename; saves are limited to 1 MiB.')
            provider = self.editor_provider(label)
            if creation is not None:
                from features.text_editor.names import document_name
                from .workspace import MAX_SESSIONS
                if len(self.app.workspace.sessions) >= MAX_SESSIONS:
                    raise ValueError('Close an open document before creating another (limit: 32).')
                document_name(target)
                if Path(target).suffix.lower() not in {'.txt', '.md', '.markdown'}:
                    raise ValueError('Choose a TXT or Markdown filename.')
                if getattr(provider, 'remote_storage', False):
                    raise ValueError('Cloud files are read-only. Create locally and use Push.')
            source_document = self.save_as_source_document
            store = self.store
            privacy_gate = self.save_as_privacy_gate
            def resolve_destination():
                model = ResourceSelection(provider, mode='save', extensions=SOURCE_EXTENSIONS)
                try:
                    return model.resolve(folder, target, cancelled=work.cancel.is_set), None
                except FileExistsError:
                    # Resolve validated the path, parent and write capabilities.
                    destination = '/'.join(part for part in (model.relative(folder), target) if part)
                    entry = provider.entry(destination)
                    if entry['directory']:
                        raise ValueError('A folder with this name already exists. Choose another name.')
                    if creation is not None:
                        raise FileExistsError('A destination with this name already exists. Choose another name.')
                    return destination, entry['revision']
            destination, revision = await asyncio.to_thread(resolve_destination)
            if not self._accepts(work):
                return
            if revision is not None:
                confirmed = await self.app.main_window.dialog(toga.ConfirmDialog(
                    f'Replace “{Path(target).name}”?',
                    f'A file with this name already exists in {folder or label}. '
                    'Replacing it will overwrite its contents.'))
                if not self._accepts(work) or not confirmed:
                    return
                if (target, label, folder) != (self.save_as_name.value, self.save_as_storage.value, self.picker_folder.value):
                    self.save_as_status.value = 'Destination changed. Save again to confirm the new destination.'
                    return
            def save():
                if provider.private and source_document is not None:
                    store.privatize(source_document)
                copies = encrypted_copies(provider) if provider.private else LocalTextCopies(provider)
                def reopen():
                    reader = copies.open(destination)
                    if reader.data != data:
                        raise ValueError('The saved file changed after publication.')
                    kind, content = reader.page(0)
                    return copies, destination, (reader, kind, content)
                return save_resource_and_reopen(provider, destination, data, reopen=reopen, expected_revision=revision, cancelled=work.cancel.is_set)
            copies, destination, prepared = await asyncio.to_thread(save)
            if not self._accepts(work):
                return
            epoch = self._epoch
            self._finish_work(work)
            if creation is not None:
                route_destination, count, details = creation
                if route_destination == 'documents' and self.app.adaptive.split is not None:
                    self.app.adaptive.trim_details(details)
                else:
                    self.app.routes.trim(route_destination, count)
            opened = await self.open_crypt(copies=copies, key=destination, prepared=prepared,
                                    privacy_gate=privacy_gate, edit=creation is not None)
            if not self.active_host or epoch != self._epoch:
                return
            if opened:
                self.origin = self.panel = None
                self.creation = None
                self.save_as_data = None
                self.save_as_privacy_gate = None
                if source_document is not None and getattr(source_document, 'private', False):
                    source_document.text = source_document.snapshot.text
                    self.app.finish_save_as_source(source_document)
                self.save_as_source_document = None
            else:
                self.save_as_status.value = ('The file was created in the chosen folder, but its editor could not be opened.'
                    if creation is not None else 'The file was saved, but its editor could not be opened. The Save As draft is retained.')
                self.show_view(self.panel, route='text-destination', title='New document' if creation is not None else 'Save As')
        except MutationIncomplete as error:
            if not self._accepts(work):
                return
            self.save_as_status.value = str(error) + ('\nRefresh the folder before retrying.' if creation is not None
                else '\nRefresh before retrying; your draft remains available.')
        except Exception as error:
            if not self.active_host or work.epoch != self._epoch or work.cancel.is_set():
                return
            self.save_as_status.value = ('Creation failed: ' if creation is not None else 'Save As failed; draft retained: ') + str(error)[:200]
        finally:
            self._finish_work(work)

