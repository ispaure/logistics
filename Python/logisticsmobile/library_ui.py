"""Mobile Books and Comics catalogue; readers own their own presentation."""
from features.rclone.mobile.storage_location import collection_path, CollectionFiles
import asyncio
import sqlite3
import json
from types import SimpleNamespace
from configparser import ConfigParser, Error as ConfigError
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .appearance import list_button
from .appearance import template_icon
from .hub_icons import icon
from .files_ui import local_read_available
from commonUtils.runtime.local_files import LocalFiles
from .appearance import action_button
from features.comics.library_config import library_names


def discover_libraries(root, jobs, client=None, crypt_remotes=()):
    """Inspect collection-root INIs, without recursively scanning book files."""
    from features.rclone.localcrypt.mobile.resources import encrypted_library_sources
    from .folder_hub import exclusions, visible_remotes
    from services.folders.policy import visible_name
    root = Path(root)
    sources, records, failures, seen = [], [], 0, set()
    try:
        local = collection_path(root)
    except (OSError, ValueError):
        return [], 1
    rules = exclusions()
    if local.is_dir() and not local.is_symlink():
        provider = CollectionFiles(root)
        sources.append((provider, '', 'Local'))
        for child in sorted(local.iterdir(), key=lambda path: path.name.casefold()):
            if child.is_dir() and not child.is_symlink() and visible_name(child.name, rules):
                sources.append((provider, child.name, 'Local'))
        for job in jobs:
            if not job['crypt'] and visible_name(job['remote'], rules, remote=True):
                sources.append((provider, job['target'], 'Local'))
    private_sources, private_failures = encrypted_library_sources(root, jobs, client, visible_remotes(crypt_remotes))
    sources.extend(private_sources)
    failures += private_failures
    # A local copy can itself be a collection, or hold collection folders.
    for provider, folder, source in list(sources):
        if provider.private:
            try:
                sources.extend((provider, row['path'], source) for row in provider.list(folder)
                               if row['directory'] and visible_name(row['name'], rules))
            except (OSError, ValueError):
                failures += 1
    for provider, folder, source in sources:
        identity = str(provider.root), folder
        if identity in seen:
            continue
        seen.add(identity)
        try:
            path = '/'.join(part for part in (folder, 'remoteConfig.ini') if part)
            with provider.open(path) as stream:
                data = stream.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError('Library configuration is too large.')
            config = ConfigParser(interpolation=None)
            config.read_string(data.decode('utf-8-sig'))
            names = library_names(config)
            if names is None:
                legacy = (config.has_option('ComicRack', 'appdata_local_cyo_sub_path')
                          and config.has_option('ComicRack', 'appdata_roaming_cyo_sub_path'))
                if not legacy and not config.has_option('YACReaderLibrary', 'yacreaderlibrary_ini_sub_path'):
                    continue
                names = ['']
            for name in names:
                path = '/'.join(part for part in (folder, name) if part)
                try:
                    available = provider.entry(path)['directory']
                except FileNotFoundError:
                    continue
                if available:
                    records.append(dict(name=name or Path(folder).name or 'Comics',
                        folder=path, source=source, provider=provider))
        except FileNotFoundError:
            continue
        except (OSError, ValueError, UnicodeError, ConfigError):
            failures += 1
    return records, failures


class LibraryCatalog:
    def clear_private_libraries(self):
        self.library_scan_epoch = getattr(self, 'library_scan_epoch', 0) + 1
        self.library_records = [record for record in getattr(self, 'library_records', ())
                                if not record['provider'].private]
        self.filter_library()

    def build_library_catalog(self):
        self.library_index_status = toga.Label('Metadata search · preparing index', style=Pack(font_size=12))
        self.library_rows = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.library_folder_list = self.app.presentation.summary_list(kind='Library folder',
            icon_kind='files', on_select=self._select_library_row, style=Pack(flex=1))
        self.library_empty = toga.Box(children=[
            toga.Label('No configured library folders.', style=Pack(font_size=18, margin_top=16, margin_bottom=8)),
            toga.Label('Import an EPUB or comic, or browse\na folder in Local or LocalCrypt.', style=Pack(font_size=13, margin_bottom=12)),
            action_button(toga.Button('Import a book or comic…', on_press=self.import_book, style=Pack(height=48))),
            toga.Button('Open Workspaces', on_press=self.app.show_locations, style=Pack(height=48))],
            style=Pack(direction=COLUMN))
        self.library_records = []
        self.imported_records = []
        self.imported_selected = set()
        self.library_row_buttons = []
        self.library_view = toga.Box(children=[
            toga.Box(children=[toga.Button('Refresh', on_press=self.refresh_library, style=Pack(height=48, flex=1)), self.book_import],
                     style=Pack(direction=ROW, margin_bottom=8)),
            self.library_rows,
            self.book_status], style=Pack(direction=COLUMN, margin=12, flex=1))
        self.book_import.text = 'Import…'
        self.book_import.style.flex = 1
        self.book_import.style.height = 48
        self.book_status.style.font_size = 12


    def filter_library(self, widget=None, **kwargs):
        if not hasattr(self, 'library_rows'):
            return
        self.library_row_buttons = []
        rows = []
        for record in self.library_records:
            if not self.app.library_folder_visible(record):
                continue
            async def open_item(widget=None, library=record, **kw):
                if (self.active_host and not self.book_busy
                        and any(item is library for item in self.library_records)):
                    app = self.app
                    provider = library['provider']
                    if provider.private and (app.cloud_client is not library['client']
                            or app.cloud_client.generation != library['generation']):
                        await self.refresh_library_folders()
                        return
                    app.show_cloud(present=False)
                    if not local_read_available(app, private=provider.private):
                        return
                    await app.show_files(local_root=not provider.private)
                    if provider.private and (app.cloud_client is not library['client']
                            or app.cloud_client.generation != library['generation']):
                        return
                    label = library['source'] if provider.private else 'Local files'
                    app.file_roots[label] = provider
                    app.update_file_locations()
                    await app.browser_file_location((label, library['folder']))
            # Compatibility actions are lightweight models, not native controls.
            self.library_row_buttons.append(SimpleNamespace(text=record['name'], on_press=open_item,
                                                            enabled=not self.book_busy))
            rows.append(dict(title=record['name'], subtitle=record['source'],
                icon=self.library_folder_list.row_icon, folder=True, thumbnail=False,
                entry=record, callback=open_item, index=len(rows)))
        listing = self.library_folder_list
        listing.updating = True
        try:
            listing.data = rows
            listing.enabled = not self.book_busy
        finally:
            listing.updating = False
        view = listing if rows else self.library_empty
        if list(self.library_rows.children) != [view]:
            for child in list(self.library_rows.children):
                self.library_rows.remove(child)
            self.library_rows.add(view)

    def _select_library_row(self, widget, **kwargs):
        if widget.updating or self.book_busy:
            return
        row = widget.selection
        if row is not None and any(record is row.entry for record in self.library_records):
            self.loop.create_task(row.callback())

    async def refresh_library_folders(self, widget=None, **kwargs):
        """Serialize discovery and briefly reuse the same credential/config snapshot."""
        app = self.app
        while True:
            task = getattr(self, '_library_discovery', None)
            if task is not None and not task.done():
                await asyncio.shield(task)
                if not self.active_host:
                    return
                continue
            client = getattr(app, 'cloud_client', None)
            signature = (id(client), getattr(client, 'generation', None),
                         json.dumps(list(app.mirror_store().jobs.values()), sort_keys=True),
                         tuple(sorted(getattr(app, 'cloud_crypt_remotes', ()))),
                         getattr(self, '_library_discovery_revision', 0))
            cached = getattr(self, '_library_discovery_cached', None)
            if widget is None and cached is not None and cached[0] == signature and self.loop.time() - cached[1] < 2:
                return
            self._library_discovery = task = self.loop.create_task(self._discover_library_folders())
            await asyncio.shield(task)
            if (self.active_host and client is getattr(app, 'cloud_client', None)
                    and signature[1] == getattr(client, 'generation', None)):
                self._library_discovery_cached = signature, self.loop.time()
            return

    async def _discover_library_folders(self):
        app = self.app
        epoch = self.library_scan_epoch = getattr(self, 'library_scan_epoch', 0) + 1
        client = getattr(app, 'cloud_client', None)
        generation = getattr(client, 'generation', None)
        jobs = [dict(job) for job in app.mirror_store().jobs.values()]
        remotes = tuple(getattr(app, 'cloud_crypt_remotes', ()))
        self.book_status.text = 'Finding configured libraries…'
        try:
            records, failures = await asyncio.to_thread(discover_libraries, self.private_root, jobs, client, remotes)
        except (OSError, ValueError):
            records, failures = [], 1
        if not self.active_host or epoch != self.library_scan_epoch:
            return
        if client is not getattr(app, 'cloud_client', None) or generation != getattr(client, 'generation', None):
            records = [record for record in records if not record['provider'].private]
        for record in records:
            record.update(client=client, generation=generation)
        self.library_records = records
        self.filter_library()
        self.book_status.text = (f'{failures} library configuration(s) could not be read.' if failures
                                 else f'{len(records)} configured library folder(s).')


    def refresh_library(self, widget=None, **kwargs):
        if widget is not None:
            self._library_discovery_revision = getattr(self, '_library_discovery_revision', 0) + 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._publish_library_inventory(*self.library_store.items())
            return
        self._publish_library_inventory(*self.library_store.cached_items())
        self._library_refresh_again = True
        task = getattr(self, '_library_inventory_task', None)
        if task is None or task.done():
            async def refresh():
                while self.active_host and self._library_refresh_again:
                    self._library_refresh_again = False
                    records, failures = await asyncio.to_thread(self.library_store.items)
                    if self.active_host and not self._library_refresh_again:
                        self._publish_library_inventory(records, failures)
            self._library_inventory_task = self.loop.create_task(refresh())

    def _publish_library_inventory(self, records, failures):
        previous = self.book_loading
        self.book_loading = True
        self.imported_records = records
        if hasattr(self, 'library_rows'):
            self.refresh_imported_metadata(records)
        labels = {}
        for record in records:
            label = record['name']
            while label in labels:
                label += ' (copy)'
            labels[label] = record['id']
        if hasattr(self, 'library_rows'):
            self.library_scan_task = self.loop.create_task(self.refresh_library_folders())
        self.book_labels = labels
        self.book_selector.items = list(labels)
        if self.book_record:
            self.book_selector.value = next((label for label, key in labels.items()
                                            if key == self.book_record['id']), None)
        if failures:
            self.book_status.text = f'{len(failures)} library record(s) could not be read; they were preserved.'
        self.book_loading = previous

    async def wait_for_refresh(self):
        """Wait for inventories and the metadata work they schedule, not an old scan."""
        while True:
            inventory = getattr(self, '_library_inventory_task', None)
            if inventory is not None:
                await asyncio.shield(inventory)
            discovery = getattr(self, 'library_scan_task', None)
            metadata = getattr(self, 'metadata_task', None)
            for task in (discovery, metadata):
                if task is not None:
                    await asyncio.shield(task)
            if (inventory is getattr(self, '_library_inventory_task', None)
                    and discovery is getattr(self, 'library_scan_task', None)
                    and metadata is getattr(self, 'metadata_task', None)):
                return


    async def edit_imported_comics(self, widget=None, **kwargs):
        if self.book_busy:
            return
        selected = [record for record in self.imported_records if record['id'] in self.imported_selected]
        if not selected:
            self.book_status.text = 'Select comics before opening batch metadata.'
            return
        if len(selected) > 200:
            self.book_status.text = 'Select at most 200 comics per batch.'
            return
        self.set_book_busy(True)
        try:
            documents = []
            for record in selected:
                _, reader = await asyncio.to_thread(self.library_store.open, record['id'])
                documents.append(reader.document)
        except Exception as error:
            self.book_status.text = 'Cannot edit selection: ' + str(error)[:300]
            return
        finally:
            self.set_book_busy(False)
        from features.comics.mobile.metadata import batch_form
        import threading
        cancel = threading.Event()
        async def save(changes):
            if self.book_busy:
                return 'Wait for the current batch.'
            if not changes:
                return 'No fields selected.'
            self.set_book_busy(True)
            cancel.clear()
            try:
                completed, failures = await asyncio.to_thread(self.library_store.edit_comics,
                    selected, changes, cancelled=cancel.is_set)
                replacements = {record['id']: record for record in completed}
                selected[:] = [replacements.get(record['id'], record) for record in selected]
                self.refresh_library()
                return (f'{len(completed)} saved; {len(failures)} failed; '
                        f'{len(selected) - len(completed) - len(failures)} unprocessed. '
                        + ' '.join(message for _, message in failures)[:500])
            finally:
                self.set_book_busy(False)
        from features.comics.mobile.collection import suggestions
        choices = self.metadata_index.suggestions() if getattr(self, 'metadata_ready', False) else suggestions(())
        view = batch_form(documents, save=save, back=self.show_library, cancel=lambda widget, **kw: cancel.set(), choices=choices,
            width=max(1, min(640, min(self.main_window.size) - 24)))
        self.show_view(view, reader_route='metadata-batch', title='Edit comic metadata')


    def refresh_imported_metadata(self, records):
        epoch = self.metadata_epoch = getattr(self, 'metadata_epoch', 0) + 1
        records = [dict(record) for record in records]
        self.imported_selected.intersection_update(record['id'] for record in records)
        self.metadata_ready = False
        self.filter_library()
        from features.comics.mobile.index import CollectionIndex
        if not hasattr(self, 'metadata_index'):
            self.metadata_index = CollectionIndex(self.library_store.root / '.metadata.sqlite3')
        def current():
            return self.metadata_epoch == epoch and self.active_host and not self.loop.is_closed()
        def signature(record):
            path = self.library_store.path(record['id'], '.epub' if record['kind'] == 'epub' else '.cbz')
            info = path.stat()
            return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns
        def load(record):
            from features.comics.mobile.collection import metadata_fields
            path = self.library_store.path(record['id'], '.epub' if record['kind'] == 'epub' else '.cbz')
            # Never consult passwords or index protected metadata, even when an
            # inner ZIP has a remembered/configured password elsewhere.
            if self.library_store.validate_archive(path, record['kind']):
                return None
            _, reader = self.library_store.open(record['id'])
            return metadata_fields(record['kind'], reader)
        def report(done, total, failures):
            def update():
                if current():
                    first = not self.metadata_ready
                    self.metadata_ready = True
                    self.library_index_status.text = f'Metadata checked: {done}/{total} imports.\n{failures} unreadable; protected metadata excluded.'
                    if first or done == total:
                        self.filter_library()
            if not self.loop.is_closed():
                self.loop.call_soon_threadsafe(update)
        async def scan():
            try:
                await asyncio.to_thread(self.metadata_index.scan, records, signature=signature,
                    load=load, cancelled=lambda: not current(), progress=report)
            except (OSError, ValueError, sqlite3.Error):
                if current():
                    self.library_index_status.text = 'Metadata index unavailable; filename search remains available.'
                    self.metadata_ready = False
                    self.filter_library()
            if current():
                self.filter_library()
        self.metadata_task = self.loop.create_task(scan())
