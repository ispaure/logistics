"""Workspaces discovery, access and folder actions."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import asyncio
import inspect
from textwrap import fill

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from commonUtils.ui.native.forms import fit_text
from services.documents.locations import collection_path

from .appearance import action_button
from .folder_hub import folder_browse_copy
from .ui_metrics import TOUCH_TARGET
from .workspaces_screen import WorkspacesScreen


def reflow_folder_notice(app, width=None):
    """Fit the Workspaces header and incoming notice to their owning pane."""
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
    picker = getattr(app, 'folder_credential', None)
    if picker is not None and type(picker._impl).__module__.startswith('toga_iOS.') and width > 0:
        fit_folder_credential(app, width)


def fit_folder_credential(app, width):
    """Keep the picker inline even when a narrow UIKit column needs a shorter label."""
    picker = app.folder_credential
    row = app.folder_credential_row
    if row.parent is None:
        return
    toggle = app.folder_view_toggle
    width -= toggle.style.width + toggle.style.margin_left
    caption = app.folder_credential_label
    # Keep a bounded field even when a long credential name increases the
    # native intrinsic width. The picker and its accessibility label stay intact.
    hint = caption.intrinsic.width
    caption_width = getattr(hint, 'value', hint or 0) + caption.style.margin_right
    show_caption = width >= caption_width + picker._MIN_WIDTH
    if show_caption and caption.parent is None:
        row.insert(0, caption)
    elif not show_caption and caption.parent is row:
        row.remove(caption)
    picker.style.width = max(TOUCH_TARGET, int(width - (caption_width if show_caption else 0)))


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

    async def refresh_hub_crypt_locations(self, *, valid=lambda: True):
        """Resolve native crypt locations once when credentials load."""
        client = getattr(self, 'cloud_client', None)
        generation = getattr(client, 'generation', None)
        def discover():
            roots = {}
            locations = dict(self.existing_crypt_locations(roots=roots))
            return locations, roots
        locations, roots = await asyncio.to_thread(discover)
        if (valid() and self.active_host and client is getattr(self, 'cloud_client', None)
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
        actions = []

        def add(label, callback, *, needs_idle=False):
            if needs_idle and (self.cloud_busy or self.transfer_busy):
                return

            def invoke():
                if (self.folder_picker_choices.get(name) == entry
                        and not (needs_idle and (self.cloud_busy or self.transfer_busy))):
                    return callback()
            actions.append((label, invoke))

        seen = set()
        for copy in (entry, *entry.get('copies', ())):
            key = copy['source'], copy['kind'], str(copy['value'])
            if key not in seen:
                seen.add(key)
                add('Browse ' + copy['source'], lambda copy=copy: self.open_picker_folder(copy))
        if entry['kind'] == 'job':
            add('Pull…', lambda: self.start_mirror_pull(entry['value']), needs_idle=True)
            add('Push…', lambda: self.start_mirror_review(entry['value']), needs_idle=True)
        else:
            remote = next((copy for copy in (entry, *entry.get('copies', ()))
                           if copy['kind'] == 'remote'), None)
            if remote is not None:
                async def pull():
                    if await self.open_picker_folder(remote):
                        await self.pull_remote_copy()
                add('Pull…', pull, needs_idle=True)
            if entry['kind'] == 'local' and entry['value']:
                add('Push…', lambda: self.show_local_push(entry['value']), needs_idle=True)
        if entry['source'] != 'Remote' and entry['value'] and entry['kind'] != 'shared-local':
            add('Delete local folder…', lambda: self.delete_picker_folder(entry), needs_idle=True)
        return actions

    def show_workspace_status(self, entry, message, *, waiting=False):
        from commonUtils.ui.native.forms import FittedLabel
        from .appearance import surface

        notice = surface(FittedLabel(message, style=Pack(margin_bottom=12)),
                         background='transparent', foreground='text', outlined=False)
        box = toga.Box(children=[notice], style=Pack(direction=COLUMN, margin=16, flex=1))
        box._workspace_status_label = notice
        if waiting and self.transfer_busy:
            box.add(action_button(toga.Button('View transfer progress', on_press=self.show_transfers,
                                              style=Pack(height=TOUCH_TARGET))))
        elif waiting:
            box.add(action_button(toga.Button('Cancel current request', on_press=self.cancel_cloud,
                                              style=Pack(height=TOUCH_TARGET))))
        if waiting:
            def dismiss():
                if (self.active_host and not (self.cloud_busy or self.transfer_busy
                                              or getattr(self, '_folder_opening', False))
                        and self.native_host.state.destination == 'files'
                        and box in self.routes.body('files').children):
                    self.routes.back()
            box._workspace_status_dismiss = dismiss
        self.show_view(box, destination='files', route='workspace-status', title=entry['name'])

    async def browse_hub_folder(self, name):
        entry = self.folder_picker_choices.get(name)
        if entry is None:
            return False
        return await self.open_picker_folder(folder_browse_copy(entry, self.folder_source))

    async def open_picker_folder(self, entry):
        if not self.active_host:
            return False
        from .files_ui import local_read_available
        offline = entry['source'] == 'Local' or (entry['source'] == 'LocalCrypt'
            and local_read_available(self, private=True))
        if entry == getattr(self, '_opening_workspace', None):
            return False
        if not offline and (self.cloud_busy or self.transfer_busy or getattr(self, '_folder_opening', False)):
            message = ('Online browsing will be available when the transfer ends.'
                       if self.transfer_busy else 'Wait for the current connection request before opening this workspace.')
            self.show_workspace_status(entry, message, waiting=True)
            return False

        key = (self.folder_source, self.folder_local_group if self.folder_source == 'Local' else None)
        name = next((name for name, choice in self.folder_picker_choices.items()
                     if entry == choice or entry == folder_browse_copy(choice, self.folder_source)),
                    entry['name'])
        origin = self.navigation_generation
        status = toga.Label('')
        token = self._folder_opening = object()
        self._opening_workspace = entry
        self.set_folder_loading('Opening ' + entry['source'] + ' folder…', busy=True)
        progress = self.folder_loading_progress
        progress.max = None
        progress.start()
        try:
            opened = await self._open_picker_folder(entry, status)
        finally:
            if self._folder_opening is token:
                self._folder_opening = False
                self._opening_workspace = None
                self.set_folder_loading()
                progress.stop()
                progress.max, progress.value = 100, 0
                self.dismiss_idle_workspace_status()
        if opened:
            for tab_key, tab in self.folder_tab_views.items():
                tab.select(name if tab_key == key else None)
        elif self.active_host and self.navigation_generation == origin:
            self.show_workspace_status(entry, status.text or 'Could not open this workspace. Check the connection and try again.')
        return opened

    async def _open_picker_folder(self, entry, status):
        kind, value = entry['kind'], entry['value']
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
                status.text = 'This folder mapping is no longer available. Choose another workspace.'
                return False
            if job['crypt']:
                return await self.open_mirror_copy(value)
            value = job['target']
            kind = 'local'
        if kind in ('shared-local', 'device-folder'):
            return await self.show_files(location=('Shared files', value))
        if kind == 'inbox':
            return await self.show_files(location=('Received Files', value))
        if kind in ('local', 'copy-folder'):
            return await self.show_files(location=('Local files', value))
        if kind == 'crypt':
            return await self.show_files(location=(value, ''))
        if kind == 'job-remote':
            job = self.mirror_store().jobs.get(value)
            if job is None:
                status.text = 'This folder mapping is no longer available. Choose another workspace.'
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
                status.text = str(error)
                return False
        else:
            remote, path = value
        if remote not in [row.value for row in self.cloud_remote.items]:
            status.text = 'Load the matching connection first.'
            return False
        self.cloud_remote.value = remote
        self.cloud_location.value = path
        self.show_cloud()
        return bool(await self.browse_cloud(preserve_path=True))

    def refresh_folder_actions(self, *, refresh_choices=True):
        # Discovery reads published metadata/local names while the bridge is busy.
        if refresh_choices and hasattr(self, 'folder_list') and not getattr(self.app, '_storage_changing', False):
            self.update_folder_list(self.folder_choices())
        self.dismiss_idle_workspace_status()

    def dismiss_idle_workspace_status(self):
        if (not hasattr(self, 'routes') or self.cloud_busy or self.transfer_busy
                or self.native_host.state.destination != 'files'):
            return
        for view in self.routes.body('files').children:
            dismiss = getattr(view, '_workspace_status_dismiss', None)
            if dismiss is not None:
                self.app.loop.call_soon(dismiss)

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
