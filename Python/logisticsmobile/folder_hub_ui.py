"""A compact folder picker and focused, source-owned folder actions."""
import asyncio
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .folder_hub import hub_entries
from .cloud_ui import import_hint
from textwrap import fill


class FolderHubUI:
    async def refresh_folder_hub(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        if not self.cloud_busy:
            locations = await asyncio.to_thread(self.existing_crypt_locations)
            self.hub_crypt_locations = list(locations.items())
        if self.active_host:
            self.show_locations()

    def folder_choices(self):
        jobs = self.mirror_store().jobs
        remotes = [row.value for row in self.cloud_remote.items] if hasattr(self, 'cloud_remote') else []
        crypt = dict(getattr(self, 'hub_crypt_locations', ()))
        if not getattr(self, 'cloud_busy', False):
            crypt = dict(self.existing_crypt_locations())
            crypt.update(self.linked_crypt_locations())
        self.hub_crypt_locations = list(crypt.items())
        choices = {'All files': dict(source='Local', kind='local', value='', name='All files', copies=[])}
        for name, parts, copies in hub_entries(self.private_root, jobs, remotes, crypt.items()):
            for source, (kind, value) in copies:
                title = (name if not jobs[value]['prefix'] else jobs[value]['target']) if kind == 'job' else name
                if kind == 'remote':
                    value = value, ''
                copy = dict(source=source, kind=kind, value=value, name=title)
                group = choices.setdefault(title, dict(copy, copies=[]))
                group['copies'].append(copy)
        if getattr(self, 'cloud_open_remote', None) in remotes:
            for row in self.cloud_rows.values():
                if row['directory']:
                    label = self.cloud_open_remote + '/' + row['path']
                    copy = dict(source='Remote', kind='remote',
                        value=(self.cloud_open_remote, row['path']), name=label)
                    group = choices.setdefault(label, dict(copy, copies=[]))
                    group['copies'].append(copy)
        for group in choices.values():
            if group['copies']:
                primary = min(group['copies'], key=lambda copy: (copy['kind'] != 'job', copy['source'] == 'Remote'))
                group.update(primary)
        return choices

    def show_folder_picker(self, *, initialize=True):
        if self.window_id != 'primary':
            return self.show_window_boundary()
        if initialize:
            self.show_cloud(present=False)
        box = self.build_folder_picker()
        self.show_view(box, destination='files', root=True)

    def build_folder_picker(self):
        self.folder_picker_choices = self.folder_choices()
        self.folder_choice = toga.Selection(items=['Choose a folder…', *self.folder_picker_choices], style=Pack(height=44))
        self.folder_choice.value = 'Choose a folder…'
        box = toga.Box(children=[toga.Label('Files', style=Pack(font_size=24, margin_bottom=12)),
            self.folder_choice,
            toga.Label(import_hint('Choose a folder. Available actions follow its copies.'), style=Pack(font_size=12, margin_top=8)),
            toga.Box(children=[toga.Button('Connections', on_press=self.show_cloud_connections, style=Pack(height=44, flex=1)),
                toga.Button('Transfers', on_press=self.show_transfers, style=Pack(height=44, flex=1)),
                toga.Button('Refresh', on_press=self.refresh_folder_hub, style=Pack(height=44, flex=1))],
                style=Pack(direction=ROW, margin_top=12))], style=Pack(direction=COLUMN, margin=12, flex=1))
        self.folder_choice.on_change = self.choose_picker_folder
        return box

    def choose_picker_folder(self, widget, **kwargs):
        entry = self.folder_picker_choices.get(widget.value)
        if entry is not None:
            # UIKit Selection uses a text field with a wheel input view.
            # Dismiss that input before moving to another navigation page.
            native = getattr(getattr(widget, '_impl', None), 'native', None)
            if native is not None and hasattr(native, 'resignFirstResponder'):
                native.resignFirstResponder()
            self.show_picker_folder(entry)

    def show_picker_folder(self, entry):
        self.folder_picker_selected = dict(entry)
        entry = self.folder_picker_selected
        self.folder_picker_status = toga.Label('', style=Pack(font_size=12, margin_top=8))
        async def browse(widget=None, **kwargs):
            await self.open_picker_folder(entry)
        self.folder_action_controls = []
        self.folder_browse_button = toga.Button('Browse folder', on_press=browse,
            enabled=not self.cloud_busy or entry['source'] == 'Local', style=Pack(height=48))
        box = toga.Box(children=[toga.Button('Choose another folder', on_press=self.show_locations, style=Pack(height=44)),
            toga.Label(fill(entry['name'], width=24), style=Pack(font_size=22, margin_top=12)),
            toga.Label(entry['source'], style=Pack(font_size=12, margin_bottom=12)), self.folder_browse_button],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.folder_action_controls.append((self.folder_browse_button, entry['source'] != 'Local'))
        for copy in entry.get('copies', []):
            if copy == {key: entry[key] for key in ('source', 'kind', 'value', 'name')}:
                continue
            async def alternate(widget=None, selected=copy, **kwargs):
                await self.open_picker_folder(selected)
            button = toga.Button('Browse online' if copy['source'] == 'Remote' else 'Browse ' + copy['source'] + ' copy',
                on_press=alternate, style=Pack(height=44))
            self.folder_action_controls.append((button, copy['source'] != 'Local'))
            box.add(button)
        if entry['kind'] == 'job':
            key = entry['value']
            for label, action in [('Pull…', self.start_mirror_pull), ('Push…', self.start_mirror_review)]:
                def transfer(widget=None, selected=key, operation=action, **kw):
                    operation(selected)
                button = toga.Button(label, on_press=transfer, style=Pack(height=44))
                self.folder_action_controls.append((button, True))
                box.add(button)
        elif entry['kind'] == 'remote' or any(copy['kind'] == 'remote' for copy in entry.get('copies', [])):
            remote_copy = entry if entry['kind'] == 'remote' else next(copy for copy in entry['copies'] if copy['kind'] == 'remote')
            async def pull(widget=None, **kwargs):
                if await self.open_picker_folder(remote_copy):
                    await self.pull_remote_copy()
            button = toga.Button('Pull…', on_press=pull, style=Pack(height=44, margin_top=8))
            self.folder_action_controls.append((button, True))
            box.add(button)
            box.add(toga.Label('The first pull links a local copy. Later pulls and pushes use that copy automatically.', style=Pack(font_size=12)))
        if entry['source'] != 'Remote' and entry['value']:
            async def delete(widget=None, **kwargs):
                await self.delete_picker_folder(entry)
            button = toga.Button('Delete local folder…', on_press=delete, style=Pack(height=44, margin_top=12))
            self.folder_action_controls.append((button, True))
            box.add(button)
        box.add(self.folder_picker_status)
        self.refresh_folder_actions()
        self.register_transfer_status(box)
        self.show_view(box, destination='files', route='folder-options', title=entry['name'])

    async def open_picker_folder(self, entry):
        kind, value = entry['kind'], entry['value']
        if self.cloud_busy and entry['source'] != 'Local':
            self.folder_picker_status.text = 'This connection is busy. Local folders remain available.'
            return False
        if kind == 'job':
            job = self.mirror_store().jobs.get(value)
            if job is None:
                self.folder_picker_status.text = 'This folder mapping is no longer available. Choose another folder.'
                return False
            if job['crypt']:
                return await self.open_mirror_copy(value)
            value = job['target']
            kind = 'local'
        if kind == 'local':
            await self.show_files(local_root=True)
            return await self.browser_file_location(('Local files', value)) if value else True
        if kind == 'crypt':
            await self.show_files()
            return await self.browser_file_location((value, ''))
        remote, path = value
        if remote not in [row.value for row in self.cloud_remote.items]:
            self.folder_picker_status.text = 'Load the matching connection first.'
            return False
        self.cloud_remote.value = remote
        self.cloud_location.value = path
        self.show_cloud()
        await self.browse_cloud()
        return self.cloud_open_remote == remote and self.cloud_path == path

    def refresh_folder_actions(self):
        busy = getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False)
        for button, needs_idle in getattr(self, 'folder_action_controls', []):
            button.enabled = not busy or not needs_idle
        # Credential restore can finish while Files is already showing its root.
        # Refresh that selector in place instead of leaving a local-only snapshot.
        host = getattr(self, 'native_host', None)
        if (not busy and hasattr(self, 'folder_choice') and host is not None
                and host.state.destination == 'files' and not self.routes.screens['files']):
            choices = self.folder_choices()
            if choices != self.folder_picker_choices:
                self.folder_picker_choices = choices
                self.folder_choice.on_change = None
                try:
                    self.folder_choice.items = ['Choose a folder…', *choices]
                    self.folder_choice.value = 'Choose a folder…'
                    picker = getattr(self.folder_choice._impl, 'native_picker', None)
                    if picker is not None:
                        picker.reloadAllComponents()
                finally:
                    self.folder_choice.on_change = self.choose_picker_folder
        status = getattr(self, 'folder_picker_status', None)
        if status is not None:
            status.text = import_hint('A connection is busy. Local files remain available; online and encrypted operations wait until it finishes.') if busy else ''

    async def delete_picker_folder(self, entry):
        if self.cloud_busy or getattr(self, 'transfer_busy', False):
            return False
        if entry['kind'] == 'job':
            result = await self.delete_mirror_copy(entry['value'])
            if result:
                self.show_locations()
            return result
        store = self.mirror_store()
        if not self.clear_private_reader():
            return False
        if entry['kind'] == 'local':
            target = store.guard(self.private_root / 'LocalFiles' / entry['value'])
        elif entry['kind'] == 'crypt':
            remote = dict(self.hub_crypt_locations).get(entry['value'])
            if remote is None or self.cloud_client is None:
                return False
            identity = self.cloud_client.request('crypt_path', remote=remote, path='', directory=True)['identity']
            target = store.guard(self.private_root / 'LocalCryptFolders' / identity)
        else:
            return False
        try:
            if not await self.main_window.dialog(toga.ConfirmDialog('Delete local folder?',
                    'Delete ' + entry['name'] + ' from this device? This permanently deletes the folder and everything inside it. It cannot be undone. Online files are kept.')):
                return False
            if self.cloud_busy or getattr(self, 'transfer_busy', False) or not self.active_host:
                return False
            self.set_cloud_busy(True)
            try:
                await asyncio.to_thread(store.wipe_folder, target)
            finally:
                self.set_cloud_busy(False)
            self.show_locations()
            return True
        except (OSError, ValueError) as error:
            self.folder_picker_status.text = 'Deletion stopped: ' + str(error)[:200]
            return False
