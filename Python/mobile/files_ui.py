"""Native local file management; shared operations own transfer correctness."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.ui.native.password_input import PasswordInput

from services.documents.locations import collection_path
import asyncio
from pathlib import Path
import toga
from .control_icons import icon_button
from services.workflow_host import OwnedAttribute
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.runtime.resources.provider import capabilities


def local_read_available(app, *, private=True):
    """Offline reads may share a managed transfer; credential operations still wait."""
    return (app.active_host and not getattr(app, '_storage_changing', False) and (not private or not getattr(app, 'cloud_busy', False)
            or getattr(app, 'transfer_busy', False) or getattr(app, 'remote_read_busy', False)))


def ordinary_local_copies(copies):
    from services.documents.mobile_reading import reading_capabilities
    capabilities = reading_capabilities(copies)
    return capabilities.offline and not capabilities.private and not capabilities.remote


class FileSelectionUI:
    """Bulk selection for a browser with its own provider and folder listing."""

    selection_destination_finished = None

    def build_file_selection(self):
        from .appearance import accessible_name, action_button, surface

        self.file_browser.finish_selection = self.end_file_selection
        self.file_checked = {}
        self.file_selection_count = toga.Label('0 selected', style=Pack(flex=1, font_size=14, margin_left=8))
        from .control_icons import button_icons
        self.file_move_button = button_icons(action_button(toga.Button(
            'Move…', on_press=self.move_checked_files, style=Pack(height=48))), [('move_file', '')])
        self.file_archive_button = action_button(toga.Button('Archive', on_press=self.create_file_archive,
            enabled=False, style=Pack(height=48)))
        accessible_name(self.file_archive_button, 'Archive selected items')
        self.file_delete_button = action_button(toga.Button('Delete…', on_press=self.delete_checked_files,
            enabled=False, style=Pack(height=48)), destructive=True)
        accessible_name(self.file_delete_button, 'Delete selected items')
        self.file_select_bar = surface(toga.Box(children=[self.file_selection_count, self.file_move_button,
            self.file_archive_button, self.file_delete_button], style=Pack(direction=ROW, align_items=CENTER,
                gap=4)), radius=10, background='alternate')
        self._show_file_selection_bar(False)

    def can_select_file_entries(self, provider):
        from .archive_operations import ordinary
        can_move = capabilities(provider).delete and not getattr(provider, 'read_only', False)
        return can_move or (ordinary(provider) and self.app.feature_enabled('archives'))

    def begin_file_selection(self, widget=None, **kwargs):
        browser = self.file_browser
        if (self.app.cloud_busy or browser.on_check_entry is not None
                or not self.can_select_file_entries(self.file_provider)):
            return
        if browser.search_open:
            browser.close_search()
        browser.on_check_entry = self.check_file_entry
        browser.highlight_selection()
        self.file_move_button.enabled = self.file_archive_button.enabled = self.file_delete_button.enabled = False
        self.file_selection_count.text = '0 selected'
        can_delete = capabilities(self.file_provider).delete and not getattr(self.file_provider, 'read_only', False)
        self.file_move_button.style.display = self.file_delete_button.style.display = 'pack' if can_delete else 'none'
        from .archive_operations import ordinary
        self.file_archive_button.style.display = ('pack' if ordinary(self.file_provider)
                                                  and self.app.feature_enabled('archives') else 'none')
        self._show_file_selection_bar(True)

    def _show_file_selection_bar(self, visible):
        visibility = 'visible' if visible else 'hidden'
        # Toga iOS mounts Pack children as native siblings of their Box.
        for control in self.file_select_bar.children:
            control.style.visibility = visibility if control.style.display != 'none' else 'hidden'
        self.file_select_bar.style.update(height=48 if visible else 0,
            display='pack' if visible else 'none', visibility=visibility)
        browser = self.file_browser
        header = browser.location_bar
        if getattr(header, 'file_selection_mode', False) == visible:
            return
        header.file_selection_mode = browser.widget._file_selection_mode = visible
        self.update_file_selection_controls(visible)

    def check_file_entry(self, entry):
        if self.app.cloud_busy:
            return
        from .local_sources import SharedFiles
        if isinstance(self.file_provider, SharedFiles) and self.file_provider.is_managed_collection(entry.payload['path']):
            return
        if entry.identity in self.file_checked:
            del self.file_checked[entry.identity]
        else:
            self.file_checked[entry.identity] = entry.payload
        self.file_browser.checked_entries = set(self.file_checked)
        self.file_browser.highlight_selection()
        self.file_move_button.enabled = bool(self.file_checked) and self.file_move_button.style.display != 'none'
        self.file_archive_button.enabled = bool(self.file_checked)
        self.file_delete_button.enabled = bool(self.file_checked) and self.file_delete_button.style.display != 'none'
        self.file_selection_count.text = f'{len(self.file_checked)} selected'

    async def move_checked_files(self, widget=None, **kwargs):
        from .file_operations import FileSelectionMove

        provider = self.file_provider
        if (self.app.cloud_busy or not self.file_checked or not capabilities(provider).delete
                or getattr(provider, 'read_only', False)):
            return
        selection = self.selected_file_roots()
        folder = self.file_path
        self.end_file_selection()
        action = FileSelectionMove(provider, selection, on_complete=self.selection_destination_finished)
        await self.app.editor_picker().show_destination('', action, start_folder=folder)

    def selected_file_roots(self):
        entries = {row['path']: row['revision'] for row in self.file_checked.values()}
        return tuple((path, revision) for path, revision in entries.items()
                     if not any(parent.as_posix() in entries for parent in Path(path).parents))

    async def delete_checked_files(self, widget=None, **kwargs):
        from .file_operations import FileOperationRequest

        provider = self.file_provider
        if (self.app.cloud_busy or self.file_browser.on_check_entry is None or not self.file_checked
                or not capabilities(provider).delete or getattr(provider, 'read_only', False)):
            return
        browser = self.file_browser
        client = self.app.cloud_client
        generation = getattr(client, 'generation', None)
        navigation = self.app.navigation_generation
        selection = self.selected_file_roots()
        requests = tuple(FileOperationRequest('delete', provider, path, expected_revision=revision)
                         for path, revision in selection)
        count = len(requests)
        items = 'item' if count == 1 else 'items'
        if not await self.app.main_window.dialog(toga.ConfirmDialog(f'Delete {count} selected {items}?',
                'This permanently deletes the selected files, folders and their contents.')):
            return
        if (not self.app.active_host or self.file_browser is not browser or browser.on_check_entry is None
                or self.file_provider is not provider or self.app.cloud_busy or self.app.cloud_client is not client
                or getattr(client, 'generation', None) != generation or self.app.navigation_generation != navigation
                or self.selected_file_roots() != selection):
            return
        completed = []
        self.end_file_selection()
        result = await self.file_operations().run_selection(requests, completed.append, verb='Deleting')
        if (result is not None and self.app.navigation_generation == navigation
                and self.file_provider is provider):
            failures, _, cancelled = result
            await self.browse_files()
            summary = 'Deletion stopped.' if cancelled else f'Deleted {len(completed)} of {count} {items}.'
            self.file_status.value = '\n'.join((summary, *failures))

    async def create_file_archive(self, widget=None, **kwargs):
        from .archive_ui import controller
        from .archive_operations import ArchiveItem, ordinary
        provider = self.file_provider
        if ordinary(provider) and self.app.feature_enabled('archives'):
            sources = tuple(ArchiveItem.from_row(provider, row) for row in self.file_checked.values())
            if sources:
                self.end_file_selection()
                await controller(self.app).create(sources, on_complete=self.selection_destination_finished)

    def end_file_selection(self, widget=None, **kwargs):
        self.file_checked.clear()
        self.file_browser.on_check_entry = None
        self.file_browser.checked_entries.clear()
        self.file_browser.highlight_selection()
        self._show_file_selection_bar(False)


class FilesUI(FileSelectionUI):
    @staticmethod
    def file_browser_rows(rows, provider=None):
        from services.documents.locations import visible_transfer_rows
        return {f'{i + 1}. {"Folder" if row["directory"] else "File"}: {row["name"]}': row
                for i, row in enumerate(visible_transfer_rows(provider, rows))}

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

    async def browse_local_during_transfer(self, folder, *, preserve_listing=False):
        listing = FilesUI.folder_listing(self)
        work = listing.begin()
        # Keep the existing cancellation handle available to compatibility callers.
        self._local_browse_cancel = work.cancel
        browser = self.file_browser
        app = getattr(self, 'app', self)
        origin = getattr(app, 'navigation_generation', None)
        def restore_location():
            if (listing.work is work and browser is self.file_browser and hasattr(self, 'file_loaded_location')
                    and (self.file_storage.value, self.file_location.value) == (label, folder)):
                self.file_changing_location = True
                try:
                    self.file_storage.value, self.file_location.value = self.file_loaded_location
                finally:
                    self.file_changing_location = False
                self.refresh_file_source_tabs()
        with browser.population_paused():
            label = self.file_storage.value
            request = None
            try:
                provider = self.file_provider_for(label)
                path = provider.relative(folder)
                request = listing.capture(work, provider, path, (label, folder))
                browser._notes_requested_location = (str(getattr(provider, 'root', '')), getattr(provider, 'remote', ''), path)
                rows = await listing.read(request)
                if rows is None or getattr(app, 'navigation_generation', None) != origin:
                    restore_location()
                    return False
                if (self.app.navigation_generation != origin
                        or not listing.accepts(work, request)):
                    restore_location()
                    return False
                location = label, path
                same_folder = getattr(self, 'file_loaded_location', None) == location
                preserve = preserve_listing and same_folder and self.file_provider is provider and browser.folder_tree is not None
                if not same_folder:
                    self.end_file_selection()
                self.file_provider, self.file_path = provider, path
                self.file_rows = FilesUI.file_browser_rows(rows, provider)
                # set_entries publishes selection reset once with the new snapshot.
                self.file_loaded_location = location
                if preserve:
                    browser.refresh_entries(rows)
                else:
                    self.populate_file_browser(rows, self.file_password.value, location=location)
                self.refresh_file_source_tabs()
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
        if not self.active_host or getattr(self, '_storage_changing', False):
            return False
        try:
            collection_path(self.private_root)
        except (OSError, ValueError) as error:
            await self.main_window.dialog(toga.InfoDialog('Collection drive unavailable', str(error)))
            return False
        if self.cloud_busy and not self.can_browse_local():
            return False
        if (hasattr(self, 'files_view') and self.file_provider is not None
                and not self.file_browser.closed):
            if local_read_available(self, private=True):
                roots = {**self.ordinary_file_roots(include_collections=False), **self.existing_crypt_locations(), **self.linked_crypt_locations()}
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
            previous_notes = getattr(self.app, 'vault_browser', None)
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
            if getattr(self.app, 'vault_browser', None) is not previous_notes:
                return opened
            if opened is False:
                return False
            self.refresh_file_source_tabs()
            if self.show_view(self.files_view, destination='files', route='browser', title='Local File Browser') is False:
                return False
            return opened
        if hasattr(self, 'file_browser'):
            await self.file_browser.close()
        self._build_file_browser(location)
        self.refresh_file_source_tabs()
        # A direct folder shortcut must make the choice over its origin screen.
        previous_notes = getattr(self.app, 'vault_browser', None)
        opened = await self.browse_files()
        self.file_storage.on_change = self.change_file_storage
        if getattr(self.app, 'vault_browser', None) is not previous_notes:
            return opened
        if not opened:
            return False
        if self.show_view(self.files_view, destination='files', route='browser', title='Local File Browser') is False:
            return False
        return opened

    def _build_file_browser(self, location):
        """Construct browser/command controls before route publication and first listing."""
        self.file_roots = self.ordinary_file_roots(include_collections=False)
        if local_read_available(self, private=True):
            self.file_roots.update(self.existing_crypt_locations())
            self.file_roots.update(self.linked_crypt_locations())
        self.file_storage = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_storage.value = self.local_browser_root()
        self.file_location = toga.TextInput(placeholder='Folder path (empty for root)', style=Pack(height=48))
        if location is not None:
            self.file_storage.value, self.file_location.value = location
        self.file_selection = toga.Selection(style=Pack(height=48))
        from .file_browser_view import LocalFileBrowser
        self.file_browser = LocalFileBrowser(folder_visible=self.folder_path_visible, selected=self.browser_file_selected, open_folder=self.browser_file_folder, navigate=self.browser_file_location, open_file=self.browser_file_open)
        self.file_browser.install_item_commands(lambda row: self.file_item_commands(row=row))
        backend = self.file_browser.native_list.factory.DetailedList.__module__
        if backend.startswith('toga_iOS.'):
            from .native.file_drag_ios import install as install_file_drag
            install_file_drag(self, self.file_browser)
        elif backend.startswith('toga_android.'):
            from .native.file_drag_android import install as install_file_drag
            install_file_drag(self, self.file_browser)
        from weakref import ref
        from .native.file_shortcuts import install
        owner = ref(self)

        def file_key(browser, key):
            current = owner()
            return current is not None and current.file_browser is browser and current.file_move_shortcut(key)

        install(self.file_browser, file_key)
        self.file_browser.navigation_controls.remove(self.file_browser.back_button)
        self.file_password = PasswordInput(placeholder='Inner archive password, when needed', style=Pack(height=48))
        from .filename_input import FilenameInput
        self.file_name = FilenameInput(placeholder='New name / folder name', style=Pack(height=48))
        self.file_destination = toga.Selection(items=list(self.file_roots), style=Pack(height=48))
        self.file_target = toga.TextInput(placeholder='Destination path including name', style=Pack(height=48))
        (collection_path(self.private_root)).mkdir(exist_ok=True)
        self.file_status = LocalFileBrowser.status_label(style=Pack(height=20, margin_top=14, margin_bottom=14, font_size=15))
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
        self.file_actions_button.style.update(display='none', visibility='hidden')
        self.file_actions = FeatureCommands(self.file_actions_button, self,
            self.current_folder_commands(), self.show_file_actions)
        self.file_browser.attach_location_header(self.file_status,
            icon_button('back', 'Back to Workspaces', on_press=self.parent_file_folder))
        from .browser_ui import browser_command
        browser_command(self.file_actions_button)
        self.file_browser.location_bar.add(self.file_browser.view_switch, self.file_actions_button)
        self.build_file_selection()
        self.file_source_tabs = toga.Box(style=Pack(direction=ROW, height=48))
        self.files_view = toga.Box(children=[
            self.file_browser.location_bar,
            self.file_select_bar,
            self.file_browser.scroll_container()],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.files_view._refresh_file_listing = lambda: self.browse_files(preserve_listing=True)
        from .scroll_edges import fill_bottom
        fill_bottom(self.files_view, self.file_browser.native_list, self.file_browser._tile_scroll)
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
            row = self.file_rows.get(self.file_selection.value)
            request = FileOperationRequest('move', provider, path, expected_revision=row.get('revision'))
            name = path.rpartition('/')[2]
            return self.loop.create_task(self.editor_picker().show_destination(
                name, request, start_folder=self.file_path))
        box = self.file_operation_view.content
        for child in list(box.children):
            box.remove(child)
        selected = self.file_rows.get(self.file_selection.value)
        item_action = operation in ('rename', 'password')
        title = selected['name'] if item_action and selected else Path(self.file_path).name or 'Folder actions'
        box.add(toga.Label(title, style=Pack(font_size=20, margin_bottom=12)))
        if operation in ('new', 'rename'):
            if operation == 'rename' and selected:
                self.file_name.set_filename(selected['name'], directory=selected['directory'])
            else:
                self.file_name.set_filename('', directory=True)
            self.file_name.placeholder = 'Folder name' if operation == 'new' else 'New name'
            box.add(self.file_name)
            box.add(self.file_commands[3 if operation == 'new' else 4])
        elif operation == 'password':
            box.add(self.file_password,
                    toga.Button('Open with password', on_press=self.read_managed_file, style=Pack(height=48)))
        else:
            for label, callback in self.current_folder_commands():
                async def run(widget=None, target=callback, **kw):
                    import inspect
                    result = target()
                    if inspect.isawaitable(result):
                        await result
                box.add(toga.Button(label, on_press=run, style=Pack(height=48, margin_bottom=4)))
        box.add(self.file_action_status)
        box.add(toga.Button('Return to files', on_press=self.show_files, style=Pack(height=48, margin_top=12)))
        self.show_view(self.file_operation_view, destination='files', route='file-actions', title='File actions')

    def current_folder_commands(self):
        provider = self.file_provider
        access = capabilities(provider)
        commands = []
        if access.create and not getattr(provider, 'read_only', False):
            commands.append(('New folder…', lambda: self.show_file_actions(operation='new')))
        if self.can_select_file_entries(provider):
            commands.append(('Select items', self.begin_file_selection))
        return commands

    def file_item_commands(self, *, context=None, row=None):
        if context is None:
            provider = self.file_provider
            selected = row if row is not None else self.file_rows.get(self.file_selection.value)
        else:
            provider, _, selected = context

        if provider is None or not selected or not selected.get('path'):
            return []
        from .local_sources import SharedFiles
        if isinstance(provider, SharedFiles) and provider.is_managed_collection(selected['path']):
            return [('Open', self.enter_file_folder)]

        access = capabilities(provider)
        writable = not getattr(provider, 'read_only', False)
        commands = [('Open', self.enter_file_folder if selected['directory'] else self.read_managed_file),
                    ('Details', self.show_file_details)]
        if writable and access.rename:
            commands.append(('Rename…', lambda: self.show_file_actions(operation='rename')))
        if writable and access.delete:
            commands.append(('Move…', lambda: self.show_file_actions(operation='move')))
        if self.can_copy_file(provider):
            commands.append(('Duplicate', lambda: self.duplicate_file(provider, selected)))
        if context is None:
            commands.extend(self.app.file_item_actions(provider, selected))
        if not selected['directory'] and Path(selected['path']).suffix.lower() in {'.cbz', '.zip', '.epub'}:
            commands.append(('Archive password…', lambda: self.show_file_actions(operation='password')))
        from .archive_ui import archive_commands
        commands.extend(archive_commands(self.app, provider, selected))
        if writable and access.delete:
            commands.append(('Delete…', self.delete_file))
        return commands

    def update_file_selection_controls(self, visible):
        browser = self.file_browser
        header = browser.location_bar
        if visible:
            header._file_selection_actions = [(control, control.style.display, control.style.visibility)
                for control in (browser.search_button, browser.view_switch, self.file_actions_button)]
            for control, _, _ in header._file_selection_actions:
                control.style.update(display='none', visibility='hidden')
        else:
            for control, display, visibility in header._file_selection_actions:
                control.style.update(display=display, visibility=visibility)
            del header._file_selection_actions
            self._update_file_actions_visibility()
        header.update_back_icon()
        if getattr(header, '_android_title', False):
            header.balance_android_title()
        if self.app.routes.apple and getattr(header, '_native_title_mounted', False):
            self.app.adaptive.render()

    def pending_file_cut(self):
        cut = getattr(self, '_file_cut', None)
        client = self.cloud_client
        if cut is not None and cut[0].private and cut[2] != (client, getattr(client, 'generation', None)):
            self._file_cut = cut = None
        return cut

    def file_move_shortcut(self, key):
        from commonUtils.runtime.resources.provider import capabilities

        if (not self.active_host or self.cloud_busy or self.file_browser.navigation_busy
                or self.file_provider is None):
            return False
        access = capabilities(self.file_provider)
        if key == 'x' and access.delete:
            if not self.file_checked and self.file_selection.value not in self.file_rows:
                return False
            self.cut_files()
            return True
        if key == 'v' and access.create and access.rename and access.delete and self.pending_file_cut():
            task = getattr(self, '_file_paste_shortcut_task', None)
            if task is None or task.done():
                self._file_paste_shortcut_task = self.loop.create_task(self.paste_files())
            return True
        return False

    def cut_files(self, widget=None, **kwargs):
        provider = self.file_provider
        from commonUtils.runtime.resources.provider import capabilities
        if self.cloud_busy or not capabilities(provider).delete:
            return
        selected = self.file_rows.get(self.file_selection.value)
        rows = list(self.file_checked.values()) or ([selected] if selected else [])
        entries = {}
        for row in rows:
            path = row['path']
            if 'revision' not in row:
                self.file_status.value = 'Refresh this folder before cutting these items.'
                return
            entries[path] = row['revision']
        if entries:
            client = self.cloud_client
            self._file_cut = provider, entries, (client, getattr(client, 'generation', None))
            self.end_file_selection()
            if self.file_operation_view is self.body:
                self.loop.create_task(self.show_files())
            self.file_status.value = f'{len(entries)} item(s) cut. Browse to the destination and choose Paste move here.'

    async def paste_files(self, widget=None, **kwargs):
        from .file_operations import FileDestination, FileOperationRequest

        cut = self.pending_file_cut()
        destination = self.file_provider
        from commonUtils.runtime.resources.provider import capabilities
        access = capabilities(destination)
        if cut is None or self.cloud_busy or not (access.rename and access.create and access.delete):
            return
        source, entries, (client, generation) = cut
        folder = self.file_path
        plaintext = source.private and not destination.private
        if plaintext and not await self.main_window.dialog(toga.ConfirmDialog(
                'Move to unencrypted storage?', 'The destination will contain decrypted files. Continue?')):
            return
        if (self.pending_file_cut() is not cut or self.file_provider is not destination or self.file_path != folder
                or self.cloud_busy):
            return
        reopened = None
        if getattr(source, 'closed', False):
            try:
                source = reopened = source.reopen()
            except (OSError, ValueError):
                self.file_status.value = 'The source is no longer open. Select its items again.'
                return
        captured = FileDestination(self.private_root, client, destination, generation)
        requests = [FileOperationRequest('move', source, path, '/'.join(filter(None, (folder, Path(path).name))),
                                        captured, plaintext_approved=plaintext, expected_revision=revision)
                    for path, revision in entries.items()
                    if not any(parent.as_posix() in entries for parent in Path(path).parents)]

        def completed(request):
            for path in tuple(entries):
                if path == request.path or Path(request.path) in Path(path).parents:
                    del entries[path]
            if not entries:
                self._file_cut = None

        cancel = toga.Button('Cancel move', on_press=self.cancel_cloud, style=Pack(height=48))
        self.file_browser.location_bar.add(cancel)
        try:
            result = await self.file_operations().run_selection(requests, completed, verb='Moving')
        finally:
            self.file_browser.location_bar.remove(cancel)
            if reopened is not None:
                reopened.close()
        if result is not None:
            failures, notice, cancelled = result
            await self.browse_files()
            self.file_status.value = ('Move stopped. Inspect both locations.' if cancelled else
                                      '\n'.join(failures) if failures else notice or 'Move finished.')

    def can_copy_file(self, provider=None):
        from services.documents.storage import document_writable
        provider = self.file_provider if provider is None else provider
        return provider is not None and document_writable(provider)

    def show_file_details(self, widget=None, **kwargs):
        self.file_browser.show_details_panel(self.files_view)

    async def parent_file_folder(self, widget=None, **kwargs):
        if self.file_browser.on_check_entry is not None:
            self.end_file_selection()
            return True
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
        from services.documents.mobile_locations import enabled
        if (not enabled(self.private_root) and label == 'Shared files'
                and (path == local_name or path.startswith(local_name + '/'))):
            location = ('Local files', path.removeprefix(local_name).lstrip('/'))
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

        self.refresh_file_source_tabs()

    def files_back(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_cloud()

    def local_browser_root(self):
        return 'Shared files' if 'Shared files' in self.ordinary_file_roots() else 'Local files'

    def ordinary_file_roots(self, *, include_collections=True):
        from .local_sources import device_files
        from .incoming_files import inbox_path
        from services.documents.locations import MobileLocalFiles
        from services.documents.mobile_locations import enabled
        roots = {'Local files': None, 'Shared files': device_files(self.private_root, include_collections=include_collections)}
        if not enabled(self.private_root):
            roots['Received Files'] = MobileLocalFiles(inbox_path(self.private_root))
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

    async def browse_files(self, widget=None, *, preserve_listing=False, **kwargs):
        previous = getattr(self, '_local_browse_cancel', None)
        if previous is not None:
            previous.set()
        if not self.active_host:
            return False
        if self.cloud_busy:
            if self.can_browse_local(self.file_storage.value):
                return await self.browse_local_during_transfer(self.file_location.value, preserve_listing=preserve_listing)
            return False
        # Listing is a cancellable read, not a mutation. Keep cloud controls and
        # download discovery out of the navigation path, including idle browsing.
        return await self.browse_local_during_transfer(self.file_location.value, preserve_listing=preserve_listing)

    def _update_file_actions_visibility(self):
        available = bool(self.file_actions.actions) and self.file_browser.on_check_entry is None
        self.file_actions_button.style.update(display='pack' if available else 'none',
                                              visibility='visible' if available else 'hidden')

    def populate_file_browser(self, rows, password='', *, location=None):
        from .browser_preview import LocalThumbnails, dark_notebook_thumbnails
        client = self.cloud_client
        provider = self.file_provider
        source = LocalThumbnails(provider, client, password, dark_notebooks=dark_notebook_thumbnails(self.app))
        self.file_browser.configure_previews(source)
        self.file_browser.details = source.details
        self.file_actions.raw_actions = self.current_folder_commands()
        self.file_actions.refresh()
        self._update_file_actions_visibility()
        if location is None:
            self.file_browser.history.clear()
        self.file_browser.set_entries(self.file_provider, self.file_path, rows, location=location)
        label = self.file_storage.value
        managed_root = label == 'Local files' and self.local_browser_root() == 'Shared files'
        name = ('Local' if managed_root else 'On this device'
                if label in ('Local files', 'Shared files') else label)
        from services.documents.mobile_locations import COPIES, enabled
        from .local_sources import device_files_label
        root_title = ''
        if enabled(self.private_root):
            if label == 'Shared files':
                root_title = device_files_label(self.app)
            elif label == 'Local files':
                root_title = COPIES
        self.file_browser.location_bar.update_provider(self.file_path,
            self.file_provider, name=Path(self.file_path).name if self.file_path else root_title or name)
        from .folder_navigation import record
        record(getattr(self, 'app', self), self.files_view, self.file_browser, 'browser', label,
               self.file_path, self.browser_file_location, root_title=root_title)
        from .browser_ui import sync_browser_population
        sync_browser_population(self.app)

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

    async def duplicate_file(self, provider, row):
        from .file_operations import FileOperationRequest
        request = FileOperationRequest('copy', provider, row['path'], expected_revision=row.get('revision'))
        awake = self.app.acquire_awake_lease()
        try:
            if await self.file_operations().run(lambda: request):
                message = self.file_status.value
                if await self.browse_files():
                    self.file_status.value = message
        finally:
            awake.close()

    async def delete_file(self, widget=None, **kwargs):
        from .file_operations import FileOperationRequest
        if self.cloud_busy:
            return
        try:
            provider, path = self.selected_file()
            revision = provider.entry(path)['revision']
        except (OSError, ValueError) as error:
            self.file_status.value = str(error)
            return
        request = FileOperationRequest('delete', provider, path, expected_revision=revision)
        from services.documents.storage import display_path
        if not await self.main_window.dialog(toga.ConfirmDialog(
                f'Delete {Path(path).name}?',
                f'{display_path(provider, path)}\n\nThis permanently deletes the selected item and its contents.')):
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
            from commonUtils import archives
            from .archive_operations import ArchiveItem, ordinary
            if (self.feature_enabled('archives') and ordinary(provider)
                    and path.lower().endswith(archives.TAR_SUFFIXES)):
                from .archive_ui import controller
                return await controller(self.app).open(ArchiveItem(provider, path))
            from services.documents.mobile_storage import open_provider_document
            self.crypt_password.value = self.file_password.value
            if self.file_browser.search_open and self.file_browser.search.value.strip():
                from .obsidian import open_search_note
                return await open_search_note(self.app, provider, path,
                    regular=lambda: open_provider_document(self.app, provider, path))
            return await open_provider_document(self.app, provider, path)
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
        self.file_status.value = 'Choose a local folder or encrypted copy for this downloaded file.'

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
