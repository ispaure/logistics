"""Native local file management; shared operations own transfer correctness."""
from commonUtils.ui.native.password_input import PasswordInput
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

from features.rclone.mobile.storage_location import collection_path, CollectionFiles
import asyncio
import threading
from pathlib import Path
from commonUtils.runtime.operations import MutationIncomplete
import toga
from .control_icons import icon_button
from .host_services import OwnedAttribute
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.resource_provider import resource_path
from commonUtils.runtime.resource_mutations import move_resource, delete_resource, create_resource_folder, rename_resource
from features.rclone.localcrypt.mobile.resources import encrypted_storage, encrypted_document


def local_read_available(app, *, private=True):
    """Offline reads may share a managed transfer; credential operations still wait."""
    return (app.active_host and not getattr(app, '_storage_changing', False) and (not private or not getattr(app, 'cloud_busy', False)
            or getattr(app, 'transfer_busy', False) or getattr(app, 'remote_read_busy', False)))


class FilesUI:
    def set_file_items(self, items):
        self.file_selection.items = ['Select an item…', *items]
        # Toga 0.5.7's iOS picker can retain its previous row count after a
        # source update, selecting the wrong item until the picker is opened.
        picker = getattr(self.file_selection._impl, 'native_picker', None)
        if picker is not None:
            picker.reloadAllComponents()
        if items:
            self.file_selection.value = 'Select an item…'

    def build_file_manager(self):
        return toga.Button('Manage local files and folders…', on_press=self.show_files, style=Pack(height=48))

    def can_browse_local(self, label='Local files'):
        provider = getattr(self, 'file_roots', {}).get(label)
        ordinary = label == 'Local files' or (isinstance(provider, LocalFiles) and not provider.private)
        return (self.cloud_busy and local_read_available(self, private=not ordinary)
                and (label == 'Local files' or label in getattr(self, 'file_roots', {})))

    async def browse_local_during_transfer(self, folder):
        previous = getattr(self, '_local_browse_cancel', None)
        if previous is not None:
            previous.set()
        cancel = self._local_browse_cancel = threading.Event()
        label = self.file_storage.value
        client = self.cloud_client
        generation = getattr(client, 'generation', None)
        try:
            provider = self.file_provider_for(label)
            path = provider.relative(folder)
            rows = await asyncio.to_thread(provider.list, path, cancelled=cancel.is_set)
            if (not self.active_host or cancel.is_set()
                    or (self.file_storage.value, self.file_location.value) != (label, folder)
                    or (provider.private and (client is not self.cloud_client
                        or generation != getattr(self.cloud_client, 'generation', None)))):
                return False
            self.file_provider, self.file_path = provider, path
            self.file_rows = {f'{i + 1}. {"Folder" if row["directory"] else "File"}: {row["name"]}' : row
                              for i, row in enumerate(rows)}
            # set_entries publishes selection reset once with the new snapshot.
            self.file_loaded_location = label, path
            self.populate_file_browser(rows, self.file_password.value, location=self.file_loaded_location)
            self.file_status.value = f'{len(rows)} items'
            return True
        except Exception as error:
            if (self.active_host and not cancel.is_set()
                    and (self.file_storage.value, self.file_location.value) == (label, folder)):
                self.file_status.value = 'Could not browse local folder: ' + str(error)[:200]
                if self.file_provider is not None and self.file_browser.tree is not None:
                    self.file_changing_location = True
                    try:
                        self.file_storage.value, self.file_location.value = self.file_loaded_location
                    finally:
                        self.file_changing_location = False
                else:
                    self.file_provider = None
                    self.file_rows = {}
                    self.file_selection.items = []
                    self.file_browser.stop()
            return False

    async def show_files(self, widget=None, *, local_root=False, **kwargs):
        try:
            collection_path(self.private_root)
        except (OSError, ValueError) as error:
            await self.main_window.dialog(toga.InfoDialog('Collection drive unavailable', str(error)))
            return
        if self.cloud_busy and not self.can_browse_local():
            return
        if (hasattr(self, 'files_view') and self.file_provider is not None
                and not self.file_browser.closed):
            if local_read_available(self, private=True):
                roots = {**self.ordinary_file_roots(), **self.existing_crypt_locations(), **self.linked_crypt_locations()}
                storage, destination = self.file_storage.value, self.file_destination.value
                local_root = local_root or storage not in roots
                self.file_changing_location = True
                try:
                    self.file_roots = roots
                    self.file_storage.items = list(roots)
                    self.file_destination.items = list(roots)
                    self.file_storage.value = storage if storage in roots else 'Local files'
                    self.file_destination.value = destination if destination in roots else 'Local files'
                finally:
                    self.file_changing_location = False
            if local_root or (self.cloud_busy and not self.can_browse_local(self.file_storage.value)):
                self.file_changing_location = True
                try:
                    self.file_storage.value = 'Local files'
                    self.file_location.value = self.file_path if (not local_root and isinstance(self.file_provider, LocalFiles)
                        and self.file_provider.root == collection_path(self.private_root)) else ''
                finally:
                    self.file_changing_location = False
                if local_root:
                    self.file_browser.search.value = ''
                    self.file_browser.history.clear()
                await self.browse_files()
            self.show_view(self.files_view, destination='files', route='browser', title='File browser')
            return
        if hasattr(self, 'file_browser'):
            await self.file_browser.close()
        self.file_roots = self.ordinary_file_roots()
        if local_read_available(self, private=True):
            self.file_roots.update(self.existing_crypt_locations())
            self.file_roots.update(self.linked_crypt_locations())
        self.file_storage = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_storage.value = 'Local files'
        self.file_location = toga.TextInput(placeholder='Folder path (empty for root)', style=Pack(height=48))
        self.file_selection = toga.Selection(style=Pack(height=48))
        from .browser_ui import FileBrowser as NativeBrowser
        self.file_browser = NativeBrowser(folder_visible=self.folder_path_visible, selected=self.browser_file_selected, open_folder=self.browser_file_folder, navigate=self.browser_file_location, open_file=self.browser_file_open, item_actions=self.show_file_actions)
        self.file_browser.navigation_controls.remove(self.file_browser.back_button)
        self.file_password = PasswordInput(placeholder='Inner archive password, when needed', style=Pack(height=48))
        self.file_name = toga.TextInput(placeholder='New name / folder name', style=Pack(height=48))
        self.file_destination = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_target = toga.TextInput(placeholder='Destination path including name', style=Pack(height=48))
        (collection_path(self.private_root)).mkdir(exist_ok=True)
        self.file_status = NativeBrowser.status_label(style=Pack(height=18, font_size=12))
        self.file_action_status = toga.Label('', style=Pack(font_size=12, margin_top=8))
        self.file_rows, self.file_provider = {}, None
        buttons = [toga.Button(label, on_press=handler, style=Pack(height=48)) for label, handler in (
            ('Browse folder', self.browse_files), ('Open folder', self.enter_file_folder),
            ('Open file', self.read_managed_file), ('New folder', self.new_file_folder),
            ('Rename selected', self.rename_file), ('Delete selected…', self.delete_file),
            ('Move selected', self.move_file), ('Use selected offline encrypted copy', self.use_downloaded_file),
            ('Cancel operation', self.cancel_cloud), ('Back to remote files', self.files_back))]
        self.file_commands = buttons
        self.file_operation_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
            toga.Button('Folder Hub', on_press=self.show_locations, style=Pack(height=48)),
            toga.Label('Local files and folders'), self.file_storage, self.file_location, buttons[0],
            icon_button('up', 'Parent folder', on_press=self.parent_file_folder),
            self.file_password, self.file_browser.widget, buttons[1], buttons[2], self.file_name, *buttons[3:6],
            toga.Label('Move destination'), self.file_destination, self.file_target, *buttons[6:],
            toga.Button('Use selected private download', on_press=self.use_local_download, style=Pack(height=48)),
            toga.Label('Moving to Local creates decrypted files.\nCloud originals are unchanged.'), self.file_status],
            style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
        # Keep mutations and destination fields in a separate commands route.
        # A widget has one native parent; move browser/status into the main view.
        operation_box = self.file_operation_view.content
        operation_box.remove(self.file_browser.widget)
        from commonUtils.ui.native.presentation import scroll_content
        operation_box.remove(self.file_status)
        operation_box.remove(buttons[1])
        operation_box.remove(buttons[2])
        operation_box.remove(self.file_storage)
        from .action_menu import FeatureCommands
        self.file_actions_button = icon_button('more', 'File and folder actions')
        self.file_actions = FeatureCommands(self.file_actions_button, self,
            [('New folder…', lambda: self.show_file_actions(operation='new')),
             ('Rename…', lambda: self.show_file_actions(operation='rename')),
             ('Move…', lambda: self.show_file_actions(operation='move')),
             ('Pin current folder', self.pin_local_folder),
             ('Delete selected…', self.delete_file), ('Change location…', lambda: self.show_file_actions(operation='location')),
             ('Archive password…', lambda: self.show_file_actions(operation='password'))], self.show_file_actions)
        self.file_browser.location_bar = NativeBrowser.location_header(self.file_status,
            icon_button('back', 'Back to Folder Hub', on_press=self.parent_file_folder))
        self.files_view = toga.Box(children=[
            toga.Box(children=[toga.Button('Folder Hub', on_press=self.show_locations, style=Pack(height=48, flex=1)),
                               self.file_actions_button], style=Pack(direction=ROW)),
            self.file_storage,
            self.file_browser.location_bar,
            toga.ScrollContainer(horizontal=False, content=scroll_content(self.file_browser.widget), style=Pack(flex=1))],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.show_view(self.files_view, destination='files', route='browser', title='File browser')
        await self.browse_files()
        self.file_storage.on_change = self.change_file_storage

    def change_file_storage(self, widget=None, **kwargs):
        # Check programmatic-change guards synchronously. Native async handlers
        # otherwise run after the guard has been cleared and undo valid switches.
        if getattr(self, 'file_changing_location', False):
            return
        try:
            selected = self.file_storage.value
        except IndexError:
            # Android Spinner can report its old index while a source is cleared.
            return
        if selected is None:
            return
        native = getattr(getattr(self.file_storage, '_impl', None), 'native', None)
        if native is not None and hasattr(native, 'resignFirstResponder'):
            native.resignFirstResponder()
        loaded = getattr(self, 'file_loaded_location', (None, ''))[0]
        if self.cloud_busy and not self.can_browse_local(selected):
            self.file_changing_location = True
            try:
                if loaded in [row.value for row in self.file_storage.items]:
                    self.file_storage.value = loaded
            finally:
                self.file_changing_location = False
            self.file_status.value = 'This connection is busy. Local files remain available.'
            return
        if selected != loaded:
            self.file_location.value = ''
            return self.loop.create_task(self.browse_files())

    def show_file_actions(self, widget=None, *, operation=None, **kwargs):
        if self.cloud_busy:
            return
        box = self.file_operation_view.content
        for child in list(box.children):
            box.remove(child)
        selected = self.file_rows.get(self.file_selection.value)
        title = selected['name'] if selected else 'Folder actions'
        box.add(toga.Label(title, style=Pack(font_size=20, margin_bottom=12)))
        if operation in ('new', 'rename'):
            if operation == 'rename' and selected:
                self.file_name.value = selected['name']
            else:
                self.file_name.value = ''
            self.file_name.placeholder = 'Folder name' if operation == 'new' else 'New name'
            box.add(self.file_name)
            box.add(self.file_commands[3 if operation == 'new' else 4])
        elif operation == 'move':
            box.add(toga.Label('Move to'))
            box.add(self.file_destination)
            box.add(self.file_target)
            box.add(self.file_commands[6])
        elif operation == 'password':
            box.add(toga.Label('Password for the archive you want to open'))
            box.add(self.file_password)
        elif operation == 'location':
            box.add(self.file_location)
            box.add(self.file_commands[0])
        else:
            commands = [('New folder…', lambda: self.show_file_actions(operation='new'))]
            if self.file_storage.value == 'Local files':
                commands.append(('Pin this folder', self.pin_local_folder))
            if selected:
                commands += [('Open', self.enter_file_folder if selected['directory'] else self.read_managed_file),
                             ('Rename…', lambda: self.show_file_actions(operation='rename')),
                             ('Move…', lambda: self.show_file_actions(operation='move')),
                             ('Details', self.show_file_details), ('Delete…', self.delete_file)]
            from features.rclone.localcrypt.mobile.resources import CryptFiles
            if isinstance(self.file_provider, LocalFiles) and (not self.file_provider.private or isinstance(self.file_provider, CryptFiles)):
                commands += [('Edit comics in this folder…', self.edit_local_comic_folder)]
            commands += [('Archive password…', lambda: self.show_file_actions(operation='password'))]
            for label, callback in commands:
                async def run(widget=None, target=callback, **kw):
                    import inspect
                    result = target()
                    if inspect.isawaitable(result):
                        await result
                box.add(toga.Button(label, on_press=run, style=Pack(height=48, margin_bottom=4)))
        box.add(self.file_action_status)
        box.add(toga.Button('Return to files', on_press=self.show_files, style=Pack(height=48, margin_top=12)))
        self.show_view(self.file_operation_view, destination='files', route='file-actions', title='File actions')

    def show_file_details(self, widget=None, **kwargs):
        info = self.file_browser.info
        if info.parent is not None:
            info.parent.remove(info)
        box = toga.Box(children=[info,
            toga.Button('Return to files', on_press=self.show_files, style=Pack(height=48))],
            style=Pack(direction=COLUMN, margin=12))
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)), destination='files',
                       route='file-details', title='File details')

    async def parent_file_folder(self, widget=None, **kwargs):
        if not self.file_path:
            self.show_locations()
            return
        if not self.cloud_busy or self.can_browse_local(self.file_storage.value):
            self.file_location.value = self.file_path.rpartition('/')[0]
            await self.browse_files()

    def browser_file_selected(self, row):
        if row is None:
            self.set_file_items(list(self.file_rows))
            return
        label = next((label for label, value in self.file_rows.items() if value['path'] == row['path']), None)
        if label is None:
            label = 'Search: ' + row['path']
            self.file_rows[label] = row
            self.set_file_items(list(self.file_rows))
        self.file_selection.value = label

    async def browser_file_open(self, row):
        # Selection has already been published by the browser on the GUI thread.
        await self.read_managed_file()

    async def browser_file_folder(self, row):
        if self.cloud_busy and not self.can_browse_local(self.file_storage.value):
            return False
        return await self.browser_file_location((self.file_storage.value, row['path']))

    async def browser_file_location(self, location):
        if self.cloud_busy and not self.can_browse_local(location[0]):
            return False
        self.file_changing_location = True
        try:
            self.file_storage.value, self.file_location.value = location
        finally:
            self.file_changing_location = False
        return await self.browse_files()

    def update_file_locations(self):
        self.file_changing_location = True
        try:
            self.file_storage.items = list(self.file_roots)
            picker = getattr(self.file_storage._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
        finally:
            self.file_changing_location = False

    def files_back(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_cloud()

    def ordinary_file_roots(self):
        from .local_sources import shared_files
        roots = {'Local files': None}
        shared = shared_files(self.private_root)
        if shared is not None:
            roots['Shared files'] = shared
        return roots

    def file_provider_for(self, label):
        return self.storage_provider(label, self.file_roots)

    def storage_provider(self, label, roots):
        """One provider resolution path for browsing, moving and editor pickers."""
        remote = roots[label]
        if isinstance(remote, LocalFiles):
            return remote
        if remote is None:
            return CollectionFiles(self.private_root)
        return encrypted_storage(self.private_root, self.cloud_client, remote)

    async def file_work(self, work, *, mutation=True):
        if not self.active_host or self.cloud_busy or (mutation and not self.clear_private_reader()):
            return False
        # Capture selection on the GUI thread before handing work to a worker.
        row = self.file_rows.get(self.file_selection.value)
        self._file_selected = (self.file_provider, row['path'] if row else None)
        controls = (self.file_storage, self.file_location, self.file_selection,
                    self.file_name, self.file_destination, self.file_target, self.file_password, self.file_actions_button)
        for control in controls:
            control.enabled = False
        self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        try:
            await asyncio.to_thread(work, self._crypt_cancel.is_set)
            if not self.active_host:
                return False
            self.file_status.value = 'Finished. Destination verified before removing the source.'
            return True
        except MutationIncomplete as error:
            if self.active_host:
                self.file_status.value = str(error) + '\nRefresh before retrying.'
            return False
        except Exception as error:
            if self.active_host:
                self.file_status.value = 'Operation failed: ' + str(error)[:300] + '\nRefresh to inspect any completed items.'
            return False
        finally:
            self._crypt_cancel = None
            if self.active_host:
                self.file_action_status.text = self.file_status.value
                self.set_cloud_busy(False)
                self.refresh_downloads()
                for control in controls:
                    control.enabled = True
            else:
                self.cloud_busy = False

    async def browse_files(self, widget=None, **kwargs):
        previous = getattr(self, '_local_browse_cancel', None)
        if previous is not None:
            previous.set()
        if not self.active_host:
            return False
        if self.cloud_busy:
            if self.can_browse_local(self.file_storage.value):
                return await self.browse_local_during_transfer(self.file_location.value)
            return False
        # Listing is a cancellable read, not a mutation. Keep cloud controls and
        # download discovery out of the navigation path, including idle browsing.
        return await self.browse_local_during_transfer(self.file_location.value)

    def populate_file_browser(self, rows, password='', *, location=None):
        from .browser_preview import callbacks
        client = self.cloud_client
        self.file_browser.thumbnail, self.file_browser.details = callbacks(self.file_provider, client, password)
        if location is None:
            self.file_browser.history.clear()
        self.file_browser.set_entries(self.file_provider, self.file_path, rows, location=location)
        self.file_browser.location_bar.update(self.file_path, encrypted=self.file_provider.private,
            name=Path(self.file_path).name if self.file_path else self.file_storage.value)

    def selected_file(self):
        row = self.file_rows.get(self.file_selection.value)
        if self.file_provider is None or row is None:
            raise ValueError('Browse and select a file or folder first.')
        return self.file_provider, row['path']

    async def enter_file_folder(self, widget=None, **kwargs):
        if self.cloud_busy and not self.can_browse_local(self.file_storage.value):
            return
        row = self.file_rows.get(self.file_selection.value)
        if row and row['directory']:
            self.file_location.value = row['path']
            await self.browse_files()

    async def new_file_folder(self, widget=None, **kwargs):
        name = self.file_name.value
        def work(cancelled):
            name_part = resource_path(name)
            if not name_part or '/' in name_part or self.file_provider is None:
                raise ValueError('Browse a folder and enter one new folder name.')
            create_resource_folder(self.file_provider, '/'.join(p for p in (self.file_path, name_part) if p), cancelled=cancelled)
        if await self.file_work(work):
            await self.browse_files()

    async def rename_file(self, widget=None, **kwargs):
        name = self.file_name.value
        def work(cancelled):
            provider, source = self._file_selected
            if provider is None or source is None:
                raise ValueError('Select a file first.')
            part = resource_path(name)
            if not part or '/' in part:
                raise ValueError('Enter one new name.')
            rename_resource(provider, source, '/'.join(p for p in (source.rpartition('/')[0], part) if p), cancelled=cancelled)
        if await self.file_work(work):
            await self.browse_files()

    async def delete_file(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        try:
            provider, path = self.selected_file()
        except ValueError as error:
            self.file_status.value = str(error)
            return
        if not await self.main_window.dialog(toga.ConfirmDialog('Delete permanently', 'Delete this item and all contents? This cannot be undone.')):
            return
        if await self.file_work(lambda cancelled: delete_resource(provider, path, cancelled=cancelled)):
            await self.browse_files()

    async def move_file(self, widget=None, **kwargs):
        destination, target = self.file_destination.value, self.file_target.value
        def work(cancelled):
            provider, path = self._file_selected
            if provider is None or path is None:
                raise ValueError('Select a file first.')
            move_resource(provider, path, self.file_provider_for(destination), target, cancelled=cancelled)
        if await self.file_work(work):
            await self.browse_files()
            await self.refresh_crypt()


    async def read_managed_file(self, widget=None, **kwargs):
        try:
            provider, path = self.selected_file()
            if self.cloud_busy and not (local_read_available(self, private=getattr(provider, 'private', False)) and isinstance(provider, LocalFiles)):
                return
            if provider.entry(path)['directory']:
                raise ValueError('Choose a file to read.')
            source = encrypted_document(provider, path)
            if source is not None:
                self.crypt_password.value = self.file_password.value
                copies, key = source
                await self.open_crypt(copies=copies, key=key, destination='files')
            elif Path(path).suffix.lower() in SOURCE_EXTENSIONS:
                from features.text_editor.resources import LocalTextCopies
                await self.open_crypt(copies=LocalTextCopies(provider), key=path, destination='files')
            else:
                await self.open_download(path=provider._locate(path), destination='files')
        except ValueError as error:
            self.file_status.value = str(error)

    async def use_local_download(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        path = self.download_labels.get(self.download_selector.value)
        if path is None:
            self.file_status.value = 'Select a private download on the remote-files screen first.'
            return
        self.file_provider = LocalFiles(path.parent)
        self.file_path = ''
        row = self.file_provider.entry(path.name)
        self.file_rows = {row['name']: row}
        self.set_file_items(list(self.file_rows))
        self.populate_file_browser([row])
        self.file_status.value = 'Choose a Local or LocalCrypt destination for this downloaded file.'

    # Existing native probes and callbacks retain their app-facing entry points.
    editor_browser = OwnedAttribute('editor_picker', 'editor_browser')
    editor_linked_roots = OwnedAttribute('editor_picker', 'editor_linked_roots')
    editor_picker_location = OwnedAttribute('editor_picker', 'editor_picker_location')
    editor_picker_mode = OwnedAttribute('editor_picker', 'editor_picker_mode')
    editor_picker_rows = OwnedAttribute('editor_picker', 'editor_picker_rows')
    editor_storage_roots = OwnedAttribute('editor_picker', 'editor_storage_roots')
    picker_entries = OwnedAttribute('editor_picker', 'picker_entries')
    picker_folder = OwnedAttribute('editor_picker', 'picker_folder')
    save_as_data = OwnedAttribute('editor_picker', 'save_as_data')
    save_as_name = OwnedAttribute('editor_picker', 'save_as_name')
    save_as_privacy_gate = OwnedAttribute('editor_picker', 'save_as_privacy_gate')
    save_as_source_document = OwnedAttribute('editor_picker', 'save_as_source_document')
    save_as_status = OwnedAttribute('editor_picker', 'save_as_status')
    save_as_storage = OwnedAttribute('editor_picker', 'save_as_storage')
    save_as_view = OwnedAttribute('editor_picker', 'save_as_view')

    async def show_crypt_save_as(self, widget=None, *, owner=None, **kwargs):
        return await self.editor_picker().show_crypt_save_as(widget, owner=owner, **kwargs)

    async def show_document_save_as(self, widget=None, **kwargs):
        return await self.editor_picker().show_document_save_as(widget, **kwargs)

    async def show_editor_open(self, widget=None, **kwargs):
        return await self.editor_picker().show_editor_open(widget, **kwargs)

    async def show_text_destination(self, name, data, *, privacy_gate=None):
        return await self.editor_picker().show_text_destination(name, data, privacy_gate=privacy_gate)

    async def show_editor_browser(self, mode, name='', data=None):
        return await self.editor_picker().show_editor_browser(mode, name, data)

    def browser_editor_selected(self, row):
        return self.editor_picker().browser_editor_selected(row)

    async def browser_editor_folder(self, row):
        return await self.editor_picker().browser_editor_folder(row)

    async def browser_editor_location(self, location):
        return await self.editor_picker().browser_editor_location(location)

    def editor_provider(self, label):
        return self.editor_picker().editor_provider(label)

    async def refresh_editor_browser(self, widget=None, **kwargs):
        return await self.editor_picker().refresh_editor_browser(widget, **kwargs)

    async def parent_editor_folder(self, widget=None, **kwargs):
        return await self.editor_picker().parent_editor_folder(widget, **kwargs)

    async def select_editor_item(self, widget=None, **kwargs):
        return await self.editor_picker().select_editor_item(widget, **kwargs)

    async def confirm_editor_file(self, widget=None, **kwargs):
        return await self.editor_picker().confirm_editor_file(widget, **kwargs)

    def cancel_text_destination(self, widget=None, **kwargs):
        return self.editor_picker().cancel_text_destination(widget, **kwargs)

    async def save_text_destination(self, widget=None, **kwargs):
        return await self.editor_picker().save_text_destination(widget, **kwargs)



    async def edit_local_comic_folder(self, widget=None, **kwargs):
        if self.cloud_busy:
            return
        if self.file_provider.private:
            return await self.edit_private_comic_folder()
        from features.comics.mobile.collection import scan_comics, CollectionBatch, metadata_fields, suggestions, open_local_comic
        from features.comics.mobile.metadata import batch_form
        provider = self.file_provider
        if not isinstance(provider, LocalFiles) or provider.private:
            return
        selected = self.file_rows.get(self.file_selection.value)
        folder = selected['path'] if selected and selected['directory'] else self.file_path
        cancel = threading.Event()
        self.set_cloud_busy(True)
        try:
            def prepare():
                entries = scan_comics(provider, folder, cancelled=cancel.is_set)
                if not entries:
                    raise ValueError('No CBZ/ZIP comics found in this folder.')
                def document(path):
                    return open_local_comic(provider._locate(path))
                return CollectionBatch(entries, open_document=document,
                    revision=lambda path: provider.entry(path)['revision'],
                    publish=lambda path, doc, changes: doc.save(changes))
            plan = await asyncio.to_thread(prepare)
        except Exception as error:
            self.file_action_status.text = 'Cannot edit folder: ' + str(error)[:200]
            return
        finally:
            self.set_cloud_busy(False)
        async def apply(changes):
            if self.cloud_busy:
                return 'Wait for the current operation.'
            if not changes:
                return 'No fields selected.'
            self.set_cloud_busy(True)
            cancel.clear()
            try:
                completed, failures = await asyncio.to_thread(plan.apply, changes, cancelled=cancel.is_set)
                return (f'{len(completed)} saved; {len(failures)} failed; '
                    f'{len(plan.entries) - len(completed) - len(failures)} unprocessed. '
                    + ' '.join(message for _, message in failures)[:300])
            finally:
                self.set_cloud_busy(False)
        choices = suggestions(metadata_fields('comic', document) for document in plan.documents)
        async def back(widget=None, **kwargs):
            await self.show_files()
        view = batch_form(plan.documents, save=apply, choices=choices,
            width=max(1, min(640, min(self.main_window.size) - 24)),
            cancel=lambda w, **kw: cancel.set(), back=back)
        self.local_comic_batch, self.local_comic_batch_view = plan, view
        self.show_view(view, destination='files', route='comic-folder-batch', title='Edit folder comics')

    def retire_private_comic_batch(self, *, view=None, stale_only=False):
        plan = getattr(self, 'private_comic_batch', None)
        if plan is None or (view is not None and plan.view is view):
            return
        if stale_only and plan.valid():
            return
        plan.close()
        self.private_comic_batch = None
        privacy = getattr(self, 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()

    async def edit_private_comic_folder(self):
        from contextlib import contextmanager
        from features.rclone.localcrypt.mobile.resources import CryptFiles, encrypted_document
        from features.comics.mobile.private_batch import PrivateCollectionBatch
        from features.comics.mobile.collection import metadata_fields, suggestions
        from features.comics.mobile.metadata import batch_form
        from commonUtils.runtime.operations import OperationCancelled
        provider = self.file_provider
        if not isinstance(provider, CryptFiles) or self.cloud_busy:
            return
        if len(self.scene_manager.owners.hosts) > 1:
            self.file_action_status.text = 'Close other windows before editing private collections.'
            return
        self.retire_private_comic_batch()
        client, generation = self.cloud_client, self.cloud_client.generation
        navigation = self.navigation_generation
        def valid():
            return (self.active_host and self.cloud_client is client and client.generation == generation
                    and getattr(self, 'private_comic_batch', None) is plan)
        def release(reader):
            source = reader.source
            if hasattr(source, 'close'):
                source.close()
            if hasattr(source, 'data'):
                source.data = b''
            reader.data, reader.password = None, ''
            reader.book = None
            reader.__dict__.pop('_comic', None)
        @contextmanager
        def opened(path):
            copies, key = encrypted_document(provider, path)
            reader = copies.open(key, cancelled=lambda: plan.closed or plan.cancel.is_set() or not valid())
            try:
                yield reader
            finally:
                release(reader)
        def publish(reader, changes, *, cancelled):
            copies, _ = encrypted_document(provider, reader.key)
            return copies.save_metadata(reader, changes, cancelled=cancelled)
        plan = PrivateCollectionBatch(valid=valid, open_reader=opened,
            revision=lambda path: provider.entry(path)['revision'], publish=publish, release_reader=release)
        self.private_comic_batch = plan
        plan.privacy_gate = getattr(client, 'session_privacy', None)
        self.screen_privacy.refresh()
        selected = self.file_rows.get(self.file_selection.value)
        folder = selected['path'] if selected and selected['directory'] else self.file_path
        self.set_cloud_busy(True)
        try:
            await asyncio.to_thread(plan.prepare, provider, folder)
            if not valid() or self.navigation_generation != navigation:
                self.retire_private_comic_batch()
                return
            async def save(changes):
                if self.cloud_busy or not valid() or plan.closed or plan.requires_reopen:
                    return 'Private batch is unavailable. Reopen the folder.'
                if not changes:
                    return 'No fields selected.'
                plan.cancel.clear()
                self.set_cloud_busy(True)
                count = len(plan.entries)
                try:
                    completed, failures = await asyncio.to_thread(plan.apply, changes)
                    message = f'{len(completed)} saved encrypted locally; {len(failures)} failed; {count - len(completed) - len(failures)} unprocessed.'
                    if plan.requires_reopen:
                        message += ' A file may already be saved. Reopen the batch before retrying.'
                    return message
                finally:
                    self.set_cloud_busy(False)
            async def back(widget=None, **kwargs):
                self.retire_private_comic_batch()
                await self.show_files()
            choices = suggestions(metadata_fields('comic', document) for document in plan.documents)
            view = batch_form(plan.documents, save=save, back=back, choices=choices,
                width=max(1, min(640, min(self.main_window.size) - 24)), cancel=lambda w, **kw: plan.cancel.set())
            plan.view = view
            self.show_view(view, destination='files', route='private-comic-batch', title='Edit private folder comics')
        except OperationCancelled:
            self.retire_private_comic_batch()
        except Exception:
            self.retire_private_comic_batch()
            self.file_action_status.text = 'Private batch could not be opened. Check the folder, credentials and archive passwords.'
        finally:
            self.set_cloud_busy(False)
