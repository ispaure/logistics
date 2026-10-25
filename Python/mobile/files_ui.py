"""Native local file management; shared operations own transfer correctness."""
from commonUtils.ui.native.password_input import PasswordInput
from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS

from features.rclone.mobile.storage_location import collection_path
import asyncio
from pathlib import Path
import toga
from .control_icons import icon_button
from services.workflow_host import OwnedAttribute
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from commonUtils.runtime.resources.local import LocalFiles
from features.rclone.localcrypt.mobile.resources import encrypted_document


def local_read_available(app, *, private=True):
    """Offline reads may share a managed transfer; credential operations still wait."""
    return (app.active_host and not getattr(app, '_storage_changing', False) and (not private or not getattr(app, 'cloud_busy', False)
            or getattr(app, 'transfer_busy', False) or getattr(app, 'remote_read_busy', False)))


def ordinary_local_copies(copies):
    provider = getattr(copies, 'provider', None)
    return (isinstance(provider, LocalFiles) and not provider.private
        and not getattr(copies, 'encrypted', True) and not getattr(copies, 'remote_storage', False))


class FilesUI:
    def folder_listing(self):
        if not hasattr(self, '_folder_listing'):
            from .folder_listing import FolderListing
            self._folder_listing = FolderListing(active=lambda: self.active_host,
                context=lambda: (id(self.file_browser),
                    id(getattr(self, 'file_roots', {}).get(self.file_storage.value))),
                location=lambda: (self.file_storage.value, self.file_location.value),
                credentials=lambda: (self.cloud_client, getattr(self.cloud_client, 'generation', None)))
        return self._folder_listing

    def file_operations(self):
        if not hasattr(self, '_file_operations'):
            from .composition.presentation import file_operations
            self._file_operations = file_operations(self)
        return self._file_operations

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
        listing = FilesUI.folder_listing(self)
        work = listing.begin()
        # Keep the existing cancellation handle available to compatibility callers.
        self._local_browse_cancel = work.cancel
        browser = self.file_browser
        with browser.population_paused():
            label = self.file_storage.value
            request = None
            try:
                provider = self.file_provider_for(label)
                path = provider.relative(folder)
                request = listing.capture(work, provider, path, (label, folder))
                rows = await listing.read(request)
                if rows is None:
                    return False
                self.file_provider, self.file_path = provider, path
                self.file_rows = {f'{i + 1}. {"Folder" if row["directory"] else "File"}: {row["name"]}' : row
                                  for i, row in enumerate(rows)}
                # set_entries publishes selection reset once with the new snapshot.
                self.file_loaded_location = label, path
                self.populate_file_browser(rows, self.file_password.value, location=self.file_loaded_location)
                self.file_status.value = ''
                return True
            except Exception as error:
                if (listing.accepts(work, request, private=request is None)
                        and (self.file_storage.value, self.file_location.value) == (label, folder)):
                    self.file_status.value = 'Could not browse local folder: ' + str(error)[:200]
                    if self.file_provider is not None and browser.tree is not None:
                        self.file_changing_location = True
                        try:
                            self.file_storage.value, self.file_location.value = self.file_loaded_location
                        finally:
                            self.file_changing_location = False
                        self.refresh_file_source_tabs()
                    else:
                        self.file_provider = None
                        self.file_rows = {}
                        self.file_selection.items = []
                        browser.stop()
                return False

    async def show_files(self, widget=None, *, local_root=False, location=None, **kwargs):
        # Files can be opened directly from Home/Documents on a cold launch.
        # Ordinary local browsing does not depend on saved credentials.
        if not hasattr(self, 'cloud_view'):
            self.show_cloud(present=False)
        if not self.active_host or getattr(self, '_storage_changing', False):
            return
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
            opened = None
            if location is not None:
                self.files_view._folder_entry_location = location
                self.file_browser.search.value = ''
                self.file_browser.history.clear()
                opened = await self.browser_file_location(location)
            elif local_root or (self.cloud_busy and not self.can_browse_local(self.file_storage.value)):
                self.files_view._folder_entry_location = (self.local_browser_root(), '')
                self.file_changing_location = True
                try:
                    self.file_storage.value = self.local_browser_root()
                    self.file_location.value = self.file_path if (not local_root and isinstance(self.file_provider, LocalFiles)
                        and self.file_provider.root == collection_path(self.private_root)) else ''
                finally:
                    self.file_changing_location = False
                if local_root:
                    self.file_browser.search.value = ''
                    self.file_browser.history.clear()
                opened = await self.browse_files()
            self.refresh_file_source_tabs()
            self.show_view(self.files_view, destination='files', route='browser', title='Local File Browser')
            return opened
        if hasattr(self, 'file_browser'):
            await self.file_browser.close()
        self._build_file_browser(location)
        self.refresh_file_source_tabs()
        self.show_view(self.files_view, destination='files', route='browser', title='Local File Browser')
        opened = await self.browse_files()
        self.file_storage.on_change = self.change_file_storage
        return opened

    def _build_file_browser(self, location):
        """Construct browser/command controls before route publication and first listing."""
        self.file_roots = self.ordinary_file_roots()
        if local_read_available(self, private=True):
            self.file_roots.update(self.existing_crypt_locations())
            self.file_roots.update(self.linked_crypt_locations())
        self.file_storage = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_storage.value = self.local_browser_root()
        self.file_location = toga.TextInput(placeholder='Folder path (empty for root)', style=Pack(height=48))
        if location is not None:
            self.file_storage.value, self.file_location.value = location
        self.file_selection = toga.Selection(style=Pack(height=48))
        from .browser_ui import FileBrowser as NativeBrowser
        self.file_browser = NativeBrowser(folder_visible=self.folder_path_visible, selected=self.browser_file_selected, open_folder=self.browser_file_folder, navigate=self.browser_file_location, open_file=self.browser_file_open)
        self.file_browser.on_item_actions = lambda row: self.file_browser.show_item_menu(self.file_item_commands())
        self.file_browser.navigation_controls.remove(self.file_browser.back_button)
        self.file_password = PasswordInput(placeholder='Inner archive password, when needed', style=Pack(height=48))
        self.file_name = toga.TextInput(placeholder='New name / folder name', style=Pack(height=48))
        self.file_destination = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_target = toga.TextInput(placeholder='Destination path including name', style=Pack(height=48))
        (collection_path(self.private_root)).mkdir(exist_ok=True)
        self.file_status = NativeBrowser.status_label(style=Pack(height=20, margin_top=14, margin_bottom=14, font_size=15))
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
            toga.Button('Workspaces', on_press=self.show_locations, style=Pack(height=48)),
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
        operation_box.remove(self.file_status)
        operation_box.remove(buttons[1])
        operation_box.remove(buttons[2])
        operation_box.remove(self.file_storage)
        from .action_menu import FeatureCommands
        self.file_actions_button = icon_button('overflow', 'File and folder actions')
        self.file_actions = FeatureCommands(self.file_actions_button, self,
            [('New folder…', lambda: self.show_file_actions(operation='new')),
             ('Rename…', lambda: self.show_file_actions(operation='rename')),
             ('Move…', lambda: self.show_file_actions(operation='move')),
             ('Pin current folder', self.pin_local_folder),
             ('Delete selected…', self.delete_file), ('Change location…', lambda: self.show_file_actions(operation='location')),
             ('Archive password…', lambda: self.show_file_actions(operation='password'))], self.show_file_actions)
        self.file_browser.attach_location_header(self.file_status,
            icon_button('back', 'Back to Workspaces', on_press=self.parent_file_folder))
        from .browser_ui import browser_command
        browser_command(self.file_actions_button)
        self.file_browser.location_bar.add(self.file_actions_button)
        self.file_source_tabs = toga.Box(style=Pack(direction=ROW, height=48))
        self.files_view = toga.Box(children=[
            self.file_browser.location_bar,
            self.file_browser.scroll_container()],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.files_view._folder_entry_location = location or (self.local_browser_root(), '')

    def refresh_file_source_tabs(self):
        if not hasattr(self, 'file_source_tabs'):
            return
        # Workspaces owns source selection. A folder browser has one active
        # provider, described by its location header on every platform.
        for child in list(self.file_source_tabs.children):
            self.file_source_tabs.remove(child)
        self.file_source_buttons = {}
        if self.file_source_tabs.parent is not None:
            self.file_source_tabs.parent.remove(self.file_source_tabs)

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
        self.refresh_file_source_tabs()
        if selected != loaded:
            self.file_location.value = ''
            return self.loop.create_task(self.browse_files())

    def show_file_actions(self, widget=None, *, operation=None, **kwargs):
        if self.cloud_busy:
            return
        if operation == 'move':
            try:
                provider, path = self.selected_file()
            except ValueError as error:
                self.file_status.value = str(error)
                return
            if not self.file_operations().host.allowed(False):
                return
            from .file_operations import FileOperationRequest
            request = FileOperationRequest('move', provider, path)
            return self.loop.create_task(self.editor_picker().show_destination(
                path.rpartition('/')[2], request))
        box = self.file_operation_view.content
        for child in list(box.children):
            box.remove(child)
        selected = self.file_rows.get(self.file_selection.value)
        title = selected['name'] if selected else 'Workspace actions'
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
            commands = self.file_item_commands()
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

    def file_item_commands(self):
        selected = self.file_rows.get(self.file_selection.value)
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
        return commands + [('Archive password…', lambda: self.show_file_actions(operation='password'))]

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
        if (self.file_storage.value, self.file_path) == getattr(self.files_view, '_folder_entry_location', None):
            self.show_locations()
            return
        if not self.file_path and self.file_storage.value == 'Local files' and self.local_browser_root() == 'Shared files':
            return await self.browser_file_location(('Shared files', ''))
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
        if not self.app.routes.folders.restoring:
            self.app.routes.folders.capture()
        label, path = location
        local_name = collection_path(self.private_root).name
        if label == 'Shared files' and (path == local_name or path.startswith(local_name + '/')):
            location = ('Local files', path.removeprefix(local_name).lstrip('/'))
        if self.cloud_busy and not self.can_browse_local(location[0]):
            return False
        self.file_changing_location = True
        try:
            self.file_storage.value, self.file_location.value = location
        finally:
            self.file_changing_location = False
        self.refresh_file_source_tabs()
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

        self.refresh_file_source_tabs()

    def files_back(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_cloud()

    def local_browser_root(self):
        return 'Shared files' if 'Shared files' in self.ordinary_file_roots() else 'Local files'

    def ordinary_file_roots(self):
        from .local_sources import device_files
        from .incoming_files import inbox_path
        roots = {'Local files': None, 'Shared files': device_files(self.private_root),
                 'Received Files': LocalFiles(inbox_path(self.private_root))}
        return roots

    def file_provider_for(self, label):
        return self.storage_provider(label, self.file_roots)

    def storage_provider(self, label, roots):
        """One provider resolution path for browsing, moving and editor pickers."""
        from .file_operations import FileDestination
        location = roots[label]
        if isinstance(location, LocalFiles):
            if getattr(location, 'closed', False) and hasattr(location, 'reopen'):
                location = roots[label] = location.reopen()
            return location
        client = self.cloud_client if location is not None else None
        return FileDestination(self.private_root, client, location, getattr(client, 'generation', None)).resolve()

    async def file_work(self, work, *, mutation=True):
        # Compatibility for existing callbacks; built-in commands use captured requests.
        return await self.file_operations().run(lambda: work, mutation=mutation)

    def capture_file_operation(self, kind):
        from .file_operations import FileDestination, FileOperationRequest
        row = self.file_rows.get(self.file_selection.value)
        path = row['path'] if row else None
        if kind == 'new':
            return FileOperationRequest(kind, self.file_provider, self.file_path, self.file_name.value)
        if kind == 'rename':
            return FileOperationRequest(kind, self.file_provider, path, self.file_name.value)
        if self.file_provider is None or path is None:
            return FileOperationRequest(kind, self.file_provider, path)
        client = self.cloud_client
        destination = FileDestination(self.private_root, client, self.file_roots[self.file_destination.value],
                                      getattr(client, 'generation', None))
        return FileOperationRequest(kind, self.file_provider, path, self.file_target.value, destination)

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
        # A folder listing needs names and filesystem metadata, not archive
        # covers or decrypted content. Rich details remain explicit actions.
        _, self.file_browser.details = callbacks(self.file_provider, client, password)
        self.file_browser.thumbnail = None
        if location is None:
            self.file_browser.history.clear()
        self.file_browser.set_entries(self.file_provider, self.file_path, rows, location=location)
        managed_root = (self.file_storage.value == 'Local files' and not self.file_path
                        and self.local_browser_root() == 'Shared files')
        name = (Path(self.file_path).name if self.file_path else
                'Local' if managed_root else
                'On this device' if self.file_storage.value in ('Local files', 'Shared files') else self.file_storage.value)
        self.file_browser.location_bar.update_provider(self.file_path or ('Local' if managed_root else ''),
            self.file_provider, name=name)
        from .folder_navigation import record
        record(getattr(self, 'app', self), self.files_view, self.file_browser, 'browser', self.file_storage.value,
               self.file_path, self.browser_file_location)

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
            return await self.browser_file_location((self.file_storage.value, row['path']))

    async def new_file_folder(self, widget=None, **kwargs):
        if await self.file_operations().run(lambda: self.capture_file_operation('new')):
            await self.browse_files()

    async def rename_file(self, widget=None, **kwargs):
        if await self.file_operations().run(lambda: self.capture_file_operation('rename')):
            await self.browse_files()

    async def delete_file(self, widget=None, **kwargs):
        from .file_operations import FileOperationRequest
        if self.cloud_busy:
            return
        try:
            provider, path = self.selected_file()
        except ValueError as error:
            self.file_status.value = str(error)
            return
        request = FileOperationRequest('delete', provider, path)
        if not await self.main_window.dialog(toga.ConfirmDialog('Delete permanently', 'Delete this item and all contents? This cannot be undone.')):
            return
        if await self.file_operations().run(lambda: request):
            await self.browse_files()

    async def move_file(self, widget=None, **kwargs):
        if not self.file_operations().host.allowed(False):
            return
        # Capture before confirmation so changing selection cannot move a
        # different item when the native dialog returns.
        try:
            request = self.capture_file_operation('move')
            location = request.destination.location if request.destination else None
            plaintext = location is None or (isinstance(location, LocalFiles) and not location.private)
            if request.provider is not None and request.provider.private and plaintext:
                if not await self.main_window.dialog(toga.ConfirmDialog('Move to unencrypted storage?',
                        'The destination will contain a decrypted copy. Continue?')):
                    return
                from dataclasses import replace
                request = replace(request, plaintext_approved=True)
        except (OSError, ValueError, KeyError) as error:
            self.file_status.value = str(error)
            return
        if await self.file_operations().run(lambda: request):
            await self.browse_files()
            await self.refresh_crypt()

    async def read_managed_file(self, widget=None, **kwargs):
        try:
            provider, path = self.selected_file()
            if self.file_storage.value == 'Shared files' and path.startswith('Local/'):
                # Search can find collection files from the outer root. Keep
                # their editor identity the same as opening inside Collection.
                provider, path = self.file_provider_for('Local files'), path.removeprefix('Local/')
            if self.cloud_busy and not (local_read_available(self, private=getattr(provider, 'private', False)) and isinstance(provider, LocalFiles)):
                return
            if provider.entry(path)['directory']:
                raise ValueError('Choose a file to read.')
            if Path(path).suffix.lower() == '.rmdoc' and isinstance(provider, LocalFiles) and not getattr(provider, 'private', False):
                if self.app.select_destination('notebooks') is False:
                    return False
                self.app.native_host.activate('notebooks')
                await self.app.notebook_panel.open_path(provider._locate(path))
                return True
            source = encrypted_document(provider, path)
            if source is not None:
                self.crypt_password.value = self.file_password.value
                copies, key = source
                return await self.open_crypt(copies=copies, key=key)
            elif Path(path).suffix.lower() in SOURCE_EXTENSIONS:
                from features.text_editor.resources import LocalTextCopies
                return await self.open_crypt(copies=LocalTextCopies(provider), key=path)
            else:
                return await self.open_download(path=provider._locate(path))
        except ValueError as error:
            self.file_status.value = str(error)
            return False

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
        return await self.comic_batch_controller().edit_local_comic_folder(widget, **kwargs)

    def retire_private_comic_batch(self, *, view=None, stale_only=False):
        return self.comic_batch_controller().retire_private_comic_batch(view=view, stale_only=stale_only)

    async def edit_private_comic_folder(self):
        return await self.comic_batch_controller().edit_private_comic_folder()
