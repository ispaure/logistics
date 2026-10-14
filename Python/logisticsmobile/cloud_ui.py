"""Native remote-file browser and private downloads; no remote mutations."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .cloud import CloudClient, Downloads, download_name
from .localcrypt_ui import LocalCryptUI


class CloudUI(LocalCryptUI):
    def show_cloud(self, widget=None, *, present=True, **kwargs):
        if not hasattr(self, 'cloud_view'):
            self.cloud_busy = False
            self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_crypt_remotes = set()
            self.downloads = Downloads(self.private_root / 'Downloads')
            self.cloud_client = getattr(self, 'cloud_client', None)
            error = ''
            if self.cloud_client is None:
                try:
                    from .credential_vault import ProtectedVault
                    self.cloud_client = CloudClient(vault=ProtectedVault.for_app(self))
                except Exception:
                    error = 'The native remote engine or device credential protection is unavailable.'
            self.cloud_password = toga.PasswordInput(placeholder='Credential ZIP password', style=Pack(height=44))
            self.cloud_import = toga.Button('Import credential ZIP…', on_press=self.import_cloud_package, style=Pack(height=44))
            self.cloud_probe = toga.Button('Check rclone engine', on_press=self.probe_cloud, style=Pack(height=44))
            self.cloud_remember = toga.Switch('Save credentials on this device', value=True, style=Pack(height=44))
            self.cloud_package = toga.Label('Credential package: none', style=Pack(font_size=14))
            self.cloud_reload = toga.Button('Reload saved credentials', on_press=self.restore_cloud, style=Pack(height=44))
            self.cloud_remote = toga.Selection(on_change=self.cloud_remote_changed, style=Pack(height=44))
            self.cloud_location = toga.TextInput(placeholder='Folder within remote', style=Pack(height=44))
            self.cloud_browse = toga.Button('Browse folder', on_press=self.browse_cloud, style=Pack(flex=1, height=44))
            self.cloud_up = toga.Button('Parent folder', on_press=self.parent_cloud, style=Pack(flex=1, height=44))
            self.cloud_entries = toga.Selection(style=Pack(height=44))
            from commonUtils.ui.native_browser import NativeBrowser
            self.remote_browser = NativeBrowser(selected=self.browser_cloud_selected, open_folder=self.browser_cloud_folder, navigate=self.browser_cloud_location)
            self.cloud_open = toga.Button('Open selected folder', on_press=self.open_cloud_folder, style=Pack(height=44))
            self.cloud_download = toga.Button('Download private copy', on_press=self.download_cloud, style=Pack(height=44))
            self.cloud_cancel = toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44))
            self.cloud_clear = toga.Button('Forget saved credentials', on_press=self.clear_cloud, style=Pack(height=44))
            self.cloud_status = toga.MultilineTextInput(value=error or 'Choose saved or session-only credentials, then import a ZIP. Its password is never saved.',
                                                       readonly=True, style=Pack(height=72))
            self.download_selector = toga.Selection(style=Pack(height=44))
            self.download_open = toga.Button('Open private copy', on_press=self.open_download, style=Pack(flex=1, height=44))
            self.download_export = toga.Button('Export private copy…', on_press=self.export_download, style=Pack(flex=1, height=44))
            self.cloud_view = toga.ScrollContainer(content=toga.Box(children=[
                toga.Button('Locations', on_press=self.show_locations, style=Pack(height=44)),
                toga.Label('Remote files', style=Pack(font_size=22)), self.cloud_remember, toga.Label('Off: use credentials only for this app session.'), self.cloud_password, self.cloud_import,
                 self.cloud_probe, self.cloud_reload, self.cloud_package, self.cloud_remote, self.cloud_location,
                toga.Box(children=[self.cloud_browse, self.cloud_up], style=Pack(direction=ROW)),
                self.remote_browser.widget, self.cloud_open, self.cloud_download, *self.build_localcrypt(), self.cloud_cancel, self.cloud_clear,
                self.cloud_status, toga.Label('Private downloads'), self.download_selector,
                toga.Box(children=[self.download_open, self.download_export], style=Pack(direction=ROW))],
                style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            self.refresh_downloads()
            self.set_cloud_busy(False)
            if self.cloud_client is not None and getattr(self.cloud_client, 'vault', None) is not None:
                self.set_cloud_busy(True)
                self.cloud_restore_task = self.loop.create_task(self.restore_cloud(initial=True))
        if present:
            self.show_view(self.cloud_view, destination='files')

    def set_cloud_busy(self, value):
        self.cloud_busy = value
        for item in (self.cloud_password, self.cloud_import, self.cloud_probe, self.cloud_remote,
                     self.cloud_location, self.cloud_browse, self.cloud_up, self.cloud_entries,
                     self.cloud_open, self.cloud_download, self.cloud_clear, self.cloud_reload, self.cloud_remember,
                     self.crypt_download, self.crypt_open, self.crypt_refresh, self.crypt_selector, self.crypt_password):
            item.enabled = not value and self.cloud_client is not None
        self.cloud_download.enabled = not value and self.cloud_client is not None and self.cloud_remote.value not in self.cloud_crypt_remotes
        self.crypt_download.enabled = not value and self.cloud_client is not None and self.cloud_remote.value in self.cloud_crypt_remotes
        self.cloud_cancel.enabled = value
        self.download_open.enabled = self.download_export.enabled = not value and bool(self.download_labels)

    def cloud_remote_changed(self, widget=None, **kwargs):
        if hasattr(self, 'download_labels'):
            self.set_cloud_busy(self.cloud_busy)

    async def _load_crypt_remote_names(self):
        # Alternate client adapters may expose ordinary downloads only.
        kinds = getattr(self.cloud_client, 'crypt_remotes', lambda: ())
        self.cloud_crypt_remotes = set(await asyncio.to_thread(kinds))

    async def restore_cloud(self, widget=None, *, initial=False, **kwargs):
        if (self.cloud_busy and not initial) or self.cloud_client is None:
            return
        if not self.clear_private_reader():
            return
        self.set_cloud_busy(True)
        try:
            self.clear_private_catalog()
            names = await asyncio.to_thread(self.cloud_client.restore)
            await self._load_crypt_remote_names()
            self.cloud_remote.items = names
            self.cloud_entries.items = []
            self.cloud_rows = {}
            self.cloud_open_remote = None
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_package.text = 'Credential package: ' + (self.cloud_client.package_name or 'none')
            self.cloud_status.value = (f'{len(names)} saved remote(s) restored. Choose a remote, then browse.'
                                       if names else 'No saved credential package. Import a ZIP to get started.')
        except Exception:
            self.cloud_status.value = 'Saved credentials are unavailable. Unlock the device and reload, or forget saved credentials to import again.'
        finally:
            self.set_cloud_busy(False)

    async def probe_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            version = await asyncio.to_thread(self.cloud_client.request, 'probe')
            self.cloud_status.value = f'Embedded rclone {version}; offline read check passed.'
        except Exception:
            self.cloud_status.value = 'The embedded rclone engine could not complete its read check.'
        finally:
            self.set_cloud_busy(False)

    async def import_cloud_package(self, widget=None, **kwargs):
        from .pickers import pick_document
        if self.cloud_busy or self.cloud_client is None:
            return
        password = self.cloud_password.value
        self.cloud_password.value = ''
        self.set_cloud_busy(True)
        try:
            selected = await pick_document(self)
            if selected is None:
                self.cloud_status.value = 'Import cancelled.'
                return
            if not self.clear_private_reader():
                return
            self.clear_private_catalog()
            names = await asyncio.to_thread(self.cloud_client.import_package, *selected, password, remember=self.cloud_remember.value)
            await self._load_crypt_remote_names()
            self.cloud_remote.items = names
            self.cloud_package.text = 'Logistics credential package: ' + getattr(self.cloud_client, 'package_name', 'Imported ZIP')
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_status.value = f'{len(names)} {'saved' if self.cloud_remember.value else 'session'} remote(s) loaded. Choose a remote, then browse. No connection has been made yet.'
        except Exception as error:
            self.cloud_status.value = 'Import failed: ' + str(error)[:300]
        finally:
            password = None
            self.set_cloud_busy(False)

    async def browse_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None or not self.cloud_remote.value:
            return
        remote, folder = self.cloud_remote.value, self.cloud_location.value.strip('/')
        previous_rows = self.cloud_rows
        previous_selected = self.cloud_entries.value
        self.set_cloud_busy(True)
        self.cloud_rows = {}
        self.cloud_entries.items = []
        try:
            rows = await asyncio.to_thread(self.cloud_client.entries, remote, folder)
            self.cloud_rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                               for index, row in enumerate(rows)}
            self.cloud_entries.items = list(self.cloud_rows)
            self.cloud_open_remote, self.cloud_path = remote, folder
            from pathlib import Path
            from types import SimpleNamespace
            import base64
            from commonUtils.runtime.resource_provider import resource_path
            root = Path('/remote') / remote
            provider = SimpleNamespace(root=root, relative=lambda path: resource_path(str(Path(path).relative_to(root)) if Path(path).is_absolute() else path))
            generation = getattr(self.cloud_client, 'generation', 0)
            def list_children(path, *, cancelled):
                if cancelled() or getattr(self.cloud_client, 'generation', 0) != generation:
                    raise ValueError('Search cancelled or credentials changed.')
                values = self.cloud_client.entries(remote, path)
                if cancelled() or getattr(self.cloud_client, 'generation', 0) != generation:
                    raise ValueError('Search cancelled or credentials changed.')
                return [dict(row, name=Path(row['path']).name, modified='') for row in values]
            provider.list = list_children
            password = self.crypt_password.value
            client = self.cloud_client
            def thumbnail(row, size, cancelled):
                if cancelled() or not getattr(client, 'supports_streaming', False):
                    return b''
                if Path(row['path']).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.zip', '.cbz', '.epub'}:
                    return b''
                result = client.request('remote_thumbnail', remote=remote, path=row['path'], password=password, width=size[0], height=size[1])
                return base64.b64decode(result['data'], validate=True) if not cancelled() else b''
            self.remote_browser.closed = False
            self.remote_browser.thumbnail = thumbnail
            self.remote_browser.set_entries(provider, folder, [dict(row, name=Path(row['path']).name, modified='') for row in rows], location=(remote, folder))
            self.cloud_status.value = f'{len(rows)} entry/entries. Remote files are read-only.'
            return True
        except Exception as error:
            self.cloud_status.value = 'Browse failed: ' + str(error)[:300]
            if self.remote_browser.tree is not None:
                self.cloud_remote.value, self.cloud_location.value = self.cloud_open_remote, self.cloud_path
                self.cloud_rows = previous_rows
                self.cloud_entries.items = list(previous_rows)
                if previous_selected is not None:
                    self.cloud_entries.value = previous_selected
            return False
        finally:
            self.set_cloud_busy(False)

    async def parent_cloud(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.cloud_location.value = self.cloud_path.rpartition('/')[0]
            await self.browse_cloud()

    def browser_cloud_selected(self, row):
        if row is None:
            self.cloud_entries.items = ['Select an item…', *self.cloud_rows]
            picker = getattr(self.cloud_entries._impl, 'native_picker', None)
            if picker is not None:
                picker.reloadAllComponents()
            self.cloud_entries.value = 'Select an item…'
            return
        label = next((label for label, value in self.cloud_rows.items() if value['path'] == row['path']), None)
        if label is None:
            label = 'Search: ' + row['path']
            self.cloud_rows[label] = row
            self.browser_cloud_selected(None)
        self.cloud_entries.value = label

    async def browser_cloud_folder(self, row):
        if self.cloud_busy:
            return False
        return await self.browser_cloud_location((self.cloud_open_remote, row['path']))

    async def browser_cloud_location(self, location):
        if self.cloud_busy:
            return False
        self.cloud_remote.value, self.cloud_location.value = location
        return await self.browse_cloud()

    async def open_cloud_folder(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if not self.cloud_busy and row and row['directory'] and self.cloud_remote.value == self.cloud_open_remote:
            self.cloud_location.value = row['path']
            await self.browse_cloud()

    async def download_cloud(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if self.cloud_busy or not row or row['directory'] or self.cloud_remote.value != self.cloud_open_remote:
            return
        self.set_cloud_busy(True)
        try:
            name = download_name(row['path'])
            target = await asyncio.to_thread(self.downloads.fetch, self.cloud_client,
                                            self.cloud_open_remote, row['path'])
            self.refresh_downloads(target)
            self.cloud_status.value = f'Downloaded {name}. The remote original was preserved.'
        except Exception as error:
            self.cloud_status.value = 'Download failed: ' + str(error)[:300]
        finally:
            self.set_cloud_busy(False)

    def cancel_cloud(self, widget=None, **kwargs):
        if getattr(self, '_crypt_cancel', None) is not None:
            self._crypt_cancel.set()
        if self.cloud_client:
            self.cloud_client.cancel()
            self.cloud_status.value = 'Cancelling the remote request…'

    async def clear_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            if not self.clear_private_reader():
                return
            self.clear_private_catalog()
            await asyncio.to_thread(self.cloud_client.clear)
            self.cloud_crypt_remotes = set()
            self.cloud_remote.items = self.cloud_entries.items = []
            self.cloud_rows = {}
            self.cloud_open_remote = None
            self.cloud_password.value = ''
            self.cloud_package.text = 'Credential package: none'
            self.cloud_status.value = 'Saved and session credentials forgotten. Private downloads remain available.'
        except Exception:
            self.cloud_status.value = 'Could not forget the protected credentials. Unlock the device and retry.'
        finally:
            self.set_cloud_busy(False)

    def refresh_downloads(self, selected=None):
        self.download_labels = {f'{i + 1}. {path.name}': path for i, path in enumerate(self.downloads.items())}
        self.download_selector.items = list(self.download_labels)
        if selected:
            self.download_selector.value = next(key for key, path in self.download_labels.items() if path == selected)

    async def open_download(self, widget=None, *, path=None, **kwargs):
        from .access import LocalDocuments
        selected = path if path is not None else self.download_labels.get(self.download_selector.value)
        if self.cloud_busy or selected is None:
            return
        self.set_cloud_busy(True)
        try:
            if selected.suffix.lower() in {'.epub', '.cbz', '.zip'}:
                self.show_library()
                record = await asyncio.to_thread(self.library_store.import_book, LocalDocuments(), selected)
                self.refresh_library()
                await self.open_book(record['id'])
            else:
                doc = await asyncio.to_thread(self.store.import_document, LocalDocuments(), selected)
                self.refresh_documents()
                self.open_document(doc.id)
                self.show_documents()
        except Exception as error:
            self.cloud_status.value = 'Open failed: ' + str(error)[:300]
            self.show_cloud()
        finally:
            self.set_cloud_busy(False)

    async def export_download(self, widget=None, **kwargs):
        from .pickers import export_file
        selected = self.download_labels.get(self.download_selector.value)
        if self.cloud_busy or selected is None:
            return
        self.set_cloud_busy(True)
        try:
            done = await export_file(self, selected)
            self.cloud_status.value = 'Private copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            self.cloud_status.value = 'Export failed: ' + str(error)[:300]
        finally:
            self.set_cloud_busy(False)
