"""Workspaces discovery, access and folder actions."""

import asyncio
import inspect
from contextlib import nullcontext
from textwrap import fill

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from commonUtils.ui.native.forms import fit_text
from features.rclone.mobile.messages import import_hint
from services.documents.locations import collection_path

from .appearance import action_button
from .folder_hub import folder_browse_copy
from .workspaces_screen import WorkspacesScreen


def reflow_folder_notice(app, width=None):
    """Fit the asynchronous incoming-files notice to its actual owning pane."""
    notice = getattr(app, 'incoming_notice', None)
    if notice is None:
        return
    if width is None:
        columns = getattr(app.adaptive, 'file_columns', None)
        if columns is not None:
            native = columns.sidebar.native
            safe = native.safeAreaInsets
            width = float(native.bounds.size.width - safe.left - safe.right) - 24
        else:
            width = app.adaptive.content_width('files', margin=32)
    fit_text(notice, max(24, width))


class FolderHubUI(WorkspacesScreen):
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
            self.update_folder_list(self.folder_all_choices)
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
        self.start_cloud_restore()
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
            self.discovery.request()
            return self.discovery.cached_choices()
        # Dummy/desktop hosts retain the synchronous path used by their callers.
        result = self.discovery.discover_now()
        self.hub_crypt_locations = list(result.crypt_locations)
        return result.choices

    def _schedule_folder_choices(self):
        return self.discovery.request()

    def invalidate_folder_discovery(self):
        self.discovery.invalidate()

    def show_folder_picker(self, *, initialize=True):
        if self.window_id != 'primary':
            return self.show_window_boundary()
        if initialize and getattr(self, 'folder_source', 'Local') != 'Local':
            self.start_cloud_restore()
        box = self.folder_picker_or_error()
        for tab in getattr(self, 'folder_tab_views', {}).values():
            tab.select(None)
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
        if source != 'Local' and not self.app.require_feature('rclone'):
            return
        # Source names and lock states need credentials, not a remote browser.
        if source in ('rclone', 'Network shares'):
            self.start_cloud_restore()
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

    def invoke_workspace_action(self, callback):
        if not self.app.active_host:
            return
        result = callback()
        if inspect.isawaitable(result):
            self.app.loop.create_task(result)

    def workspace_menu_actions(self, name):
        entry = self.folder_picker_choices.get(name)
        if entry is None:
            return []
        # Reuse the same command callbacks and enabled-state policy as the
        # fallback page. Building this content does not navigate or start I/O.
        page = self.show_picker_folder(entry, present=False)
        snapshot = dict(entry)
        controls = self.folder_action_controls
        status = self.folder_picker_status
        actions = []
        for button, _ in self.folder_action_controls:
            if not button.enabled or button.text == 'Open as Notes Library':
                continue
            async def invoke(control=button):
                if self.folder_picker_choices.get(name) != snapshot:
                    return
                self.folder_picker_selected = dict(snapshot)
                self.folder_action_controls = controls
                self.folder_picker_status = status
                self.refresh_folder_actions(refresh_choices=False)
                if control.enabled:
                    origin = self.navigation_generation
                    result = control.on_press()
                    if inspect.isawaitable(result):
                        await result
                    if self.navigation_generation == origin and status.text:
                        self.show_view(page, destination='files', route='folder-options', title=snapshot['name'])
            actions.append((button.text, invoke))
        if self.cloud_busy:
            actions.append(('Cancel current request', self.cancel_mirror_transfer
                if getattr(self, 'transfer_busy', False) else self.cancel_cloud))
        return actions

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
        box = toga.Box(children=[toga.Label(fill(entry['name'], width=24), style=Pack(font_size=22, margin_top=12)),
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
        return page


    async def open_picker_folder(self, entry):
        key = (self.folder_source, self.folder_local_group if self.folder_source == 'Local' else None)
        name = next((name for name, choice in self.folder_picker_choices.items()
                     if entry == choice or entry == folder_browse_copy(choice, self.folder_source)),
                    entry['name'])
        opened = await self._open_picker_folder(entry)
        if opened:
            for tab_key, tab in self.folder_tab_views.items():
                tab.select(name if tab_key == key else None)
        return opened

    async def _open_picker_folder(self, entry):
        kind, value = entry['kind'], entry['value']
        from .files_ui import local_read_available
        offline = entry['source'] == 'Local' or (entry['source'] == 'LocalCrypt'
            and local_read_available(self, private=True))
        # Check the busy state before any native credential/identity lookup.
        if self.cloud_busy and not offline:
            self.folder_picker_status.text = 'This connection is busy. Local folders remain available. Cancel the current request to use this online folder.'
            return False
        if entry['source'] != 'Local':
            # Workspaces may be the first credential entry point after startup.
            # Initialize the shared unlock/status controls before using them.
            self.show_cloud(present=False)
            remote = entry.get('remote')
            job = self.mirror_store().jobs.get(value) if kind in ('job', 'job-remote') else None
            remote = job['remote'] if job else remote or (value[0] if kind == 'remote' else '')
            from features.rclone.transfers.mobile.jobs import loaded_copy_cipher
            local_cipher = job and kind == 'job' and loaded_copy_cipher(self.cloud_client, job)
            if remote and not local_cipher:
                async with self.remote_activity('Checking connection for ' + remote):
                    if not await self.require_remote_credentials_async(remote,
                            identity=job['identity'] if job else entry.get('connection_identity'),
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
        if kind == 'inbox':
            return await self.show_files(location=('Received Files', value))
        if kind == 'local':
            return await self.show_files(location=('Local files', value))
        if kind == 'crypt':
            return await self.show_files(location=(value, ''))
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
        # The retained tree can remain visible beside a browser, and credentials
        # can change during transfers or in another window. Discovery reads only
        # published metadata/local names, so it is safe while the bridge is busy.
        if refresh_choices and hasattr(self, 'folder_list'):
            choices = self.folder_choices()
            self.update_folder_list(choices)
        status = getattr(self, 'folder_picker_status', None)
        if status is not None and not getattr(self, '_folder_opening', False):
            status.text = import_hint('A transfer is running. Local folders and encrypted copies remain available; online operations wait.'
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
