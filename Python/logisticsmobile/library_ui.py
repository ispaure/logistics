"""Mobile Books and Comics catalogue; readers own their own presentation."""
import asyncio
from configparser import ConfigParser, Error as ConfigError
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from commonUtils.ui.native.presentation import list_button, template_icon
from .hub_icons import icon
from commonUtils.runtime.local_files import LocalFiles
from features.comics.library_config import library_names


def discover_libraries(root, jobs, client=None, crypt_remotes=()):
    """Inspect collection-root INIs, without recursively scanning book files."""
    from .file_resources import CryptFiles
    from .folder_hub import exclusions, visible_remotes
    from services.folder_policy import visible_name
    root = Path(root)
    sources, records, failures, seen = [], [], 0, set()
    local = root / 'LocalFiles'
    rules = exclusions()
    if local.is_dir() and not local.is_symlink():
        provider = LocalFiles(local)
        sources.append((provider, '', 'Local'))
        for child in sorted(local.iterdir(), key=lambda path: path.name.casefold()):
            if child.is_dir() and not child.is_symlink() and visible_name(child.name, rules):
                sources.append((provider, child.name, 'Local'))
        for job in jobs:
            if not job['crypt'] and visible_name(job['remote'], rules, remote=True):
                sources.append((provider, job['target'], 'Local'))
    if client is not None:
        for remote in visible_remotes(crypt_remotes):
            try:
                identity = client.request('crypt_path', remote=remote, path='', directory=True)['identity']
                if (root / 'LocalCryptFolders' / identity).is_dir():
                    sources.append((CryptFiles(root / 'LocalCryptFolders', client, remote), '', 'LocalCrypt: ' + remote))
                for job in jobs:
                    if (not job['crypt'] or job['remote'] != remote
                            or client.connection_identity(remote) != job['identity']):
                        continue
                    physical = root / 'LocalCryptFolders' / job['identity'] / job['prefix']
                    if not physical.is_dir() or physical.is_symlink():
                        continue
                    provider = CryptFiles(root / 'LocalCryptFolders', client, remote, namespace=job['identity'])
                    folder = provider.mapping(job['prefix'], directory=True, decode=True)
                    sources.append((provider, folder, 'LocalCrypt: ' + remote))
            except (OSError, ValueError):
                failures += 1
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
        self.library_search = toga.TextInput(placeholder='Search libraries',
            on_change=self.filter_library, style=Pack(height=44, flex=1))
        self.library_rows = toga.Box(style=Pack(direction=COLUMN))
        self.library_records = []
        self.library_row_buttons = []
        self.library_view = toga.Box(children=[
            toga.Box(children=[self.library_search,
                toga.Button('Refresh', on_press=self.refresh_library_folders, style=Pack(height=44)), self.book_import],
                     style=Pack(direction=ROW, margin_bottom=8)),
            toga.ScrollContainer(horizontal=False, content=self.library_rows, style=Pack(flex=1)),
            self.book_status], style=Pack(direction=COLUMN, margin=12, flex=1))
        self.book_import.text = 'Import…'
        self.book_import.style.width = 88
        self.book_status.style.font_size = 12


    def filter_library(self, widget=None, **kwargs):
        if not hasattr(self, 'library_rows'):
            return
        for child in list(self.library_rows.children):
            self.library_rows.remove(child)
        self.library_row_buttons = []
        query = self.library_search.value.casefold().strip()
        for record in self.library_records:
            if query and query not in record['name'].casefold():
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
                    if provider.private and app.cloud_busy:
                        return
                    await app.show_files(local_root=not provider.private)
                    if provider.private and (app.cloud_client is not library['client']
                            or app.cloud_client.generation != library['generation']):
                        return
                    label = library['source'] if provider.private else 'Local files'
                    app.file_roots[label] = provider
                    app.update_file_locations()
                    await app.browser_file_location((label, library['folder']))
            button = toga.Button(record['name'], on_press=open_item,
                                 enabled=not self.book_busy, style=Pack(height=52))
            list_button(button)
            self.library_row_buttons.append(button)
            button.style.flex = 1
            self.library_rows.add(toga.Box(children=[
                template_icon(toga.ImageView(icon('files'), style=Pack(width=24, height=24, margin_right=12))),
                button], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=8, margin_left=8, margin_right=8)))
        if not self.library_row_buttons:
            self.library_rows.add(toga.Label('No matching libraries.' if query else 'No configured comics libraries found in Local or unlocked LocalCrypt copies.',
                                            style=Pack(margin_top=16)))

    async def refresh_library_folders(self, widget=None, **kwargs):
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


    def refresh_library(self):
        previous = self.book_loading
        self.book_loading = True
        records, failures = self.library_store.items()
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
