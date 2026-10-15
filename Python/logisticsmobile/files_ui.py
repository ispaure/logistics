"""Native local file management; shared operations own transfer correctness."""
import asyncio
import threading
from pathlib import Path
from commonUtils.runtime.operations import MutationIncomplete
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.local_files import LocalFiles
from commonUtils.runtime.resource_provider import resource_path
from commonUtils.runtime.resource_selection import ResourceSelection
from commonUtils.runtime.resource_mutations import move_resource, delete_resource, create_resource_folder, rename_resource
from .file_resources import CryptFiles, DownloadedCryptFile, ManagedCopies


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
        return toga.Button('Manage local files and folders…', on_press=self.show_files, style=Pack(height=44))

    def can_browse_local(self, label='Local files'):
        return (self.active_host and self.cloud_busy
                and label == 'Local files')

    async def browse_local_during_transfer(self, folder):
        previous = getattr(self, '_local_browse_cancel', None)
        if previous is not None:
            previous.set()
        cancel = self._local_browse_cancel = threading.Event()
        provider = LocalFiles(self.private_root / 'LocalFiles')
        path = provider.relative(folder)
        try:
            rows = await asyncio.to_thread(provider.list, path, cancelled=cancel.is_set)
            if (not self.active_host or cancel.is_set()
                    or (self.file_storage.value, self.file_location.value) != ('Local files', folder)):
                return False
            self.file_provider, self.file_path = provider, path
            self.file_rows = {f'{i + 1}. {"Folder" if row["directory"] else "File"}: {row["name"]}' : row
                              for i, row in enumerate(rows)}
            self.set_file_items(list(self.file_rows))
            self.file_loaded_location = 'Local files', path
            self.populate_file_browser(rows, location=self.file_loaded_location)
            self.file_status.value = f'{path or "Local files"} · {len(rows)} items'
            return True
        except Exception as error:
            if self.active_host and not cancel.is_set():
                self.file_status.value = 'Could not browse local folder: ' + str(error)[:200]
            return False

    async def show_files(self, widget=None, *, local_root=False, **kwargs):
        if self.cloud_busy and not self.can_browse_local():
            return
        if (hasattr(self, 'files_view') and self.file_provider is not None
                and not self.file_browser.closed):
            if not self.cloud_busy:
                roots = {'Local files': None, **self.existing_crypt_locations(), **self.linked_crypt_locations()}
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
            if self.cloud_busy or local_root:
                self.file_changing_location = True
                try:
                    self.file_storage.value = 'Local files'
                    self.file_location.value = self.file_path if (not local_root and type(self.file_provider) is LocalFiles
                        and self.file_provider.root == self.private_root / 'LocalFiles') else ''
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
        self.file_roots = {'Local files': None}
        if not self.cloud_busy:
            self.file_roots.update(self.existing_crypt_locations())
            self.file_roots.update(self.linked_crypt_locations())
        self.file_storage = toga.Selection(items=list(self.file_roots), style=Pack(height=44))
        self.file_storage.value = 'Local files'
        self.file_location = toga.TextInput(placeholder='Folder path (empty for root)', style=Pack(height=44))
        self.file_selection = toga.Selection(style=Pack(height=44))
        from .browser_ui import FileBrowser as NativeBrowser
        self.file_browser = NativeBrowser(selected=self.browser_file_selected, open_folder=self.browser_file_folder, navigate=self.browser_file_location, open_file=self.browser_file_open, item_actions=self.show_file_actions)
        self.file_password = toga.PasswordInput(placeholder='Inner archive password, when needed', style=Pack(height=44))
        self.file_name = toga.TextInput(placeholder='New name / folder name', style=Pack(height=44))
        self.file_destination = toga.Selection(items=list(self.file_roots), style=Pack(height=44))
        self.file_target = toga.TextInput(placeholder='Destination path including name', style=Pack(height=44))
        (self.private_root / 'LocalFiles').mkdir(exist_ok=True)
        self.file_status = toga.MultilineTextInput(readonly=True, style=Pack(height=48, font_size=12))
        self.file_action_status = toga.Label('', style=Pack(font_size=12, margin_top=8))
        self.file_rows, self.file_provider = {}, None
        buttons = [toga.Button(label, on_press=handler, style=Pack(height=44)) for label, handler in (
            ('Browse folder', self.browse_files), ('Open folder', self.enter_file_folder),
            ('Open file', self.read_managed_file), ('New folder', self.new_file_folder),
            ('Rename selected', self.rename_file), ('Delete selected…', self.delete_file),
            ('Move selected', self.move_file), ('Use selected offline encrypted copy', self.use_downloaded_file),
            ('Cancel operation', self.cancel_cloud), ('Back to remote files', self.files_back))]
        self.file_commands = buttons
        self.file_operation_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
            toga.Button('Folder Hub', on_press=self.show_locations, style=Pack(height=44)),
            toga.Label('Local files and folders'), self.file_storage, self.file_location, buttons[0],
            toga.Button('Parent folder', on_press=self.parent_file_folder, style=Pack(height=44)),
            self.file_password, self.file_browser.widget, buttons[1], buttons[2], self.file_name, *buttons[3:6],
            toga.Label('Move destination'), self.file_destination, self.file_target, *buttons[6:],
            toga.Button('Use selected private download', on_press=self.use_local_download, style=Pack(height=44)),
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
        self.file_actions_button = toga.Button('•••', style=Pack(width=44, height=44))
        self.file_actions = FeatureCommands(self.file_actions_button, self,
            [('New folder…', lambda: self.show_file_actions(operation='new')),
             ('Rename…', lambda: self.show_file_actions(operation='rename')),
             ('Move…', lambda: self.show_file_actions(operation='move')),
             ('Pin current folder', self.pin_local_folder),
             ('Delete selected…', self.delete_file), ('Change location…', lambda: self.show_file_actions(operation='location')),
             ('Archive password…', lambda: self.show_file_actions(operation='password'))], self.show_file_actions)
        self.files_view = toga.Box(children=[
            toga.Box(children=[toga.Button('Folder Hub', on_press=self.show_locations, style=Pack(height=44, flex=1)),
                               self.file_actions_button], style=Pack(direction=ROW)),
            self.file_storage,
            toga.Box(children=[toga.Button('Up', on_press=self.parent_file_folder, style=Pack(height=44)),
                               self.file_status], style=Pack(direction=ROW, margin_top=4)),
            toga.ScrollContainer(horizontal=False, content=scroll_content(self.file_browser.widget), style=Pack(flex=1))],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.file_status.style.flex = 1
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
            commands += [('Archive password…', lambda: self.show_file_actions(operation='password'))]
            for label, callback in commands:
                async def run(widget=None, target=callback, **kw):
                    import inspect
                    result = target()
                    if inspect.isawaitable(result):
                        await result
                box.add(toga.Button(label, on_press=run, style=Pack(height=48, margin_bottom=4)))
        box.add(self.file_action_status)
        box.add(toga.Button('Return to files', on_press=self.show_files, style=Pack(height=44, margin_top=12)))
        self.show_view(self.file_operation_view, destination='files', route='file-actions', title='File actions')

    def show_file_details(self, widget=None, **kwargs):
        info = self.file_browser.info
        if info.parent is not None:
            info.parent.remove(info)
        box = toga.Box(children=[info,
            toga.Button('Return to files', on_press=self.show_files, style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=12))
        self.show_view(toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1)), destination='files',
                       route='file-details', title='File details')

    async def parent_file_folder(self, widget=None, **kwargs):
        if not self.cloud_busy or self.can_browse_local(self.file_storage.value):
            self.file_location.value = self.file_location.value.rpartition('/')[0]
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

    def file_provider_for(self, label):
        return self.storage_provider(label, self.file_roots)

    def storage_provider(self, label, roots):
        """One provider resolution path for browsing, moving and editor pickers."""
        remote = roots[label]
        if isinstance(remote, LocalFiles):
            return remote
        if remote is None:
            root = self.private_root / 'LocalFiles'
            root.mkdir(exist_ok=True)
            return LocalFiles(root)
        return CryptFiles(self.private_root / 'LocalCryptFolders', self.cloud_client, remote)

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
        label, folder = self.file_storage.value, self.file_location.value
        password = self.file_password.value
        result = []
        def work(cancelled):
            provider = self.file_provider_for(label)
            path = provider.relative(folder)
            rows = provider.list(path, cancelled=cancelled)
            result.extend((provider, path, rows))
        completed = await self.file_work(work, mutation=False)
        if (self.file_storage.value, self.file_location.value) != (label, folder):
            # A newer local navigation may have completed while this provider
            # waited for the engine. Never replace that listing with stale rows.
            return False
        if completed:
            self.file_provider, self.file_path, rows = result
            self.file_rows = {f'{i + 1}. {"Folder" if row["directory"] else "File"}: {row["name"]}': row for i, row in enumerate(rows)}
            self.set_file_items(list(self.file_rows))
            self.file_loaded_location = label, self.file_path
            self.populate_file_browser(rows, password, location=self.file_loaded_location)
            self.file_status.value = f'{self.file_path or label} · {len(rows)} items'
            return True
        else:
            if not self.active_host:
                return False
            if self.file_provider is not None and self.file_browser.tree is not None:
                self.file_storage.value, self.file_location.value = self.file_loaded_location
            else:
                self.file_provider = None
                self.file_rows = {}
                self.file_selection.items = []
                self.file_browser.stop()
            return False

    def populate_file_browser(self, rows, password='', *, location=None):
        from .browser_preview import callbacks
        client = None if self.cloud_busy and self.can_browse_local(self.file_storage.value) else self.cloud_client
        self.file_browser.thumbnail, self.file_browser.details = callbacks(self.file_provider, client, password)
        if location is None:
            self.file_browser.history.clear()
        self.file_browser.set_entries(self.file_provider, self.file_path, rows, location=location)

    def selected_file(self):
        row = self.file_rows.get(self.file_selection.value)
        if self.file_provider is None or row is None:
            raise ValueError('Browse and select a file or folder first.')
        return self.file_provider, row['path']

    async def enter_file_folder(self, widget=None, **kwargs):
        if self.cloud_busy:
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

    async def use_downloaded_file(self, widget=None, **kwargs):
        key = self.crypt_labels.get(self.crypt_selector.value)
        result = []
        def work(cancelled):
            if not key:
                raise ValueError('Select an offline encrypted copy on the remote-files screen first.')
            provider = DownloadedCryptFile(self.crypt_copies, key)
            result.extend((provider, provider.entry(provider.name)))
        if await self.file_work(work):
            self.file_provider, row = result
            self.file_path = ''
            self.file_rows = {row['name']: row}
            self.set_file_items(list(self.file_rows))
            self.populate_file_browser([row])
            self.file_status.value = 'Choose a destination and move this existing offline copy into your folders.'

    async def read_managed_file(self, widget=None, **kwargs):
        try:
            provider, path = self.selected_file()
            if self.cloud_busy and not (self.transfer_busy and isinstance(provider, LocalFiles)
                                        and not provider.private):
                return
            if provider.entry(path)['directory']:
                raise ValueError('Choose a file to read.')
            if isinstance(provider, DownloadedCryptFile):
                self.crypt_password.value = self.file_password.value
                await self.open_crypt(copies=provider.copies, key=provider.key, destination='files')
                return
            if not isinstance(provider, CryptFiles):
                if Path(path).suffix.lower() in {'.txt', '.md', '.markdown'}:
                    from .file_resources import LocalTextCopies
                    await self.open_crypt(copies=LocalTextCopies(provider), key=path, destination='files')
                else:
                    await self.open_download(path=provider._locate(path), destination='files')
                return
            self.crypt_password.value = self.file_password.value
            await self.open_crypt(copies=ManagedCopies(provider), key=path, destination='files')
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

    async def show_crypt_save_as(self, widget=None, *, owner=None, **kwargs):
        owner = owner or self.provider_sessions().active
        if self.cloud_busy or owner is None or owner.crypt_reader is None or not owner.crypt_reader.editable:
            return
        self.save_as_source_document = None
        await self.show_text_destination(owner.crypt_reader.name, owner.crypt_reader.text_snapshot.encode(owner.crypt_text.value))

    async def show_document_save_as(self, widget=None, **kwargs):
        if self.current is None:
            return
        name, data = self.current.name, self.current.snapshot.encode(self.current.text)
        if not hasattr(self, 'cloud_view'):
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
        if self.cloud_busy:
            return
        self.save_as_source_document = self.current
        await self.show_text_destination(name, data)

    async def show_editor_open(self, widget=None, **kwargs):
        if not hasattr(self, 'cloud_view'):
            self.show_cloud()
            if getattr(self, 'cloud_restore_task', None):
                await self.cloud_restore_task
        if self.cloud_busy:
            return
        await self.show_editor_browser('open')

    async def show_text_destination(self, name, data):
        await self.show_editor_browser('save', name, data)

    async def show_editor_browser(self, mode, name='', data=None):
        if hasattr(self, 'editor_browser'):
            await self.editor_browser.close()
        self.editor_picker_mode = mode
        self.save_as_data = data
        self.editor_storage_roots = {'Local files': None, **self.existing_crypt_locations()}
        self.editor_linked_roots = self.linked_crypt_locations()
        self.editor_storage_roots.update(self.editor_linked_roots)
        roots = list(self.editor_storage_roots)
        self.editor_picker_rows = {}
        self.save_as_storage = toga.Selection(items=roots, style=Pack(height=44))
        self.picker_folder = toga.TextInput(placeholder='Folder within storage', style=Pack(height=44))
        self.picker_entries = toga.Selection(style=Pack(height=44))
        from .browser_ui import FileBrowser as NativeBrowser
        self.editor_browser = NativeBrowser(selected=self.browser_editor_selected, open_folder=self.browser_editor_folder, navigate=self.browser_editor_location, preview=False)
        self.save_as_name = toga.TextInput(value=name, placeholder='File name', style=Pack(height=44))
        self.save_as_status = toga.MultilineTextInput(readonly=True, style=Pack(height=75))
        self.save_as_view = toga.Box(children=[toga.Label('Open' if mode == 'open' else 'Save As'),
            self.save_as_storage, self.picker_folder,
            toga.Button('Browse folder', on_press=self.refresh_editor_browser, style=Pack(height=44)),
            toga.Button('Parent folder', on_press=self.parent_editor_folder, style=Pack(height=44)),
            self.editor_browser.widget, toga.Button('Choose selected item', on_press=self.select_editor_item, style=Pack(height=44)),
            self.save_as_name, toga.Label('Local files are plaintext. LocalCrypt stays encrypted. Drafts opened here stay in memory.'),
            toga.Button('Open file' if mode == 'open' else 'Save new file', on_press=self.confirm_editor_file, style=Pack(height=44)),
            toga.Button('Cancel', on_press=self.cancel_text_destination, style=Pack(height=44)), self.save_as_status],
            style=Pack(direction=COLUMN, margin=12))
        self.show_view(toga.ScrollContainer(horizontal=False, content=self.save_as_view, style=Pack(flex=1)))
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
        self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        try:
            def read():
                model = ResourceSelection(self.editor_provider(label), mode=self.editor_picker_mode,
                                          extensions=('.txt', '.md', '.markdown', '.ini'))
                return model.list(folder, cancelled=self._crypt_cancel.is_set)
            rows = await asyncio.to_thread(read)
            self.editor_picker_rows = {f'{i+1}. {"Folder" if row["directory"] else "File"}: {row["name"]}': row for i,row in enumerate(rows)}
            self.editor_picker_location = label, folder
            self.picker_entries.items = list(self.editor_picker_rows)
            picker = getattr(self.picker_entries._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            if self.editor_picker_rows:
                self.picker_entries.value = next(iter(self.editor_picker_rows))
            self.editor_browser.set_entries(ResourceSelection(self.editor_provider(label), mode=self.editor_picker_mode, extensions=('.txt', '.md', '.markdown', '.ini')), folder, rows, location=(label, folder))
            self.save_as_status.value = f'{len(rows)} entries. Choose a folder or file.'
            return True
        except Exception as error:
            if self.editor_browser.tree is not None:
                self.save_as_storage.value, self.picker_folder.value = self.editor_picker_location
            else:
                self.editor_picker_rows = {}
                self.picker_entries.items = []
                self.editor_browser.stop()
            self.save_as_status.value = str(error)
            return False
        finally:
            self._crypt_cancel = None
            self.set_cloud_busy(False)

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
        from .file_resources import LocalTextCopies
        label, folder, name = self.save_as_storage.value, self.picker_folder.value, self.save_as_name.value
        self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        try:
            def resolve():
                provider = self.editor_provider(label)
                path = ResourceSelection(provider, extensions=('.txt', '.md', '.markdown', '.ini')).resolve(folder, name, cancelled=self._crypt_cancel.is_set)
                return provider, path
            provider, path = await asyncio.to_thread(resolve)
        except Exception as error:
            self.save_as_status.value = str(error)
            return
        finally:
            self._crypt_cancel = None
            self.set_cloud_busy(False)
        await self.open_crypt(copies=ManagedCopies(provider) if provider.private else LocalTextCopies(provider), key=path)

    def cancel_text_destination(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.save_as_data = None
            self.resume_crypt() if self.provider_sessions().active is not None else self.show_documents()

    async def save_text_destination(self, widget=None, **kwargs):
        from commonUtils.runtime.resource_mutations import save_resource_and_reopen
        from .file_resources import LocalTextCopies
        if self.cloud_busy or self.save_as_data is None:
            return
        target, label, data = self.save_as_name.value, self.save_as_storage.value, self.save_as_data
        folder = self.picker_folder.value
        self.set_cloud_busy(True)
        self._crypt_cancel = threading.Event()
        try:
            if Path(target).suffix.lower() not in {'.txt', '.md', '.markdown'} or len(data) > 1024 * 1024:
                raise ValueError('Choose a text or Markdown filename; saves are limited to 1 MiB.')
            def save():
                provider = self.editor_provider(label)
                destination = ResourceSelection(provider, mode='save', extensions=('.txt', '.md', '.markdown', '.ini')).resolve(folder, target, cancelled=self._crypt_cancel.is_set)
                source_document = getattr(self, 'save_as_source_document', None)
                if provider.private and source_document is not None:
                    self.store.privatize(source_document)
                copies = ManagedCopies(provider) if provider.private else LocalTextCopies(provider)
                def reopen():
                    reader = copies.open(destination)
                    if reader.data != data:
                        raise ValueError('The saved file changed after publication.')
                    kind, content = reader.page(0)
                    return copies, destination, (reader, kind, content)
                return save_resource_and_reopen(provider, destination, data, reopen=reopen, cancelled=self._crypt_cancel.is_set)
            copies, destination, prepared = await asyncio.to_thread(save)
            if not self.active_host:
                return
            self._crypt_cancel = None
            self.set_cloud_busy(False)
            if await self.open_crypt(copies=copies, key=destination, prepared=prepared):
                self.save_as_data = None
                source_document = getattr(self, 'save_as_source_document', None)
                if source_document is not None and getattr(source_document, 'private', False):
                    source_document.text = source_document.snapshot.text
                    if self.current is source_document:
                        self.loading = True
                        try:
                            self.editor.value = source_document.text
                        finally:
                            self.loading = False
                    source_document.private = False
                    self.store.checkpoint(source_document)
                self.save_as_source_document = None
            else:
                self.save_as_status.value = 'The file was saved, but its editor could not be opened. The Save As draft is retained.'
                self.show_view(self.save_as_view)
        except MutationIncomplete as error:
            self.save_as_status.value = str(error) + '\nRefresh before retrying; your draft remains available.'
        except Exception as error:
            self.save_as_status.value = 'Save As failed; draft retained: ' + str(error)[:200]
        finally:
            self._crypt_cancel = None
            self.set_cloud_busy(False)
