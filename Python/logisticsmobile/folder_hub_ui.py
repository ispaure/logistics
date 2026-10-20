"""A folder list and focused, source-owned folder actions."""
from features.rclone.mobile.storage_location import collection_path
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from contextlib import nullcontext
import toga
from .control_icons import icon_button
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
from .folder_hub import hub_entries, folder_tree, credential_choices, source_choices, folder_storage_label, folder_browse_copy
from features.rclone.mobile.messages import import_hint
from textwrap import fill
from .appearance import list_button, batch_surfaces
from .appearance import action_button, accessible_name
from .folder_hub_style import (
    surface, source_tab, compact_icon, toolbar_button, folder_row, folder_name,
    source_actions, SOURCE_LABELS, ROW_HEIGHT, ROW_GAP, ENTRY_ICON_SLOT, ENTRY_ICON_SIZE,
    tree_anchor, tree_guide, TREE_LABEL_GAP, align_group_label,
)



class FolderHubUI:
    def legacy_name_visible(self, name, *, prefix='legacy-'):
        if not type(self._impl).__module__.startswith(('toga_iOS.', 'toga_android.')):
            return True
        show = getattr(self, 'show_legacy_session', False)
        return show or not str(name).casefold().startswith(prefix)

    def folder_path_visible(self, path, *, directory=True):
        from pathlib import PurePosixPath
        parts = PurePosixPath(str(path)).parts
        if any(part.casefold() in {'.ds_store', 'thumbs.db'} for part in parts):
            return False
        return all(self.legacy_name_visible(part) for part in (parts if directory else parts[:-1]))

    def library_folder_visible(self, record):
        return (self.folder_path_visible(record['folder'])
                and self.folder_path_visible(getattr(record['provider'], 'remote', '')))

    def change_show_legacy(self, widget, **kwargs):
        self.show_legacy_session = widget.value
        self.refresh_folder_visibility()

    def refresh_folder_visibility(self):
        vault = getattr(self.app, 'vault_browser', None)
        if vault is not None:
            vault.render_tree()
        if hasattr(self, 'folder_list'):
            self.update_folder_list(self.folder_picker_choices)
        for name in ('file_browser', 'remote_browser', 'editor_browser'):
            browser = getattr(self, name, None)
            if browser is not None:
                browser.query_changed()
        for drawer in self.adaptive.browsers.values():
            drawer.browser.query_changed()
            if drawer.destination == 'documents':
                drawer.refresh_menu()
        readers = getattr(self, 'readers', None)
        if readers is not None:
            readers.catalog.filter_library()

    async def refresh_folder_hub(self, widget=None, **kwargs):
        # Credentials already supply the remote/crypt snapshot. Refresh only
        # rereads local folder names and mappings; it must not wait on rclone,
        # including while a transfer or credential operation owns the bridge.
        self.show_cloud(present=False)
        recovering = bool(getattr(self, 'folder_hub_error', ''))
        try:
            choices = await self._schedule_folder_choices()
            if choices is None:
                return False
            if recovering or not hasattr(self, 'folder_list'):
                box = self.build_folder_picker(choices=choices)
                self.show_view(box, destination='files', root=True)
            # Successful discovery already published into an existing list.
        except (OSError, ValueError, IndexError, KeyError) as error:
            self.folder_hub_error = str(error)[:300]
            if hasattr(self, 'folder_loading_status'):
                self.set_folder_loading('Refresh failed: ' + self.folder_hub_error)
            return False
        self.folder_hub_error = ''
        if hasattr(self, 'folder_loading_status'):
            self.set_folder_loading()
        return True

    async def refresh_hub_crypt_locations(self):
        """Resolve native crypt locations once when credentials load."""
        client = getattr(self, 'cloud_client', None)
        generation = getattr(client, 'generation', None)
        def discover():
            roots = {}
            locations = dict(self.existing_crypt_locations(roots=roots))
            return locations, roots
        locations, roots = await asyncio.to_thread(discover)
        if (self.active_host and client is getattr(self, 'cloud_client', None)
                and generation == getattr(client, 'generation', None)):
            self.hub_crypt_locations = list(locations.items())
            self.hub_crypt_roots = roots
            self.folder_hub_error = ''

    def folder_choices(self):
        if type(self._impl).__module__.startswith(('toga_iOS.', 'toga_android.')):
            client = getattr(self, 'cloud_client', None)
            token = id(client), getattr(client, 'generation', None)
            self._schedule_folder_choices()
            if getattr(self, '_folder_choices_token', None) == token:
                return deepcopy(self._folder_choices_cache)
            self._folder_choices_cache = {}
            self._folder_choices_token = None
            # A credential change must not reveal a prior session's names while
            # its replacement snapshot is still being discovered.
            return {'All files': dict(source='Local', kind='local', value='',
                name='Browse All Files', copies=[], browser_root=True)}
        return self._discover_folder_choices()

    def _schedule_folder_choices(self):
        self._folder_refresh_again = True
        task = getattr(self, '_folder_discovery_task', None)
        if task is not None and not task.done():
            return task
        async def scan():
            while self.active_host and self._folder_refresh_again:
                self._folder_refresh_again = False
                epoch = getattr(self, '_folder_discovery_epoch', 0)
                client = getattr(self, 'cloud_client', None)
                token = id(client), getattr(client, 'generation', None)
                from features.rclone.transfers.mobile.jobs import resolved_job
                jobs = {key: dict(resolved_job(client, job)) for key, job in self.mirror_store().jobs.items()}
                remotes = tuple(self.loaded_remote_names())
                retained = deepcopy(self.retained_credential_associations())
                snapshot = SimpleNamespace(private_root=self.private_root, cloud_client=None,
                    mirror_store=lambda: SimpleNamespace(jobs=jobs),
                    loaded_remote_names=lambda: remotes,
                    retained_credential_associations=lambda: retained,
                    hub_crypt_locations=list(getattr(self, 'hub_crypt_locations', ())),
                    hub_crypt_roots=deepcopy(getattr(self, 'hub_crypt_roots', {})))
                try:
                    choices = await asyncio.to_thread(FolderHubUI._discover_folder_choices, snapshot)
                except (OSError, ValueError, IndexError, KeyError) as error:
                    if self.active_host:
                        self.folder_hub_error = str(error)[:300]
                        if hasattr(self, 'folder_loading_status'):
                            self.set_folder_loading('Refresh failed: ' + self.folder_hub_error)
                    return None
                if not self.active_host:
                    return None
                if epoch != getattr(self, '_folder_discovery_epoch', 0):
                    return None
                if token != (id(self.cloud_client), getattr(self.cloud_client, 'generation', None)):
                    self._folder_refresh_again = True
                    continue
                if self._folder_refresh_again:
                    continue
                self._folder_choices_cache, self._folder_choices_token = choices, token
                self.hub_crypt_locations = snapshot.hub_crypt_locations
                if hasattr(self, 'folder_list'):
                    self.update_folder_list(choices)
                return choices
            return None
        self._folder_discovery_task = self.app.loop.create_task(scan())
        return self._folder_discovery_task

    def invalidate_folder_discovery(self):
        self._folder_discovery_epoch = getattr(self, '_folder_discovery_epoch', 0) + 1
        self._folder_refresh_again = False
        self._folder_choices_cache = {}
        self._folder_choices_token = None

    def _discover_folder_choices(self):
        from features.rclone.transfers.mobile.jobs import resolved_job
        client = getattr(self, 'cloud_client', None)
        jobs = {key: resolved_job(client, job) for key, job in self.mirror_store().jobs.items()}
        # Retained metadata is a discovery index, never permission to browse.
        # Opening any locked remote still goes through the matching ZIP guard.
        retained = self.retained_credential_associations()
        remotes = sorted(set(self.loaded_remote_names()) | {
            remote for package in retained for remote in package['remotes']}, key=str.casefold)
        crypt = dict(getattr(self, 'hub_crypt_locations', ()))
        roots = getattr(self, 'hub_crypt_roots', {})
        if roots:
            # The account identities were resolved at credential load. Recheck
            # just their local directories, including copies created since then.
            base = collection_path(self.private_root, True)
            crypt = {}
            for label, (remote, identity) in roots.items():
                path = base / identity
                if path.is_dir() and not path.is_symlink() and any(path.iterdir()):
                    crypt[label] = remote
            self.hub_crypt_locations = list(crypt.items())
        # Rendering and menu opening must never enter the native bridge. A
        # credential load updates this discovery snapshot.
        choices = {'All files': dict(source='Local', kind='local', value='', name='Browse All Files', copies=[], browser_root=True)}
        for name, parts, copies in hub_entries(self.private_root, jobs, remotes, crypt.items()):
            for source, (kind, value) in copies:
                title = (name if not jobs[value]['prefix'] else jobs[value]['target']) if kind == 'job' else name
                if kind == 'remote':
                    value = value, ''
                remote = jobs[value]['remote'] if kind == 'job' else name if kind in ('crypt', 'remote') else None
                copy = dict(source=source, kind=kind, value=value, name=title, remote=remote)
                group = choices.setdefault(title, dict(copy, copies=[]))
                group['copies'].append(copy)
        for group in choices.values():
            if group['copies']:
                primary = min(group['copies'], key=lambda copy: (copy['kind'] != 'job', copy['source'] == 'Remote'))
                group.update(primary)
                # Browse the mapped scope, rather than accidentally opening the
                # remote root for a pulled subfolder. Decode crypt paths on open.
                if primary['kind'] == 'job':
                    job = jobs[primary['value']]
                    # The mapping already identifies this online folder even
                    # before credentials load. Opening it uses the usual unlock
                    # guard and resolves its mapped scope after authentication.
                    group['copies'] = [copy for copy in group['copies'] if copy['source'] != 'Remote']
                    group['copies'].append(dict(source='Remote', kind='job-remote',
                                                value=job['id'], name=primary['name'], remote=job['remote']))
                elif primary['kind'] == 'crypt' and not any(copy['source'] == 'Remote' for copy in group['copies']):
                    group['copies'].append(dict(source='Remote', kind='remote',
                                                value=(primary['remote'], ''), name=primary['name'],
                                                remote=primary['remote']))
        from .local_sources import shared_files
        shared = shared_files(self.private_root)
        if shared is not None:
            # Imported folders and mapped copies stay individually accessible.
            # The shared directory is a separate browse action below the list.
            choices['All files'] = dict(source='Local', kind='shared-local', value='',
                                        name='Browse All Files', copies=[], browser_root=True)
            for row in shared.list():
                if row['directory'] and row['name'] != 'Local':
                    title = row['name']
                    key = title if title not in choices else title + ' (Local)'
                    choices[key] = dict(source='Local', kind='shared-local', value=title, name=title, copies=[])
        return choices

    def show_folder_picker(self, *, initialize=True):
        if self.window_id != 'primary':
            return self.show_window_boundary()
        if initialize and getattr(self, 'folder_source', 'Local') != 'Local':
            self.show_cloud(present=False)
        box = self.folder_picker_or_error()
        self.show_view(box, destination='files', root=True)

    def folder_picker_or_error(self):
        """A discovery failure must leave a usable page, including on tab entry."""
        try:
            choices = self.folder_choices()
            view = getattr(self, 'folder_picker_view', None)
            if view is None:
                view = self.build_folder_picker(choices=choices)
            else:
                self.update_folder_list(choices)
            self.folder_hub_error = ''
            return view
        except (OSError, ValueError, IndexError, KeyError) as error:
            self.folder_picker_view = None
            self.folder_hub_error = str(error)[:300]
            async def local(widget=None, **kwargs):
                await self.show_files(local_root=True)
            return toga.Box(children=[
                toga.Label('Workspaces could not refresh.', style=Pack(font_size=18)),
                toga.Label(fill(self.folder_hub_error, 40), style=Pack(font_size=12)),
                toga.Button('Try again', on_press=self.refresh_folder_hub, style=Pack(height=48)),
                toga.Button('Browse local files', on_press=local, style=Pack(height=48)),
                toga.Button('Connections…', on_press=self.show_cloud_connections, style=Pack(height=48))],
                style=Pack(direction=COLUMN, margin=12, flex=1))

    def set_folder_loading(self, message='', *, busy=False):
        """Idle loading controls have no native view or reserved layout space."""
        self.folder_loading_status.text = message
        children = [self.folder_loading_status] if message else []
        if busy:
            children.append(self.folder_loading_progress)
        if list(self.folder_loading_box.children) != children:
            for child in list(self.folder_loading_box.children):
                self.folder_loading_box.remove(child)
            for child in children:
                self.folder_loading_box.add(child)

    def selected_folder_credential(self):
        try:
            selected = self.folder_credential.value
        except IndexError:
            # UIKit may still report the old row while credential items change.
            selected = getattr(self, 'folder_credential_name', 'All')
        return selected if selected in self.folder_credentials else 'All'

    def build_folder_picker(self, *, choices=None):
        # Finish discovery before replacing references to the visible controls.
        choices = self.folder_choices() if choices is None else choices
        self.folder_source = getattr(self, 'folder_source', 'Local')
        self.folder_source_styled = None
        self.folder_source_buttons = {}
        self.folder_source_tabs = surface(toga.Box(
            style=Pack(direction=ROW, margin_bottom=12)),
            radius=11, background='alternate', outlined=False)
        for source in ('Local', 'rclone', 'Network shares'):
            def select_source(widget=None, selected=source, **kwargs):
                if self.folder_source != selected:
                    self.change_folder_source(selected)
            button = toga.Button(SOURCE_LABELS[source], on_press=select_source,
                                 style=Pack(flex=1, height=44, font_size=13, margin=2))
            self.folder_source_buttons[source] = button
            self.folder_source_tabs.add(button)
        self.folder_list = toga.Box(style=Pack(direction=COLUMN))
        self.folder_tab_views = {}
        self.folder_tab_snapshot = None
        self.folder_collapsed = getattr(self, 'folder_collapsed', set())
        self.folder_credentials = self.credential_groups(source_choices(choices, 'rclone', self.network_share_remotes()))
        selected = getattr(self, 'folder_credential_name', 'All')
        self.folder_credential = toga.Selection(items=list(self.folder_credentials),
            value=selected if selected in self.folder_credentials else 'All', style=Pack(flex=1, height=44, font_size=14))
        self.folder_credential.on_change = self.change_folder_credential
        self.folder_transfers_button = toga.Button('Transfers', on_press=self.show_transfers, style=Pack(height=44, font_size=13, flex=1))
        toolbar_button(self.folder_transfers_button, 'arrow.up.arrow.down')
        self.folder_add_share_button = toga.Button('Add share…', on_press=self.show_smb_connection,
                                                  style=Pack(height=44, font_size=13, flex=1))
        toolbar_button(self.folder_add_share_button, 'plus')
        self.folder_add_remote_button = toga.Button('Add Remote…', on_press=self.show_cloud_connections,
                                                   style=Pack(height=44, font_size=13, flex=1))
        toolbar_button(self.folder_add_remote_button, 'plus')
        self.folder_loading_status = toga.Label('', style=Pack(font_size=12, margin_bottom=4))
        self.folder_loading_progress = toga.ProgressBar(max=100, value=0, style=Pack(height=4, margin_bottom=8))
        backend = type(self.folder_add_share_button._impl).__module__
        if backend.startswith('toga_iOS.'):
            self.folder_add_share_button._impl.native.accessibilityLabel = 'Add SMB / Mac share'
        elif backend.startswith('toga_android.'):
            self.folder_add_share_button._impl.native.setContentDescription('Add SMB / Mac share')
        self.folder_credential_row = toga.Box(children=[surface(toga.Label('Credential',
                style=Pack(font_size=13, width=80, margin_right=12)),
                background='window', foreground='muted', outlined=False),
                self.folder_credential], style=Pack(direction=ROW, align_items=CENTER, margin_bottom=12))
        self.folder_picker_header = toga.Box(style=Pack(direction=COLUMN))
        self.folder_source_actions = toga.Box(style=Pack(direction=ROW))
        self.folder_loading_box = toga.Box(style=Pack(direction=COLUMN))
        box = toga.Box(children=[self.folder_source_tabs, self.folder_picker_header, self.folder_source_actions,
            self.folder_loading_box,
            toga.ScrollContainer(horizontal=False, content=self.folder_list, style=Pack(flex=1))],
            style=Pack(direction=COLUMN, margin=(8, 16, 12, 16), flex=1))
        self.update_folder_list(choices)
        host = self.app
        self.register_transfer_status(box, visible_when=lambda: host.folder_source == 'rclone'
            and (getattr(host, 'transfer_busy', False)
                 or (getattr(host, 'transfer_notification', False) and not getattr(host, 'transfer_complete', False))))
        self.folder_picker_view = box
        return box

    @batch_surfaces()
    def update_folder_list(self, choices):
        import json
        network_remotes = self.network_share_remotes()
        # Setup hints depend on configuration, not search/visibility filters or
        # the selected credential. Retained locked connections count too.
        associations = (json.loads(self.preferences.values['remote_packages'])
                        + self.retained_credential_associations()
                        + list(getattr(self, 'session_credential_packages', ())))
        loaded_remotes = set(self.loaded_remote_names())
        configured = set(loaded_remotes)
        configured.update(remote for item in associations for remote in item['remotes'])
        configured.update(remote for item in getattr(getattr(self, 'cloud_client', None), 'package_records', ())
                          for remote in item['remotes'])
        self.folder_configured_sources = set()
        if network_remotes:
            self.folder_configured_sources.add('Network shares')
        if configured - network_remotes:
            self.folder_configured_sources.add('rclone')
        credentials = self.credential_groups(source_choices(choices, 'rclone', network_remotes))
        if credentials != self.folder_credentials:
            self.folder_credentials = credentials
            selected = self.selected_folder_credential()
            self.folder_credential.on_change = None
            self.folder_credential.items = list(credentials)
            self.folder_credential.value = selected if selected in credentials else 'All'
            self.folder_credential_name = selected if selected in credentials else 'All'
            self.folder_credential.on_change = self.change_folder_credential
        self.folder_picker_choices = choices
        selected = self.folder_credentials.get(self.selected_folder_credential())
        visible = source_choices(choices, self.folder_source, network_remotes)
        if self.folder_source == 'rclone' and selected is not None:
            visible = credential_choices(visible, selected)
        if self.folder_source_styled != self.folder_source:
            for source, button in self.folder_source_buttons.items():
                source_tab(button, source == self.folder_source)
                accessible_name(button, SOURCE_LABELS[source] + (' selected' if source == self.folder_source else ''))
            self.folder_source_styled = self.folder_source
        if self.folder_source == 'rclone' and not self.folder_picker_header.children:
            self.folder_picker_header.add(self.folder_credential_row)
        elif self.folder_source != 'rclone' and self.folder_picker_header.children:
            self.folder_picker_header.remove(self.folder_credential_row)
        source_actions(self.app)
        visible = {name: entry for name, entry in visible.items()
                   if self.folder_path_visible(name) and self.folder_path_visible(entry.get('remote') or '')}
        # Native selectors and retained metadata are relatively expensive. Read
        # them once, rather than once for every encrypted folder in the tree.
        crypt_remotes = set(getattr(self.app, 'cloud_crypt_remotes', ()))
        crypt_remotes.update(remote for package in getattr(self.app.cloud_client, 'package_records', ())
                             for remote in package.get('crypt_identities', {}))
        crypt_remotes.update(remote for package in associations
                             for remote in package.get('crypt_remotes', ()))
        # Cache each source's native rows independently. Discovery/credential
        # metadata may change without changing anything this source displays.
        tab = self.folder_tab_views.get(self.folder_source)
        if tab is None:
            tab = SimpleNamespace(content=toga.Box(style=Pack(direction=COLUMN)),
                                  nodes={}, panels={}, extras={})
            self.folder_tab_views[self.folder_source] = tab
        self._render_folder_tab(tab, visible, loaded_remotes, crypt_remotes)
        self.folder_buttons, self.folder_tree_buttons = tab.buttons, tab.tree_buttons
        self.mount_folder_tab(tab.content)

    def _render_folder_tab(self, tab, visible, loaded_remotes, crypt_remotes):
        """Reconcile controls and hierarchy; unchanged rows keep native identity."""
        nodes, panels, buttons, tree_buttons = {}, {}, {}, {}

        def sync(parent, children):
            # Native remove/add triggers layout. Touch only changed positions.
            for child in list(parent.children):
                if child not in children:
                    parent.remove(child)
            for index, child in enumerate(children):
                if index < len(parent.children) and parent.children[index] is child:
                    continue
                if child.parent is not None:
                    child.parent.remove(child)
                parent.insert(index, child)

        def divider():
            return surface(toga.Box(style=Pack(height=1, margin_left=34)),
                           radius=0, background='transparent', outlined=False)

        def branch_height(branch):
            return sum(ROW_HEIGHT + ROW_GAP
                       + (branch_height(node['children']) if node['children'] else 0)
                       for node in branch.values()) + max(0, len(branch) - 1)

        def child_midpoints(branch):
            offset = 0
            for _, node in sorted(branch.items(), key=lambda item: item[0].casefold()):
                yield offset + ROW_HEIGHT / 2
                offset += ROW_HEIGHT + ROW_GAP + 1
                if node['children']:
                    offset += branch_height(node['children'])

        def row_for(path, title, node):
            name = node['names'][0] if node['names'] else None
            if name is not None:
                entry = visible[name]
                target = folder_browse_copy(entry, self.folder_source)
                storage = (folder_storage_label(entry) if self.folder_source == 'Network shares'
                           else target['source'])
                remote = target.get('remote') or entry.get('remote')
                encrypted = ('LocalCrypt' in storage or ('Remote' in storage and (
                    remote in crypt_remotes
                    or any(copy['source'] == 'LocalCrypt' for copy in entry.get('copies', ())))))
                state = ('unlocked' if remote in loaded_remotes else 'locked') if encrypted else None
                icon = 'folder_' + state if state else 'folder'
                description = storage + (', ' + state if state else '')
                presentation = (title, icon, description)
            record = tab.nodes.get(path)
            if record is None or record.name != name:
                row = toga.Box(style=Pack(direction=ROW, align_items=CENTER,
                                         height=ROW_HEIGHT, margin_bottom=ROW_GAP))
                record = SimpleNamespace(name=name, row=row, presentation=None,
                                         group=None, child_box=None, divider=None, geometry=None)
                if name is not None:
                    async def select(widget=None, selected=name, **kwargs):
                        return await self.browse_hub_folder(selected)
                    record.indicator = icon_button(icon, name + ', ' + description, on_press=select)
                    record.button = folder_name(list_button(toga.Button(title, on_press=select,
                        style=Pack(height=ROW_HEIGHT, flex=1))))
                    def options(widget=None, selected=name, **kwargs):
                        self.choose_folder(selected)
                    record.menu = icon_button('more', 'Workspace actions for ' + name, on_press=options)
                    compact_icon(record.menu, width=44, size=18)
                    row.add(record.indicator, record.button, record.menu)
                    folder_row(row)
                else:
                    record.group = surface(toga.Label(title,
                        style=Pack(height=20, margin_top=14, margin_bottom=14, font_size=15,
                                   margin_left=TREE_LABEL_GAP if len(path) > 1 else 0,
                                   font_weight='bold', flex=1)), radius=0,
                        background='transparent', foreground='text', outlined=False)
                    align_group_label(record.group)
                    accessible_name(record.group, title + ', group')
                    row.add(record.group)
            if name is not None:
                if record.presentation != presentation:
                    if record.indicator.control_icon != icon:
                        from .control_icons import apply_icon
                        apply_icon(record.indicator, icon, name + ', ' + description, preserve_layout=True)
                    if record.button.text != title:
                        record.button.text = title
                    accessible_name(record.indicator, name + ', ' + description)
                    accessible_name(record.button, name + ', ' + description)
                    color = 'folder_' + state if state else 'folder'
                    if record.presentation is None:
                        compact_icon(record.indicator, width=ENTRY_ICON_SLOT, size=ENTRY_ICON_SIZE, foreground=color)
                    else:
                        surface(record.indicator, radius=0, background='transparent', foreground=color, outlined=False)
                    record.presentation = presentation
                buttons[name] = record.button
            else:
                tree_buttons[path] = record.group
            nodes[path] = record
            return record

        def add_branch(branch, parent, ancestors=()):
            children = []
            for index, (title, node) in enumerate(sorted(branch.items(), key=lambda item: item[0].casefold())):
                path = (*ancestors, title)
                record = row_for(path, title, node)
                children.append(record.row)
                if node['children']:
                    if record.child_box is None:
                        record.child_content = toga.Box(style=Pack(direction=COLUMN, flex=1))
                        record.child_box = toga.Box(style=Pack(direction=ROW))
                    add_branch(node['children'], record.child_content, path)
                    geometry = (branch_height(node['children']), tuple(child_midpoints(node['children'])),
                                tree_anchor(record.group))
                    if record.geometry != geometry:
                        record.guide = tree_guide(*geometry)
                        record.geometry = geometry
                    sync(record.child_box, [record.guide, record.child_content])
                    children.append(record.child_box)
                elif record.child_box is not None:
                    # Drop removed descendants even when their parent remains.
                    sync(record.child_content, [])
                if index < len(branch) - 1:
                    if record.divider is None:
                        record.divider = divider()
                    children.append(record.divider)
            sync(parent, children)

        content = []
        folders = {name: entry for name, entry in visible.items() if not entry.get('browser_root')}
        for title, node in sorted(folder_tree(folders).items(), key=lambda item: item[0].casefold()):
            panel = tab.panels.get(title)
            if panel is None:
                branch_content = toga.Box(style=Pack(direction=COLUMN))
                panel = surface(toga.Box(children=[branch_content], style=Pack(direction=COLUMN)),
                                radius=0, background='transparent', outlined=False)
                panel.style.margin_bottom = 12
            add_branch({title: node}, panel.children[0])
            panels[title] = panel
            content.append(panel)
        if not folders:
            if 'empty' not in tab.extras:
                tab.extras['empty'] = toga.Label('No folders available for this source.')
            content.append(tab.extras['empty'])
        browse = {}
        for name, entry in visible.items():
            if entry.get('browser_root'):
                button = getattr(tab, 'browse', {}).get(name)
                if button is None:
                    async def browse_all(widget=None, selected=name, **kwargs):
                        return await self.browse_hub_folder(selected)
                    button = list_button(toga.Button('Browse All Files', on_press=browse_all,
                        style=Pack(height=ROW_HEIGHT, margin_top=12)))
                browse[name] = buttons[name] = button
                content.append(button)
        if 'legend' not in tab.extras:
            legend = toga.Box(style=Pack(direction=ROW, align_items=CENTER, margin_top=4))
            for label, icon, color in (('Locked', 'folder_locked', 'folder_locked'),
                                       ('Unlocked', 'folder_unlocked', 'folder_unlocked')):
                mark = icon_button(icon, label + ' folder')
                compact_icon(mark, width=28, height=32, size=22, background='window', foreground=color)
                legend.add(mark)
                legend.add(surface(toga.Label(label, style=Pack(font_size=11, margin_right=16)),
                                   background='window', foreground='muted', outlined=False))
            tab.extras['legend'] = legend
        content.append(tab.extras['legend'])
        sync(tab.content, content)
        tab.nodes, tab.panels, tab.browse = nodes, panels, browse
        tab.buttons, tab.tree_buttons = buttons, tree_buttons

    def mount_folder_tab(self, content):
        if list(self.folder_list.children) != [content]:
            for child in list(self.folder_list.children):
                self.folder_list.remove(child)
            self.folder_list.add(content)

    def network_share_remotes(self):
        import json
        associations = (json.loads(self.preferences.values['remote_packages'])
                        + self.retained_credential_associations()
                        + list(getattr(self, 'session_credential_packages', ())))
        associations += [dict(zip=item['package_name'], remotes=item['remotes'])
                         for item in getattr(getattr(self, 'cloud_client', None), 'package_records', ())]
        return {remote for item in associations
                if item['zip'] in ('Network shares', 'Session network shares')
                for remote in item['remotes']}

    def change_folder_source(self, source):
        # The startup hub is built before the remote UI. Native tab navigation
        # reuses that page, so entering a remote source must start saved restore.
        if source in ('rclone', 'Network shares'):
            self.show_cloud(present=False)
        self.folder_source = source
        self.folder_credential_name = 'All'
        # Resetting a native Selection can emit on_change synchronously. The
        # source switch below already renders the new filter exactly once.
        self.folder_credential.on_change = None
        self.folder_credential.value = 'All'
        self.folder_credential.on_change = self.change_folder_credential
        self.folder_collapsed.clear()
        self.update_folder_list(self.folder_choices())
        self.app.refresh_transfer_status()

    def change_folder_credential(self, widget=None, **kwargs):
        self.folder_credential_name = self.selected_folder_credential()
        self.folder_collapsed.clear()
        self.update_folder_list(self.folder_choices())

    def choose_folder(self, name):
        entry = self.folder_picker_choices.get(name)
        if entry is not None:
            self.show_picker_folder(entry)

    async def browse_hub_folder(self, name):
        action_entry = self.folder_picker_choices.get(name)
        if action_entry is None:
            return False
        entry = folder_browse_copy(action_entry, self.folder_source)
        if getattr(self, '_folder_opening', False):
            # A pending online folder must not disable Workspaces. Local
            # browsing can proceed; another online tap gets actions and Cancel.
            from .files_ui import local_read_available
            offline = entry['source'] == 'Local' or (entry['source'] == 'LocalCrypt'
                and local_read_available(self, private=True))
            if name == getattr(self, '_folder_opening_name', None) or not offline:
                self.show_picker_folder(action_entry)
                self.folder_picker_status.text = 'A folder is opening. Local folders remain available; use Cancel to stop the current request.'
                return False
        # Keep the status/credential-resume owner available if opening fails.
        # Successful taps proceed directly into the existing guarded browser.
        page = self.show_picker_folder(action_entry, present=False)
        origin = self.navigation_generation
        self.folder_picker_status.text = 'Opening ' + entry['source'] + ' folder…'
        self.set_folder_loading(self.folder_picker_status.text, busy=True)
        self.folder_loading_progress.max = None
        self.folder_loading_progress.start()
        loading_status, loading_progress = self.folder_loading_status, self.folder_loading_progress
        token = self._folder_opening = object()
        self._folder_opening_name = name
        try:
            await asyncio.sleep(0)
            if entry['source'] == 'Remote':
                opened = await self.open_picker_folder(entry)
            else:
                # The folder's loading bar already covers local-only browsing.
                # Remote progress controls may not have been constructed yet.
                activity = (self.remote_activity('Opening ' + entry['source'] + ' folder')
                            if hasattr(self.app, 'cloud_view') else nullcontext())
                async with activity:
                    opened = await self.open_picker_folder(entry)
        finally:
            if self._folder_opening is token:
                self._folder_opening = False
                self._folder_opening_name = None
                self.set_folder_loading()
                self.folder_loading_progress.stop()
                self.folder_loading_progress.max, self.folder_loading_progress.value = 100, 0
            if not self._folder_opening or loading_progress is not self.folder_loading_progress:
                loading_status.text = ''
                loading_progress.stop()
                loading_progress.max, loading_progress.value = 100, 0
        # Credential guards may have presented an unlock page. Keep it visible.
        if not opened and self.folder_picker_status.text.startswith('Opening '):
            self.folder_picker_status.text = 'Folder did not open. Unlock its connection or retry.'
        if not opened and self.navigation_generation == origin and self.folder_picker_status.text:
            self.show_view(page, destination='files', route='folder-options', title=entry['name'])
        return opened

    def show_picker_folder(self, entry, *, present=True):
        self.folder_picker_selected = dict(entry)
        entry = self.folder_picker_selected
        self.folder_picker_status = toga.Label('', style=Pack(font_size=12, margin_top=8))
        async def browse(widget=None, **kwargs):
            await self.open_picker_folder(entry)
        self.folder_action_controls = []
        descriptions = {'Local': 'On this device', 'LocalCrypt': 'Encrypted on this device', 'Remote': 'Online'}
        self.folder_browse_button = action_button(toga.Button('Browse ' + entry['source'], on_press=browse,
            enabled=not self.cloud_busy or entry['source'] == 'Local'
            or (entry['source'] == 'LocalCrypt' and (getattr(self, 'transfer_busy', False) or getattr(self, 'remote_read_busy', False))), style=Pack(height=48)))
        box = toga.Box(children=[toga.Button('Choose another workspace', on_press=self.show_locations, style=Pack(height=48)),
            toga.Label(fill(entry['name'], width=24), style=Pack(font_size=22, margin_top=12)),
            toga.Label(descriptions[entry['source']], style=Pack(font_size=12, margin_bottom=12)), self.folder_browse_button],
            style=Pack(direction=COLUMN, margin=12, flex=1))
        self.folder_action_controls.append((self.folder_browse_button, entry['source'] == 'Remote'))
        self.folder_browse_button._requires_crypt_session = entry['source'] == 'LocalCrypt'
        seen = {(entry['source'], entry['kind'], str(entry['value']))}
        for copy in entry.get('copies', []):
            identity = (copy['source'], copy['kind'], str(copy['value']))
            if identity in seen:
                continue
            seen.add(identity)
            async def alternate(widget=None, selected=copy, **kwargs):
                await self.open_picker_folder(selected)
            button = toga.Button('Browse ' + copy['source'], on_press=alternate, style=Pack(height=48))
            self.folder_action_controls.append((button, copy['source'] == 'Remote'))
            button._requires_crypt_session = copy['source'] == 'LocalCrypt'
            box.add(button)
        if entry['kind'] == 'job':
            box.add(toga.Label('Pull: Remote → ' + entry['source'] + '\nPush: ' + entry['source'] + ' → Remote',
                               style=Pack(font_size=12, margin_top=12, margin_bottom=8)))
            key = entry['value']
            for label, action in [('Pull…', self.start_mirror_pull), ('Push…', self.start_mirror_review)]:
                def transfer(widget=None, selected=key, operation=action, **kw):
                    operation(selected)
                button = toga.Button(label, on_press=transfer, style=Pack(height=48))
                self.folder_action_controls.append((button, True))
                box.add(button)
        elif entry['kind'] == 'remote' or any(copy['kind'] == 'remote' for copy in entry.get('copies', [])):
            remote_copy = entry if entry['kind'] == 'remote' else next(copy for copy in entry['copies'] if copy['kind'] == 'remote')
            async def pull(widget=None, **kwargs):
                if await self.open_picker_folder(remote_copy):
                    await self.pull_remote_copy()
            button = toga.Button('Pull…', on_press=pull, style=Pack(height=48, margin_top=8))
            self.folder_action_controls.append((button, True))
            box.add(button)
            box.add(toga.Label(fill('The first pull links a local copy. Later pulls and pushes use that copy automatically.', width=32), style=Pack(font_size=12)))
        if entry['kind'] == 'local' and entry['value']:
            def push_local(widget=None, **kwargs):
                self.show_local_push(entry['value'])
            button = toga.Button('Push…', on_press=push_local, style=Pack(height=48))
            self.folder_action_controls.append((button, True))
            box.add(button)
        if entry['source'] != 'Remote' and entry['value'] and entry['kind'] != 'shared-local':
            async def delete(widget=None, **kwargs):
                await self.delete_picker_folder(entry)
            button = action_button(toga.Button('Delete local folder…', on_press=delete,
                style=Pack(height=48, margin_top=24)), destructive=True)
            self.folder_action_controls.append((button, True))
            box.add(button)
        box.add(self.folder_picker_status)
        if self.cloud_busy:
            box.add(toga.Button('Cancel current request', on_press=(self.cancel_mirror_transfer
                if getattr(self, 'transfer_busy', False) else self.cancel_cloud), style=Pack(height=48)))
        self.refresh_folder_actions(refresh_choices=False)
        self.register_transfer_status(box)
        # Retain a separate action page on phones; wide workspaces pair it with the tree.
        scroll = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
        page = toga.Box(children=[scroll], style=Pack(direction=COLUMN, flex=1, margin=12))
        if present:
            self.show_view(page, destination='files', route='folder-options', title=entry['name'])
        from .notes_actions import offer_notes
        notes_button = toga.Button('Open Notes Library', style=Pack(height=48))
        self.folder_action_controls.append((notes_button, entry['source'] == 'Remote'))
        notes_button._requires_crypt_session = entry['source'] == 'LocalCrypt'
        host = getattr(self, 'app', self)
        if present:
            previous = getattr(host, '_notes_offer_task', None)
            if previous is not None and not previous.done():
                previous.cancel()
            host._notes_offer_task = host.loop.create_task(offer_notes(host, dict(entry), box, notes_button, self.folder_picker_status))
        return page


    async def open_picker_folder(self, entry):
        kind, value = entry['kind'], entry['value']
        from .files_ui import local_read_available
        offline = entry['source'] == 'Local' or (entry['source'] == 'LocalCrypt'
            and local_read_available(self, private=True))
        # Check the busy state before any native credential/identity lookup.
        if self.cloud_busy and not offline:
            self.folder_picker_status.text = 'This connection is busy. Local folders remain available. Cancel the current request to use this online folder.'
            return False
        if entry['source'] != 'Local':
            remote = entry.get('remote')
            job = self.mirror_store().jobs.get(value) if kind in ('job', 'job-remote') else None
            remote = job['remote'] if job else remote or (value[0] if kind == 'remote' else '')
            if remote:
                async with self.remote_activity('Checking connection for ' + remote):
                    if not await self.require_remote_credentials_async(remote,
                            identity=job['identity'] if job else None,
                            resume=lambda: self.open_picker_folder(entry)):
                        return False
        if kind == 'job':
            job = self.mirror_store().jobs.get(value)
            if job is None:
                self.folder_picker_status.text = 'This folder mapping is no longer available. Choose another workspace.'
                return False
            if job['crypt']:
                return await self.open_mirror_copy(value)
            value = job['target']
            kind = 'local'
        if kind == 'shared-local':
            return await self.show_files(location=('Shared files', value))
        if kind == 'local':
            return await self.show_files(location=('Local files', value))
        if kind == 'crypt':
            await self.show_files()
            return await self.browser_file_location((value, ''))
        if kind == 'job-remote':
            job = self.mirror_store().jobs.get(value)
            if job is None:
                self.folder_picker_status.text = 'This folder mapping is no longer available. Choose another workspace.'
                return False
            try:
                from features.rclone.transfers.mobile.jobs import remote_location
                origin = self.navigation_generation
                client, generation = self.cloud_client, getattr(self.cloud_client, 'generation', None)
                async with self.remote_activity('Opening mapped online folder'):
                    remote, path = await asyncio.to_thread(remote_location, client, dict(job))
                if (not self.active_host or self.navigation_generation != origin
                        or client is not self.cloud_client or generation != getattr(client, 'generation', None)):
                    return False
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
        await self.browse_cloud(preserve_path=True)
        return self.cloud_open_remote == remote and self.cloud_path == path

    def refresh_folder_actions(self, *, refresh_choices=True):
        busy = getattr(self, 'cloud_busy', False) or getattr(self, 'transfer_busy', False)
        for button, needs_idle in getattr(self, 'folder_action_controls', []):
            button.enabled = not busy or (not needs_idle and (
                not getattr(button, '_requires_crypt_session', False) or getattr(self, 'transfer_busy', False)
                or getattr(self, 'remote_read_busy', False)))
        # Credential restore can finish while Workspaces is already showing its root.
        # Refresh the list in place instead of leaving a local-only snapshot.
        host = getattr(self, 'native_host', None)
        if (refresh_choices and not busy and hasattr(self, 'folder_list') and host is not None
                and host.state.destination == 'files' and not self.routes.screens['files']):
            choices = self.folder_choices()
            credentials = self.credential_groups(source_choices(choices, 'rclone', self.network_share_remotes()))
            self.update_folder_list(choices)
        status = getattr(self, 'folder_picker_status', None)
        if status is not None and not getattr(self, '_folder_opening', False):
            status.text = import_hint('A transfer is running. Local and LocalCrypt files remain available; online operations wait.'
                if getattr(self, 'transfer_busy', False) else 'A connection is busy. Local folders remain available.') if busy else ''

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
            target = store.guard(collection_path(self.private_root) / entry['value'])
        elif entry['kind'] == 'crypt':
            remote = dict(self.hub_crypt_locations).get(entry['value'])
            if remote is None or self.cloud_client is None:
                return False
            target = self.crypt_folder_target(remote)
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
