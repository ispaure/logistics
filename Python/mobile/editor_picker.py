"""Owned Open/Save As workflow; picker state never falls back to app attributes."""
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

import asyncio
from pathlib import Path
import threading
from dataclasses import dataclass, replace

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, NONE
from commonUtils.runtime.operations import MutationIncomplete
from commonUtils.runtime.resources.selection import ResourceSelection
from commonUtils.runtime.resources.paths import resource_name
from commonUtils.runtime.resources.provider import capabilities
from .control_icons import icon_button
from services.workflow_host import HostService, StateAttribute


class PickerMessage(toga.Box):
    """A message only occupies space when present; it is never a text field."""
    def __init__(self, width):
        from commonUtils.ui.native.forms import FittedLabel, fit_text
        self.label = FittedLabel('', style=Pack(font_size=14, margin_top=8))
        fit_text(self.label, max(120, width - 48))
        super().__init__(style=Pack(direction=COLUMN))

    @property
    def value(self):
        return self.label.text

    @value.setter
    def value(self, message):
        self.label.text = message
        if message and not self.children:
            self.add(self.label)
        elif not message and self.children:
            self.remove(self.label)


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
    privacy_gate: object = None
    origin: PickerOrigin | None = None
    creation: tuple | None = None
    binary_owner: object = None
    destination_action: object = None
    filename: str = ''
    mode: str = ''


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
        self.app = app
        self.operation = PickerOperation()
        self.editor_picker_rows = {}
        self.editor_picker_location = None
        self.editor_storage_roots = {}
        self.editor_linked_roots = {}
        self._work = None
        self._epoch = 0
        self.panel = None
        self._restore_when_idle = None
        self.creation_layout = None
        self.name_panel = None
        self.location_panel = None
        self.creation_type = None
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
        self.creation_layout = None
        self.name_panel = self.location_panel = None
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
        self.editor_linked_roots = {}
        if hasattr(self, 'editor_browser'):
            self.editor_browser.stop()
        if hasattr(self, 'creation_location'):
            self.creation_location.crumbs.clear()
        if hasattr(self, 'picker_destination'):
            self.picker_destination.text = ''
            self.picker_header.folder_name.text = ''
            self.picker_header.status.value = ''
        if hasattr(self, 'picker_entries'):
            self.picker_entries.items = []
            self.picker_folder.value = ''
            self.save_as_name.value = ''
            self.new_folder_name.value = ''
            self.save_as_storage.items = []
            self.save_as_status.value = ''

        # Drop the retained private source only after its displayed labels clear.
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
        self.save_as_storage.enabled = False
        self.picker_parent.enabled = False
        self.picker_primary.enabled = False
        if self.location_panel is not None:
            self.edit_name.enabled = False
            self.creation_location.set_enabled(False)
            self.creation_type.enabled = self.save_as_name.enabled = False
            self.creation_formats.set_enabled(False)
        self.picker_new_folder.enabled = False
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
        operation = PickerOperation(origin=self._capture_origin(owner, managed=False))
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
        operation = PickerOperation(origin=self._capture_origin(panel, managed=False),
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

    async def show_destination(self, name, action):
        await self.show_editor_browser('destination', name, destination_action=action)

    async def show_editor_browser(self, mode, name='', data=None, *, creation=None, destination_action=None, operation=None):
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
        self.creation_layout = None
        self.name_panel = self.location_panel = None
        self.editor_picker_location = self._listed_provider = self._listed_credentials = None
        self.operation = operation
        from .protection import for_app
        for_app(self.app).changed()
        ordinary = self.app.ordinary_file_roots(
            include_collections=getattr(destination_action, 'kind', '') != 'download')
        self.editor_storage_roots = ({'All files': ordinary['Shared files'], 'Local': None,
            'Received Files': ordinary['Received Files']} if creation is not None else {'Local files': None})
        if destination_action is not None:
            self.editor_storage_roots = dict(ordinary if getattr(destination_action, 'kind', '') == 'download' else self.app.file_roots)
        if self.app.feature_enabled('rclone'):
            if getattr(destination_action, 'kind', '') == 'download':
                unlocked = {}
                existing = self.existing_crypt_locations(roots=unlocked)
                # A loaded cipher is also a valid destination before its first
                # local file exists. Resolution creates that LocalCrypt lazily.
                self.editor_storage_roots.update({label: location[0] for label, location in unlocked.items()})
            else:
                existing = self.existing_crypt_locations()
            self.editor_storage_roots.update(existing)
        self.editor_linked_roots = self.linked_crypt_locations() if self.app.feature_enabled('rclone') else {}
        self.editor_storage_roots.update(self.editor_linked_roots)
        source_store = getattr(getattr(self.operation.origin, 'owner', None), '_crypt_reader_store', None)
        source_provider = getattr(source_store, 'provider', None)
        source_reader = getattr(getattr(self.operation.origin, 'owner', None), 'crypt_reader', None)
        if self.operation.binary_owner is not None and self.operation.binary_owner.document is not None:
            source_provider = getattr(self.operation.binary_owner.document.resource, 'provider', None)
        source_folder = ''
        source_label = None
        if mode == 'save' and creation is None and source_provider is not None and not getattr(source_provider, 'remote_storage', False):
            source_label = 'Source location'
            self.editor_storage_roots[source_label] = source_provider
            source_folder = (self.operation.binary_owner.document.resource.path if self.operation.binary_owner is not None
                             else getattr(source_reader, 'key', '') or '').rpartition('/')[0]
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
        self.creation_type = None
        if creation is not None:
            from .document_choices import available_choices
            CHOICES = self.creation_choices = available_choices(self.app)
            self.creation_type = toga.Selection(items=[label for label, extension in CHOICES],
                                                 style=Pack(height=48))
            suffix = Path(name).suffix.lower().removeprefix('.')
            self.creation_type.value = next((label for label, extension in CHOICES
                if extension == ('md' if suffix == 'markdown' else suffix)), CHOICES[0][0])
            self.creation_type.on_change = self.change_creation_type
            self.operation.filename = 'Untitled.' + dict(CHOICES)[self.creation_type.value]
        self.effective_name = self.editor_browser.status_label('')
        self.effective_name.style.flex = 0
        self.save_as_name.on_change = self.update_effective_name
        self.update_effective_name()
        self.save_as_status = PickerMessage(self.app.main_window.size.width)
        self.move_progress = toga.ProgressBar(max=None)
        self.move_notice = toga.Box(style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
        title = getattr(destination_action, 'title', 'Move') if destination_action is not None else 'New document' if creation is not None else 'Open file' if mode == 'open' else 'Save As'
        primary = getattr(destination_action, 'primary', 'Move here') if destination_action is not None else 'Create here' if creation is not None else 'Open file' if mode == 'open' else 'Save here'
        self.picker_parent = icon_button('up', 'Parent folder', on_press=self.parent_editor_folder)
        self.picker_header = self.editor_browser.attach_location_header(
            self.editor_browser.status_label(''), self.picker_parent)
        if creation is not None:
            self.picker_parent.on_press = self.parent_editor_folder
        if creation is not None:
            from commonUtils.ui.native.forms import FittedLabel, fit_text
            self.picker_destination = FittedLabel('', style=Pack(font_size=13))
            fit_text(self.picker_destination, max(120, self.app.main_window.size.width - 48))
        else:
            self.picker_destination = self.editor_browser.status_label('')
        self.picker_destination.style.flex = 0
        from .appearance import action_button
        self.picker_primary = action_button(toga.Button(primary, on_press=self.confirm_editor_file, style=Pack(height=48, flex=1)))
        self.picker_new_folder = toga.Button('New folder', on_press=self.toggle_editor_new_folder, style=Pack(height=48))
        self.new_folder_name = toga.TextInput(placeholder='New folder name', style=Pack(height=48, flex=0 if creation is not None else 1))
        from .keyboard import prepare_picker_input
        for control in (self.save_as_name, self.new_folder_name):
            prepare_picker_input(control)
        folder_actions = toga.Box(children=[toga.Button('Create folder' if creation is not None else 'Create', on_press=self.create_picker_folder, style=Pack(height=48)),
            toga.Button('Cancel', on_press=self.hide_new_folder, style=Pack(height=48))], style=Pack(direction=ROW))
        self.new_folder_form = toga.Box(children=[self.new_folder_name, folder_actions], style=Pack(
            direction=COLUMN if creation is not None else ROW))
        name_fields = [toga.Label('Name' if destination_action is not None else 'File name'), self.save_as_name]
        location_fields = [self.picker_destination, self.save_as_status]
        if creation is not None:
            self.save_as_name.on_confirm = self.choose_creation_location
            self.name_view = toga.Box(children=[*name_fields, self.effective_name],
                style=Pack(direction=COLUMN, margin=20))
            from .creation_layout import CreationFormats, CreationNameForm
            self.creation_formats = CreationFormats(self)
            self.name_form = CreationNameForm(content=self.name_view, horizontal=False, style=Pack(flex=1))
            self.next_button = toga.Button('Next', on_press=self.choose_creation_location,
                                           style=Pack(height=48, flex=1), enabled=self._creation_name_valid)
            self.name_actions = toga.Box(children=[
                toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)),
                self.next_button], style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
            self.name_content = toga.Box(children=[self.name_form], style=Pack(direction=COLUMN, flex=1))
            self.creation_formats.fit(False, 0, self.app.main_window.size.width)
            self.name_panel = toga.Box(children=[self.name_content, self.name_actions], style=Pack(direction=COLUMN, flex=1))
            self.save_as_view = toga.Box(children=location_fields,
                                        style=Pack(direction=COLUMN, margin_left=12, margin_right=12))
        else:
            self.save_as_view = toga.Box(children=[*name_fields, self.effective_name, *location_fields],
                                        style=Pack(direction=COLUMN, margin=12))
        self.picker_actions = toga.Box(children=[
                toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)),
                self.picker_primary],
                style=Pack(direction=ROW, margin_left=12, margin_right=12, margin_bottom=12))
        self.picker_form = toga.ScrollContainer(content=self.save_as_view, horizontal=False,
                                                style=Pack(height=80 if creation is not None else 180))
        # Keep the named action outside the compact location header: that
        # header reserves icon-sized slots and truncates "New folder" on phones.
        storage_row = self.save_as_storage
        if creation is not None and not type(self.save_as_storage._impl).__module__.startswith('toga_iOS.'):
            self.save_as_storage.style.flex = 1
            storage_row = toga.Box(children=[self.save_as_storage], style=Pack(direction=ROW))
        self._browse_controls = (storage_row, self.picker_header,
                                 self.picker_new_folder, self.editor_browser.scroll_container())
        if creation is not None:
            from .creation_layout import CreationLocation
            self.creation_location = CreationLocation(self)
            apple = type(self.save_as_storage._impl).__module__.startswith('toga_iOS.')
            self._browse_controls = (*(() if apple else (self.creation_location.heading,)),
                self.creation_location.storage, self.creation_location.header,
                self.editor_browser.scroll_container())
        contents = [*self._browse_controls, self.picker_form, self.picker_actions]
        panel = toga.Box(children=contents,
            style=Pack(direction=COLUMN, flex=1))
        from .ios_toolbar import prepare_form
        if creation is not None:
            self.location_panel = panel
            from .creation_layout import CreationLayout
            self.creation_layout = CreationLayout(self)
            self.listed_path = ''
        else:
            prepare_form(panel, primary=primary, cancel='Cancel')
        self.panel = panel
        self._compact_keyboard = False
        self._naming_keyboard_active = False
        self.save_as_storage.on_change = self.change_editor_storage
        if creation is not None:
            self.show_creation_name()
            if self.creation_layout.paired:
                # Both panes are usable immediately on large allocations.
                await self.load_picker_location()
            return
        self.show_view(panel, route='text-destination', title=title)
        await self.load_picker_location()

    def show_creation_name(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        returning = self.visible()
        self.hide_new_folder()
        self.fit_keyboard(False)
        self.panel = self.name_panel
        self.next_button.enabled = self._creation_name_valid
        self.creation_layout.reflow()
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
        self.fit_keyboard(False)
        self.panel = self.location_panel
        from .keyboard import dismiss_picker_keyboard
        dismiss_picker_keyboard(self)
        self.creation_layout.reflow()
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

    def fit_keyboard(self, compact):
        """Keep naming and completion usable without reparenting the focused input."""
        if self.panel is None or not hasattr(self, 'picker_form') or getattr(self, '_fitting_keyboard', False):
            return
        from .keyboard import _tuck_control, reset_picker_keyboard
        self._fitting_keyboard = True
        try:
            self._compact_keyboard = compact
            apple = type(self.app._impl).__module__.startswith('toga_iOS.')
            if apple and not compact:
                reset_picker_keyboard(self)
            def focused(control):
                return bool(getattr(getattr(control._impl, 'native', None), 'isFirstResponder', False))
            if not compact or not apple or focused(self.save_as_storage):
                self._naming_keyboard_active = False
            elif focused(self.save_as_name) or focused(self.new_folder_name):
                self._naming_keyboard_active = True
            naming = self.panel is self.name_panel
            paired = self.creation_layout is not None and self.creation_layout.paired
            controls = () if naming else self._browse_controls
            editing_folder = self.entering_creation_folder()
            hide_browser = editing_folder or (compact and not paired)
            if not hide_browser:
                controls = reversed(controls)
            for control in controls:
                # iOS Selection opens a keyboard inputView. Removing its text
                # field here immediately resigns focus and closes that picker.
                # A location read briefly disables the field and drops focus;
                # preserve its input-view session until typing or keyboard hide.
                preserve_selector = ((control is self.save_as_storage or
                    (self.creation_type is not None and control is self.creation_location.storage)) and apple
                    and not self._naming_keyboard_active)
                _tuck_control(control, hide_browser and (editing_folder or not preserve_selector))
            # A landscape keyboard can leave only ~100 logical pixels.
            # Put full-size completion buttons beside the scrollable form;
            # stacking both areas would squash the native buttons to a sliver.
            visible_height = self.app.main_window.size.height
            # UIKit keeps the outer window size and reserves the keyboard in
            # safe-area insets. Android already reports its resized viewport.
            if compact and type(self.app._impl).__module__.startswith('toga_iOS.'):
                visible_height -= self.app.native_host.adapter.keyboard_inset
            if self.creation_type is not None:
                width = (self.name_panel.style.width if paired else
                         self.app.adaptive.content_width(self.app.native_host.state.destination, margin=0))
                self.creation_formats.fit(compact, visible_height - 120, width)
            # Creation's UIKit completion lives in its native navigation bar.
            # Other picker forms retain their existing short-viewport layout.
            tight = (compact and not paired and visible_height < 220
                     and (not apple or self.creation_type is None))
            actions = self.name_actions if naming else self.picker_actions
            changes = ((self.panel, 'direction', ROW if tight else COLUMN),
                       (actions, 'direction', COLUMN if tight else ROW),
                       (actions, 'width', 112 if tight else NONE),
                       (actions, 'margin_bottom', 0 if tight else 12))
            for control, field, value in changes:
                if getattr(control.style, field) != value:
                    setattr(control.style, field, value)
            expand_form = naming or editing_folder or (compact and not paired)
            flex = 1 if expand_form else 0
            form = self.name_form if naming else self.picker_form
            if form.style.flex != flex:
                form.style.flex = flex
            # Travertino layout sizes already use logical units. Scaling them
            # out again clips the status area on high-density Android screens.
            natural = self.save_as_view.layout.min_height or 180
            minimum = 72 if self.location_panel is not None else 120
            height = NONE if expand_form else min(max(minimum, natural), max(minimum, self.app.main_window.size.height / 2))
            if form.style.height != height:
                form.style.height = height
        finally:
            self._fitting_keyboard = False
        pending = getattr(self, '_keyboard_reveal', None)
        if pending is not None:
            pending.cancel()
            self._keyboard_reveal = None
        if compact and type(self.app._impl).__module__.startswith('toga_iOS.'):
            # UIKit and Toga resize the scroll viewport after the keyboard/rotation
            # callback. Reveal the existing first responder in that final layout.
            panel = self.panel
            def reveal():
                self._keyboard_reveal = None
                if self.panel is panel and self._compact_keyboard and self.active_host and self.visible():
                    from .keyboard import reveal_picker_input
                    reveal_picker_input(self)
            self._keyboard_reveal = self.app.loop.call_soon(reveal)

    def update_effective_name(self, widget=None, **kwargs):
        if self.operation.mode != 'save':
            self.effective_name.text = ''
            return
        try:
            self.effective_name.text = 'Save as: ' + self.destination_filename()
            self._creation_name_valid = True
        except ValueError as error:
            self._creation_name_valid = False
            self.effective_name.text = str(error) if self.save_as_name.value else 'Enter a file name.'
        if self.name_panel is not None:
            self.next_button.enabled = self._creation_name_valid
            if self.listed_path:
                self.update_creation_summary()
        if self.operation.creation is not None and self.save_as_name.parent is not None and self.visible():
            self.update_picker_actions()

    def update_creation_summary(self):
        name = self.destination_filename() if self._creation_name_valid else 'Enter a valid file name'
        self.picker_destination.text = f'{name}\nIn {self.listed_path}'

    def destination_filename(self):
        if self.operation.creation is not None:
            from .document_choices import creation_filename
            return creation_filename(self.save_as_name.value, dict(self.creation_choices)[self.creation_type.value])
        from .destination_names import save_filename
        return save_filename(self.save_as_name.value, self.operation.filename, extensions=self.picker_extensions())

    def change_creation_type(self, widget=None, **kwargs):
        from .document_choices import change_creation_suffix
        extension = dict(self.creation_choices)[self.creation_type.value]
        self.operation.filename = 'Untitled.' + extension
        self.save_as_name.value = change_creation_suffix(self.save_as_name.value, extension)
        self.creation_formats.update()
        self.update_effective_name()

    def creating_notebook(self):
        return (self.operation.creation is not None or self.operation.binary_owner is not None) and Path(self.operation.filename).suffix.lower() == '.rmdoc'

    def picker_extensions(self):
        if self.operation.destination_action is not None:
            return ()
        # Creation keeps all supported document types visible while the user
        # switches format; Save As retains its existing format-specific filter.
        if self.operation.creation is not None:
            return ('.txt', '.md', '.markdown', '.rmdoc')
        return ('.rmdoc',) if self.creating_notebook() else SOURCE_EXTENSIONS

    def has_parent_folder(self):
        return bool(self.picker_folder.value) or (self.operation.creation is not None
            and self.save_as_storage.value in ('Local', 'Received Files'))

    def update_picker_actions(self):
        ready = (not self.cloud_busy and self.editor_picker_location ==
                 (self.save_as_storage.value, self.picker_folder.value))
        client = getattr(self.app, 'cloud_client', None)
        ready = ready and self._listed_credentials == (client, getattr(client, 'generation', None))
        self.save_as_storage.enabled = not self.cloud_busy
        self.save_as_name.enabled = self._work is None
        if self.creation_type is not None:
            self.creation_type.enabled = self._work is None
            self.creation_formats.set_enabled(self._work is None)
        self.picker_parent.enabled = ready and self.has_parent_folder()
        if self.location_panel is not None:
            self.edit_name.enabled = not self.cloud_busy
            self.creation_location.set_enabled(ready and not self.entering_creation_folder())
            self.save_as_name.enabled = self._work is None
        self.picker_primary.enabled = ready
        provider = self._listed_provider if ready else None
        writable = provider is not None and not getattr(provider, 'remote_storage', False)
        from .local_sources import DeviceFiles
        if isinstance(provider, DeviceFiles) and not self.picker_folder.value:
            writable = False
        self.picker_new_folder.enabled = (self.operation.mode != 'open' and writable
                                          and capabilities(provider).create)
        if self.operation.mode != 'open':
            self.picker_primary.enabled = writable and all(
                getattr(capabilities(provider), key) for key in ('create', 'rename', 'delete'))
            if self.operation.creation is not None:
                self.picker_primary.enabled = (self.picker_primary.enabled and self._creation_name_valid
                                               and not self.entering_creation_folder())
            virtual_root = ready and isinstance(provider, DeviceFiles) and not self.picker_folder.value
            self.picker_primary.text = ('Choose a folder first' if virtual_root and self.operation.creation is None else
                getattr(self.operation.destination_action, 'primary', 'Move here') if self.operation.destination_action is not None else
                'Create here' if self.operation.creation is not None else 'Save here')
            if virtual_root:
                self.save_as_status.value = ('Open a folder to create your document here.'
                    if self.operation.creation is not None else
                    'Choose Local or Received Files above, then choose or create a folder.')
        self.fit_keyboard(getattr(self, '_compact_keyboard', False))

    def entering_creation_folder(self):
        return self.creation is not None and self.new_folder_form in self.save_as_view.children

    def show_new_folder(self, widget=None, **kwargs):
        if not self.picker_new_folder.enabled:
            return
        if self.creation is not None:
            self.panel = self.location_panel
            self.creation_layout.reflow()
        self.new_folder_name.value = ''
        if self.new_folder_form not in self.save_as_view.children:
            self.save_as_view.insert(1, self.new_folder_form)
        if self.creation is not None:
            self.update_picker_actions()
        self.new_folder_name.focus()

    def hide_new_folder(self, widget=None, **kwargs):
        if hasattr(self, 'new_folder_form') and self.new_folder_form in self.save_as_view.children:
            if self.creation is not None:
                if self._work is not None:
                    return
                from .keyboard import dismiss_picker_keyboard
                dismiss_picker_keyboard(self, self.new_folder_name)
            self.save_as_view.remove(self.new_folder_form)
            if self.creation is not None:
                if self.save_as_status.value.startswith('Folder creation failed:'):
                    self.save_as_status.value = ''
                self.update_picker_actions()

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
        if getattr(self.operation.destination_action, 'kind', '') == 'download':
            return await self.complete_download()
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
            # Keep progress above the browser rather than below the naming
            # fields in its short scroll viewport (not visible on closed Duo).
            if self.save_as_status.parent is not self.move_notice:
                self.save_as_status.parent.remove(self.save_as_status)
                self.move_notice.add(self.save_as_status)
            if self.move_progress.parent is None:
                self.move_notice.add(self.move_progress)
            if self.move_notice.parent is None:
                self.panel.insert(0, self.move_notice)
            self.move_progress.max = None
            self.move_progress.start()
            name = resource_name(self.save_as_name.value)
            provider = self.editor_provider(self.save_as_storage.value)
            target = '/'.join(p for p in (self.picker_folder.value, name) if p)
            action = self.operation.destination_action
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
                                           plaintext_approved=source.private and not provider.private)
            # Use the same guarded, verified mutation as other file commands.
            from .document_mutations import prepare_document_mutation
            from .file_operations import retiring_work
            plan = await prepare_document_mutation(self.app, request,
                progress=lambda **values: work.progress.publish(values))
            def completed(result):
                work.committed = True
                plan.apply(result)
            await retiring_work(plan.execute, work.cancel, completed=completed)
            if not self._accepts(work):
                return
            self._finish_work(work)
            self.clear()
            await self.app.show_files()
            await self.app.browse_files()
            self.app.file_status.value = 'Move finished. Destination verified before removing the source.'
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
            return await operation.destination_action.complete(self.app, destination, target)
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
        if not row['directory'] and self.operation.creation is None and self.operation.destination_action is None:
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
        if self.cloud_busy or self.entering_creation_folder():
            return False
        label, folder = location
        download = getattr(self.operation.destination_action, 'kind', '') == 'download'
        if (self.operation.creation is not None and label == 'All files') or (download and label == 'Shared files'):
            # Collection roots have their own providers, just as in Workspaces.
            # In particular, iOS protects the shared Local directory itself.
            from services.documents.locations import collection_path
            from .incoming_files import inbox_path
            for name, root in (('Local files' if download else 'Local', collection_path(self.app.private_root)),
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
        if self.creation is not None:
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
        previous_destination = self.picker_destination.text
        if self.creation is not None:
            self.picker_destination.text = ''
        self.save_as_status.value = 'Loading folder…'
        try:
            model = ResourceSelection(self.editor_provider(label), mode=self.operation.mode,
                                      extensions=self.picker_extensions())
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
            if self.creation is not None:
                from .control_icons import apply_icon
                apply_icon(self.picker_parent, 'up', 'Parent folder')
            self.picker_parent.enabled = self.has_parent_folder()
            privacy = 'Encrypted' if model.provider.private else 'Plaintext'
            path = f'{label} / {folder or "Root"} · {privacy}'
            if self.creation is not None:
                self.creation_location.update(label, folder)
                self.listed_path = ' › '.join([label, *filter(None, folder.split('/'))]) + f' · {privacy}'
                self.update_creation_summary()
            else:
                self.picker_destination.text = path
            self.save_as_status.value = ('Create a folder, or save here.'
                if self.creation is not None and not rows and capabilities(model.provider).create else '')
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
        if not self.cloud_busy and not self.entering_creation_folder():
            if (not self.picker_folder.value and self.operation.creation is not None
                    and self.save_as_storage.value in ('Local', 'Received Files')):
                return await self.browser_editor_location(('All files', ''))
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
                if self.operation.creation is None:
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
            if self.operation.origin is not None or self.operation.destination_action is not None or self.operation.creation is not None:
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


    async def save_text_destination(self, widget=None, **kwargs):
        from services.documents.storage import DocumentResource
        from services.documents.destinations import DestinationRequest
        from .workspace import MAX_SESSIONS
        if self.cloud_busy or self.operation.data is None or self.entering_creation_folder():
            return
        target, label = self.save_as_name.value, self.save_as_storage.value
        folder = self.picker_folder.value
        if not self.app.require_document_feature(self.operation.filename):
            return
        work = self._begin_work()
        operation = work.presentation
        data, creation = operation.data, operation.creation
        try:
            notebook = self.creating_notebook()
            extensions = self.picker_extensions()
            target = self.destination_filename()
            self.save_as_name.value = target
            provider = self.editor_provider(label)
            if (provider.private or getattr(provider, 'remote_storage', False)) and not self.app.require_feature('rclone'):
                return
            source_document = operation.source_document
            privacy_gate = operation.privacy_gate
            request = DestinationRequest.capture(provider, folder, target, data, extensions,
                notebook=notebook, creating=creation is not None,
                session_count=len(self.app.workspace.sessions), session_limit=MAX_SESSIONS, store=self.store,
                source_document=source_document)
            if operation.binary_owner is not None:
                from services.documents.storage import DocumentPolicy
                source = operation.binary_owner.document.resource
                if source is not None and source.policy.confirm_plaintext(DocumentPolicy.for_provider(provider)):
                    if not await self.app.main_window.dialog(toga.ConfirmDialog(
                            'Save to unencrypted storage?', 'The destination will contain a decrypted copy. Continue?')) or not self._accepts(work):
                        return
            destination, revision = await asyncio.to_thread(request.resolve, cancelled=work.cancel.is_set)
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
            publication = await asyncio.to_thread(request.publish, destination, revision,
                                                   cancelled=work.cancel.is_set)
            if not self._accepts(work):
                return
            copies, destination, prepared = publication.require_reopened()
            epoch = self._epoch
            self._finish_work(work)
            if creation is not None:
                route_destination, count, details = creation
                if route_destination == 'documents' and self.app.adaptive.split is not None:
                    self.app.adaptive.trim_details(details)
                else:
                    self.app.routes.trim(route_destination, count)
            if notebook:
                from features.notebooks.mobile.documents import open_notebook
                resource = DocumentResource(provider, destination, max_bytes=request.max_bytes)
                if operation.binary_owner is not None:
                    from features.notebooks.mobile.documents import retarget_notebook
                    opened = await retarget_notebook(self.app, operation.binary_owner, resource)
                else:
                    opened = await open_notebook(self.app, resource=resource)
            else:
                opened = await self.open_crypt(copies=copies, key=destination, prepared=prepared,
                                        privacy_gate=privacy_gate, edit=creation is not None)
            if not self.active_host or epoch != self._epoch:
                return
            if opened:
                self.operation.origin = self.panel = None
                self.operation.binary_owner = None
                self.operation.creation = None
                self.operation.data = None
                self.operation.privacy_gate = None
                if source_document is not None and getattr(source_document, 'private', False):
                    source_document.text = source_document.snapshot.text
                    self.app.finish_save_as_source(source_document)
                self.operation.source_document = None
            else:
                self.save_as_status.value = ('The file was created in the chosen folder, but its editor could not be opened.'
                    if creation is not None else 'The file was saved, but its editor could not be opened. The Save As draft is retained.')
                self.show_view(self.creation_layout if creation is not None else self.panel, route='text-destination',
                               title='New document' if creation is not None else 'Save As')
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

