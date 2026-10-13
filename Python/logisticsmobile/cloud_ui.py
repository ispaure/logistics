"""Native remote-file browser and private downloads; no remote mutations."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .cloud import CloudClient, Downloads, download_name


class CloudUI:
    def show_cloud(self, widget=None, **kwargs):
        if not hasattr(self, 'cloud_view'):
            self.cloud_busy = False
            self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.downloads = Downloads(self.private_root / 'Downloads')
            self.cloud_client = getattr(self, 'cloud_client', None)
            error = ''
            if self.cloud_client is None:
                try:
                    self.cloud_client = CloudClient()
                except (ValueError, OSError, AttributeError):
                    error = 'Remote connections require the native mobile build.'
            self.cloud_password = toga.PasswordInput(placeholder='Credential ZIP password', style=Pack(height=44))
            self.cloud_import = toga.Button('Import credential ZIP…', on_press=self.import_cloud_package, style=Pack(height=44))
            self.cloud_probe = toga.Button('Check rclone engine', on_press=self.probe_cloud, style=Pack(height=44))
            self.cloud_remote = toga.Selection(style=Pack(height=44))
            self.cloud_location = toga.TextInput(placeholder='Folder within remote', style=Pack(height=44))
            self.cloud_browse = toga.Button('Browse folder', on_press=self.browse_cloud, style=Pack(flex=1, height=44))
            self.cloud_up = toga.Button('Parent folder', on_press=self.parent_cloud, style=Pack(flex=1, height=44))
            self.cloud_entries = toga.Selection(style=Pack(height=44))
            self.cloud_open = toga.Button('Open selected folder', on_press=self.open_cloud_folder, style=Pack(height=44))
            self.cloud_download = toga.Button('Download private copy', on_press=self.download_cloud, style=Pack(height=44))
            self.cloud_cancel = toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44))
            self.cloud_clear = toga.Button('Forget session credentials', on_press=self.clear_cloud, style=Pack(height=44))
            self.cloud_status = toga.MultilineTextInput(value=error or 'Import your TXT-in-ZIP credentials. Passwords and decrypted settings stay in this session.',
                                                       readonly=True, style=Pack(height=72))
            self.download_selector = toga.Selection(style=Pack(height=44))
            self.download_open = toga.Button('Open private copy', on_press=self.open_download, style=Pack(flex=1, height=44))
            self.download_export = toga.Button('Export private copy…', on_press=self.export_download, style=Pack(flex=1, height=44))
            self.cloud_view = toga.ScrollContainer(content=toga.Box(children=[
                toga.Label('Remote files', style=Pack(font_size=22)), self.cloud_password, self.cloud_import,
                self.cloud_probe, self.cloud_remote, self.cloud_location,
                toga.Box(children=[self.cloud_browse, self.cloud_up], style=Pack(direction=ROW)),
                self.cloud_entries, self.cloud_open, self.cloud_download, self.cloud_cancel, self.cloud_clear,
                self.cloud_status, toga.Label('Private downloads'), self.download_selector,
                toga.Box(children=[self.download_open, self.download_export], style=Pack(direction=ROW))],
                style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            self.refresh_downloads()
            self.set_cloud_busy(False)
        self.show_view(self.cloud_view)

    def set_cloud_busy(self, value):
        self.cloud_busy = value
        for item in (self.cloud_password, self.cloud_import, self.cloud_probe, self.cloud_remote,
                     self.cloud_location, self.cloud_browse, self.cloud_up, self.cloud_entries,
                     self.cloud_open, self.cloud_download, self.cloud_clear):
            item.enabled = not value and self.cloud_client is not None
        self.cloud_cancel.enabled = value
        self.download_open.enabled = self.download_export.enabled = not value and bool(self.download_labels)

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
            names = await asyncio.to_thread(self.cloud_client.import_package, *selected, password)
            self.cloud_remote.items = names
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_status.value = f'{len(names)} session remote(s) loaded. Choose a remote, then browse. No connection has been made yet.'
        except Exception as error:
            self.cloud_status.value = 'Import failed: ' + str(error)[:300]
        finally:
            password = None
            self.set_cloud_busy(False)

    async def browse_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None or not self.cloud_remote.value:
            return
        remote, folder = self.cloud_remote.value, self.cloud_location.value.strip('/')
        self.set_cloud_busy(True)
        self.cloud_rows = {}
        self.cloud_entries.items = []
        try:
            rows = await asyncio.to_thread(self.cloud_client.entries, remote, folder)
            self.cloud_rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                               for index, row in enumerate(rows)}
            self.cloud_entries.items = list(self.cloud_rows)
            self.cloud_open_remote, self.cloud_path = remote, folder
            self.cloud_status.value = f'{len(rows)} entry/entries. Remote files are read-only.'
        except Exception as error:
            self.cloud_status.value = 'Browse failed: ' + str(error)[:300]
        finally:
            self.set_cloud_busy(False)

    async def parent_cloud(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.cloud_location.value = self.cloud_path.rpartition('/')[0]
            await self.browse_cloud()

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
        if self.cloud_client:
            self.cloud_client.cancel()
            self.cloud_status.value = 'Cancelling the remote request…'

    async def clear_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            await asyncio.to_thread(self.cloud_client.clear)
            self.cloud_remote.items = self.cloud_entries.items = []
            self.cloud_rows = {}
            self.cloud_open_remote = None
            self.cloud_password.value = ''
            self.cloud_status.value = 'Session credentials forgotten. Private downloads remain available.'
        finally:
            self.set_cloud_busy(False)

    def refresh_downloads(self, selected=None):
        self.download_labels = {f'{i + 1}. {path.name}': path for i, path in enumerate(self.downloads.items())}
        self.download_selector.items = list(self.download_labels)
        if selected:
            self.download_selector.value = next(key for key, path in self.download_labels.items() if path == selected)

    async def open_download(self, widget=None, **kwargs):
        from .access import LocalDocuments
        selected = self.download_labels.get(self.download_selector.value)
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
        from .pickers import export_document
        from .cloud import DOWNLOAD_LIMIT
        selected = self.download_labels.get(self.download_selector.value)
        if self.cloud_busy or selected is None:
            return
        self.set_cloud_busy(True)
        try:
            with selected.open('rb') as stream:
                data = stream.read(DOWNLOAD_LIMIT + 1)
            done = await export_document(self, selected.name, data, max_bytes=DOWNLOAD_LIMIT,
                                         mime_type='application/octet-stream')
            self.cloud_status.value = 'Private copy exported.' if done else 'Export cancelled.'
        except Exception as error:
            self.cloud_status.value = 'Export failed: ' + str(error)[:300]
        finally:
            self.set_cloud_busy(False)
