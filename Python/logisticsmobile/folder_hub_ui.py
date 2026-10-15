"""A folder list and focused, source-owned folder actions."""
import asyncio
import json
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .folder_hub import hub_entries, folder_tree, credential_choices
from .cloud_ui import import_hint
from textwrap import fill
from commonUtils.ui.native.presentation import list_button


def refresh_button(action):
    button = toga.Button('↻ Refresh', on_press=action, style=Pack(height=44, flex=1))
    backend = type(button._impl).__module__
    if backend.startswith('toga_iOS.'):
        from rubicon.objc import ObjCClass
        button.text = 'Refresh'
        button._impl.native.setImage(ObjCClass('UIImage').systemImageNamed('arrow.clockwise'), forState=0)
    elif backend.startswith('toga_android.'):
        from android import R
        native = button._impl.native
        button.text = 'Refresh'
        native.setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_popup_sync, 0, 0, 0)
    return button


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
                remote = jobs[value]['remote'] if kind == 'job' else name if kind in ('crypt', 'remote') else None
                copy = dict(source=source, kind=kind, value=value, name=title, remote=remote)
                group = choices.setdefault(title, dict(copy, copies=[]))
                group['copies'].append(copy)
        if getattr(self, 'cloud_open_remote', None) in remotes:
            for row in self.cloud_rows.values():
                if row['directory']:
                    label = self.cloud_open_remote + '/' + row['path']
                    copy = dict(source='Remote', kind='remote',
                        value=(self.cloud_open_remote, row['path']), name=label, remote=self.cloud_open_remote)
                    group = choices.setdefault(label, dict(copy, copies=[]))
                    group['copies'].append(copy)
        for group in choices.values():
            if group['copies']:
                primary = min(group['copies'], key=lambda copy: (copy['kind'] != 'job', copy['source'] == 'Remote'))
                group.update(primary)
                # Browse the mapped scope, rather than accidentally opening the
                # remote root for a pulled subfolder. Decode crypt paths on open.
                if primary['kind'] == 'job':
                    job = jobs[primary['value']]
                    if job['remote'] in remotes:
                        group['copies'] = [copy for copy in group['copies'] if copy['source'] != 'Remote']
                        group['copies'].append(dict(source='Remote', kind='job-remote',
                                                    value=job['id'], name=primary['name'], remote=job['remote']))
        return choices

    def show_folder_picker(self, *, initialize=True):
        if self.window_id != 'primary':
            return self.show_window_boundary()
        if initialize:
            self.show_cloud(present=False)
        box = self.build_folder_picker()
        self.show_view(box, destination='files', root=True)

    def build_folder_picker(self):
        self.folder_list = toga.Box(style=Pack(direction=COLUMN))
        self.folder_collapsed = getattr(self, 'folder_collapsed', set())
        packages = json.loads(self.preferences.values['remote_packages'])
        self.folder_credentials = {'All': None}
        for package in packages:
            self.folder_credentials[package['zip']] = set(package['remotes'])
        selected = getattr(self, 'folder_credential_name', 'All')
        self.folder_credential = toga.Selection(items=list(self.folder_credentials),
            value=selected if selected in self.folder_credentials else 'All', style=Pack(flex=1, height=44))
        self.folder_credential.on_change = self.change_folder_credential
        self.folder_refresh_button = refresh_button(self.refresh_folder_hub)
        self.folder_transfers_button = toga.Button('Transfers', on_press=self.show_transfers, style=Pack(height=44, flex=1))
        box = toga.Box(children=[toga.Box(children=[toga.Label('Credential', style=Pack(margin_right=8)),
                self.folder_credential], style=Pack(direction=ROW, margin_bottom=8)), toga.Box(children=[self.folder_transfers_button, self.folder_refresh_button],
                style=Pack(direction=ROW, margin_bottom=12)),
            toga.Button('Add SMB / Mac share…', on_press=self.show_smb_connection, style=Pack(height=44, margin_bottom=8)),
            toga.Label(import_hint('Choose a folder to browse, pull or push its available copies.'), style=Pack(font_size=12, margin_bottom=8)),
            toga.ScrollContainer(horizontal=False, content=self.folder_list, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.update_folder_list(self.folder_choices())
        return box

    def update_folder_list(self, choices):
        self.folder_picker_choices = choices
        for child in list(self.folder_list.children):
            self.folder_list.remove(child)
        self.folder_buttons = {}
        selected = self.folder_credentials.get(self.folder_credential.value)
        visible = choices if selected is None else credential_choices(choices, selected)
        self.folder_tree_buttons = {}

        def add_branch(branch, ancestors=()):
            for title, node in sorted(branch.items(), key=lambda item: item[0].casefold()):
                path = (*ancestors, title)
                children = node['children']
                row = toga.Box(style=Pack(direction=ROW, margin_left=18 * len(ancestors)))
                if children:
                    def toggle(widget=None, selected=path, **kwargs):
                        if selected in self.folder_collapsed:
                            self.folder_collapsed.remove(selected)
                        else:
                            self.folder_collapsed.add(selected)
                        self.update_folder_list(self.folder_picker_choices)
                    arrow = toga.Button('▸' if path in self.folder_collapsed else '▾', on_press=toggle,
                                        style=Pack(width=44, height=48))
                    self.folder_tree_buttons[path] = arrow
                    row.add(arrow)
                else:
                    row.add(toga.Box(style=Pack(width=44)))
                if node['names']:
                    name = node['names'][0]
                    def select(widget=None, selected=name, **kwargs):
                        self.choose_folder(selected)
                    button = list_button(toga.Button(title, on_press=select, style=Pack(height=48, flex=1)))
                    self.folder_buttons[name] = button
                    row.add(button)
                else:
                    row.add(list_button(toga.Button(title, on_press=toggle, style=Pack(height=48, flex=1))))
                self.folder_list.add(row)
                if children and path not in self.folder_collapsed:
                    add_branch(children, path)
        add_branch(folder_tree(visible))
        if not visible:
            self.folder_list.add(toga.Label('No folders available for this credential.'))

    def change_folder_credential(self, widget=None, **kwargs):
        self.folder_credential_name = self.folder_credential.value
        self.folder_collapsed.clear()
        self.update_folder_list(self.folder_choices())

    def choose_folder(self, name):
        entry = self.folder_picker_choices.get(name)
        if entry is not None:
            self.show_picker_folder(entry)

    def show_picker_folder(self, entry):
        self.folder_picker_selected = dict(entry)
        entry = self.folder_picker_selected
        self.folder_picker_status = toga.Label('', style=Pack(font_size=12, margin_top=8))
        async def browse(widget=None, **kwargs):
            await self.open_picker_folder(entry)
        self.folder_action_controls = []
        descriptions = {'Local': 'On this device', 'LocalCrypt': 'Encrypted on this device', 'Remote': 'Online'}
        self.folder_browse_button = toga.Button('Browse ' + entry['source'], on_press=browse,
            enabled=not self.cloud_busy or entry['source'] == 'Local', style=Pack(height=48))
        box = toga.Box(children=[toga.Button('Choose another folder', on_press=self.show_locations, style=Pack(height=44)),
            toga.Label(fill(entry['name'], width=24), style=Pack(font_size=22, margin_top=12)),
            toga.Label(descriptions[entry['source']], style=Pack(font_size=12, margin_bottom=12)), self.folder_browse_button],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.folder_action_controls.append((self.folder_browse_button, entry['source'] != 'Local'))
        seen = {(entry['source'], entry['kind'], str(entry['value']))}
        for copy in entry.get('copies', []):
            identity = (copy['source'], copy['kind'], str(copy['value']))
            if identity in seen:
                continue
            seen.add(identity)
            async def alternate(widget=None, selected=copy, **kwargs):
                await self.open_picker_folder(selected)
            button = toga.Button('Browse ' + copy['source'], on_press=alternate, style=Pack(height=44))
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
        # Retain a separate action page on phones; wide workspaces pair it with the tree.
        scroll = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
        page = toga.Box(children=[scroll], style=Pack(direction=COLUMN, flex=1, margin=12))
        self.show_view(page, destination='files', route='folder-options', title=entry['name'])

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
        if kind == 'job-remote':
            job = self.mirror_store().jobs.get(value)
            if job is None:
                self.folder_picker_status.text = 'This folder mapping is no longer available. Choose another folder.'
                return False
            remote, path = job['remote'], job['prefix']
            try:
                if self.cloud_client.connection_identity(remote) != job['identity']:
                    raise ValueError('Load the matching connection first.')
                if job['crypt']:
                    path = self.cloud_client.request('crypt_path', remote=remote, identity=job['cipher_identity'],
                                                     path=path, directory=True, decode=True)['path']
            except (OSError, ValueError) as error:
                self.folder_picker_status.text = str(error)
                return False
        else:
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
        # Credential restore can finish while Folder Hub is already showing its root.
        # Refresh the list in place instead of leaving a local-only snapshot.
        host = getattr(self, 'native_host', None)
        if (not busy and hasattr(self, 'folder_list') and host is not None
                and host.state.destination == 'files' and not self.routes.screens['files']):
            choices = self.folder_choices()
            if choices != self.folder_picker_choices:
                self.update_folder_list(choices)
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
