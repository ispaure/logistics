"""Owned Open/Save As workflow; picker state never falls back to app attributes."""
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

import asyncio
from pathlib import Path
import threading
from dataclasses import dataclass

import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.runtime.operations import MutationIncomplete
from commonUtils.runtime.resource_selection import ResourceSelection
from features.rclone.localcrypt.mobile.resources import encrypted_copies
from .control_icons import icon_button
from .host_services import HostService


@dataclass
class PickerWork:
    cancel: threading.Event
    epoch: int
    client: object
    credential_generation: object
    navigation: int
    gate: object
    gate_revision: object


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

    def cancel(self):
        if self._work is not None:
            self._work.cancel.set()

    def clear(self):
        """Invalidate late results and forget picker-owned private material."""
        self._epoch += 1
        self.cancel()
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
            self.save_as_storage.items = []
            self.save_as_status.value = ''

    def _begin_work(self):
        client = getattr(self.app, 'cloud_client', None)
        gate = self.save_as_privacy_gate
        work = PickerWork(threading.Event(), self._epoch, client,
                          getattr(client, 'generation', None), self.app.navigation_generation,
                          gate, getattr(gate, 'revision', None))
        if gate is not None and gate.locked:
            work.cancel.set()
        self._work = work
        self.set_cloud_busy(True)
        return work

    def _accepts(self, work):
        client = getattr(self.app, 'cloud_client', None)
        return (self._work is work and work.epoch == self._epoch and self.active_host
                and not work.cancel.is_set() and client is work.client
                and getattr(client, 'generation', None) == work.credential_generation
                and self.app.navigation_generation == work.navigation
                and (work.gate is None or (not work.gate.locked
                     and work.gate.revision == work.gate_revision)))

    def _finish_work(self, work):
        if self._work is work:
            self._work = None
            self.set_cloud_busy(False)

    async def show_crypt_save_as(self, widget=None, *, owner=None, **kwargs):
        owner = owner or self.provider_sessions().active
        if getattr(getattr(owner, 'crypt_reader', None), 'read_only', False):
            return
        if self.cloud_busy or owner is None or owner.crypt_reader is None or not owner.crypt_reader.editable:
            return
        self.save_as_source_document = None
        await self.show_text_destination(owner.crypt_reader.name, owner.crypt_reader.text_snapshot.encode(owner.crypt_text.value),
                                         privacy_gate=getattr(owner, 'privacy_gate', None))

    async def show_document_save_as(self, widget=None, **kwargs):
        if self.current is None:
            return
        source_document = self.current
        name, data = source_document.name, source_document.snapshot.encode(source_document.text)
        if not hasattr(self, 'cloud_view'):
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
        if self.cloud_busy:
            return
        if not self.active_host:
            return
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

    async def show_editor_browser(self, mode, name='', data=None):
        if self.cloud_busy or not self.active_host:
            return
        self._epoch += 1
        if hasattr(self, 'editor_browser'):
            await self.editor_browser.close()
        if not self.active_host:
            return
        self.editor_picker_mode = mode
        self.save_as_data = data
        if mode == 'open':
            self.save_as_source_document = None
            self.save_as_privacy_gate = None
        self.editor_storage_roots = {'Local files': None, **self.existing_crypt_locations()}
        self.editor_linked_roots = self.linked_crypt_locations()
        self.editor_storage_roots.update(self.editor_linked_roots)
        roots = list(self.editor_storage_roots)
        self.editor_picker_rows = {}
        self.save_as_storage = toga.Selection(items=roots, style=Pack(height=48))
        self.picker_folder = toga.TextInput(placeholder='Folder within storage', style=Pack(height=48))
        self.picker_entries = toga.Selection(style=Pack(height=48))
        from .browser_ui import FileBrowser as NativeBrowser
        self.editor_browser = NativeBrowser(folder_visible=self.folder_path_visible, selected=self.browser_editor_selected, open_folder=self.browser_editor_folder, navigate=self.browser_editor_location, preview=False)
        self.save_as_name = toga.TextInput(value=name, placeholder='File name', style=Pack(height=48))
        self.save_as_status = toga.MultilineTextInput(readonly=True, style=Pack(height=75))
        self.save_as_view = toga.Box(children=[toga.Label('Open' if mode == 'open' else 'Save As'),
            self.save_as_storage, self.picker_folder,
            toga.Button('Browse folder', on_press=self.refresh_editor_browser, style=Pack(height=48)),
            icon_button('up', 'Parent folder', on_press=self.parent_editor_folder),
            toga.Button('Choose selected item', on_press=self.select_editor_item, style=Pack(height=48)),
            self.save_as_name, toga.Label('Local files are plaintext. LocalCrypt stays encrypted. Drafts opened here stay in memory.'),
            toga.Button('Open file' if mode == 'open' else 'Save new file', on_press=self.confirm_editor_file, style=Pack(height=48)),
            toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=48)), self.save_as_status],
            style=Pack(direction=COLUMN, margin=12))
        # The list owns its bounded scrolling viewport. Keep the form scrollable
        # beside it in the page layout, never around the native list itself.
        form = toga.ScrollContainer(horizontal=False, content=self.save_as_view,
                                    style=Pack(flex=1))
        panel = toga.Box(children=[self.editor_browser.scroll_container(), form],
                         style=Pack(direction=COLUMN, flex=1))
        from .ios_toolbar import prepare_form
        prepare_form(panel, primary='Open file' if mode == 'open' else 'Save new file', cancel='Cancel')
        self.show_view(panel)
        await self.refresh_editor_browser()

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
        if not row['directory']:
            self.save_as_name.value = row['name']

    async def browser_editor_folder(self, row):
        if self.cloud_busy:
            return False
        return await self.browser_editor_location((self.save_as_storage.value, row['path']))

    async def browser_editor_location(self, location):
        if self.cloud_busy:
            return False
        self.save_as_storage.value, self.picker_folder.value = location
        return await self.refresh_editor_browser()

    def editor_provider(self, label):
        return self.storage_provider(label, self.editor_storage_roots)

    async def refresh_editor_browser(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        label, folder = self.save_as_storage.value, self.picker_folder.value
        work = self._begin_work()
        try:
            model = ResourceSelection(self.editor_provider(label), mode=self.editor_picker_mode,
                                      extensions=SOURCE_EXTENSIONS)
            rows = await asyncio.to_thread(model.list, folder, cancelled=work.cancel.is_set)
            if not self._accepts(work):
                return False
            self.editor_picker_rows = {f'{i+1}. {"Folder" if row["directory"] else "File"}: {row["name"]}': row for i,row in enumerate(rows)}
            self.editor_picker_location = label, folder
            self.picker_entries.items = list(self.editor_picker_rows)
            picker = getattr(self.picker_entries._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            if self.editor_picker_rows:
                self.picker_entries.value = next(iter(self.editor_picker_rows))
            self.editor_browser.set_entries(model, folder, rows, location=(label, folder))
            self.save_as_status.value = f'{len(rows)} entries. Choose a folder or file.'
            return True
        except Exception as error:
            if not self._accepts(work):
                return False
            if self.editor_browser.tree is not None:
                self.save_as_storage.value, self.picker_folder.value = self.editor_picker_location
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
                self.save_as_name.value = row['name']

    async def confirm_editor_file(self, widget=None, **kwargs):
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

    def cancel_text_destination(self, widget=None, **kwargs):
        if self._work is not None:
            self.cancel()
            self.save_as_status.value = 'Cancelling the operation. Your draft remains available.'
            return
        if not self.cloud_busy:
            self.clear()
            self.resume_crypt() if self.provider_sessions().active is not None else self.show_documents()

    async def save_text_destination(self, widget=None, **kwargs):
        from commonUtils.runtime.resource_mutations import save_resource_and_reopen
        from features.text_editor.resources import LocalTextCopies
        if self.cloud_busy or self.save_as_data is None:
            return
        target, label, data = self.save_as_name.value, self.save_as_storage.value, self.save_as_data
        folder = self.picker_folder.value
        work = self._begin_work()
        try:
            if Path(target).suffix.lower() not in SOURCE_EXTENSIONS or len(data) > 1024 * 1024:
                raise ValueError('Choose a text, source or configuration filename; saves are limited to 1 MiB.')
            provider = self.editor_provider(label)
            source_document = self.save_as_source_document
            store = self.store
            privacy_gate = self.save_as_privacy_gate
            def save():
                destination = ResourceSelection(provider, mode='save', extensions=SOURCE_EXTENSIONS).resolve(folder, target, cancelled=work.cancel.is_set)
                if provider.private and source_document is not None:
                    store.privatize(source_document)
                copies = encrypted_copies(provider) if provider.private else LocalTextCopies(provider)
                def reopen():
                    reader = copies.open(destination)
                    if reader.data != data:
                        raise ValueError('The saved file changed after publication.')
                    kind, content = reader.page(0)
                    return copies, destination, (reader, kind, content)
                return save_resource_and_reopen(provider, destination, data, reopen=reopen, cancelled=work.cancel.is_set)
            copies, destination, prepared = await asyncio.to_thread(save)
            if not self._accepts(work):
                return
            epoch = self._epoch
            self._finish_work(work)
            opened = await self.open_crypt(copies=copies, key=destination, prepared=prepared,
                                    privacy_gate=privacy_gate)
            if not self.active_host or epoch != self._epoch:
                return
            if opened:
                self.save_as_data = None
                self.save_as_privacy_gate = None
                if source_document is not None and getattr(source_document, 'private', False):
                    source_document.text = source_document.snapshot.text
                    self.app.finish_save_as_source(source_document)
                self.save_as_source_document = None
            else:
                self.save_as_status.value = 'The file was saved, but its editor could not be opened. The Save As draft is retained.'
                self.show_view(self.save_as_view)
        except MutationIncomplete as error:
            if not self._accepts(work):
                return
            self.save_as_status.value = str(error) + '\nRefresh before retrying; your draft remains available.'
        except Exception as error:
            if not self.active_host or work.epoch != self._epoch or work.cancel.is_set():
                return
            self.save_as_status.value = 'Save As failed; draft retained: ' + str(error)[:200]
        finally:
            self._finish_work(work)

