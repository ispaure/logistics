"""Native read-only remote browser and access to existing offline copies."""
from commonUtils.ui.native.password_input import PasswordInput
from features.rclone.mobile.storage_location import collection_path
import asyncio
from contextlib import asynccontextmanager, contextmanager
from io import BytesIO
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.rclone.mobile.cloud import CloudClient, CredentialBusyError, Downloads, PACKAGE_LIMIT, download_name
from features.rclone.localcrypt.mobile.ui import LocalCryptUI


from features.rclone.mobile.messages import import_hint


async def explain_remote_busy(app):
    transferring = getattr(app, 'transfer_busy', False)
    message = ('Cloud previews are unavailable while a transfer is running. Wait for the transfer to finish, or open a Local copy.'
               if transferring else 'The connection is busy. Wait for the current request to finish, then open the file again.')
    app.cloud_status.value = message
    await app.main_window.dialog(toga.InfoDialog('Transfer in progress' if transferring else 'Connection busy', message))


class SelectedCredentialZIP:
    """Consume picker access immediately; retain only bounded ZIP bytes in memory."""
    def __init__(self, access, reference):
        with access.open(reference) as (name, source):
            self.data = source.read(PACKAGE_LIMIT + 1)
        if len(self.data) > PACKAGE_LIMIT:
            raise ValueError('Credential ZIPs are limited to 1 MiB.')
        self.name = download_name(name)

    @contextmanager
    def open(self, reference=None):
        with BytesIO(self.data) as stream:
            yield self.name, stream


class CloudUI(LocalCryptUI):
    @asynccontextmanager
    async def remote_activity(self, stage):
        """Keep the current network step and elapsed wait visible on the UI loop."""
        loop = asyncio.get_running_loop()
        state = dict(stage=stage, started=loop.time(), active=True)
        activities = getattr(self, '_remote_activities', None)
        if activities is None:
            activities = self._remote_activities = []
        def update(message):
            if state['active']:
                state.update(stage=message, started=loop.time())
                render()
        def render():
            if not activities or activities[-1] is not state:
                return
            elapsed = int(loop.time() - state['started'])
            message = f"{state['stage']} · {elapsed}s"
            self.cloud_status.value = message
            status = getattr(self, 'folder_picker_status', None)
            if status is not None:
                status.text = message
            if getattr(self, '_folder_opening', False):
                self.folder_loading_status.text = message
        def progress(message):
            if state['active'] and not loop.is_closed():
                loop.call_soon_threadsafe(update, message)
        async def tick():
            while True:
                await asyncio.sleep(1)
                render()
        bar = self.cloud_transfer_progress
        state['render'] = render
        activities.append(state)
        bar.max = None
        bar.start()
        render()
        task = asyncio.create_task(tick())
        try:
            # Let UIKit draw the status and spinner before starting any work.
            await asyncio.sleep(0)
            yield progress
        finally:
            state['active'] = False
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            activities.remove(state)
            if activities:
                bar.max = None
                bar.start()
                activities[-1]['render']()
            else:
                bar.stop()
                bar.max, bar.value = 100, 0

    def prepare_cloud(self):
        """Prepare connection state without constructing browser/settings views."""
        if getattr(self, '_cloud_prepared', False):
            return
        self.cloud_path = ''
        self.cloud_open_remote = None
        self.cloud_rows = {}
        self.cloud_crypt_remotes = set()
        self.cloud_pending_zip = None
        self._cloud_setup_error = ''
        if self.cloud_client is None:
            try:
                from features.rclone.mobile.credential_vault import ProtectedVault
                self.cloud_client = CloudClient(vault=ProtectedVault.for_app(self.app))
            except Exception:
                self._cloud_setup_error = 'The native remote engine or device credential protection is unavailable.'
        self._cloud_prepared = True

    def start_cloud_restore(self):
        """Load saved credentials once, independently of the connection screens."""
        if getattr(self, '_storage_changing', False):
            return
        self.prepare_cloud()
        task = getattr(self, 'cloud_restore_task', None)
        if task is None and self.cloud_client is not None and getattr(self.cloud_client, 'vault', None) is not None:
            self.set_cloud_busy(True)
            task = self.cloud_restore_task = self.loop.create_task(self.restore_cloud(initial=True))
        return task

    def show_cloud(self, widget=None, *, present=True, **kwargs):
        if getattr(self, '_storage_changing', False):
            return
        self.prepare_cloud()
        if not hasattr(self, 'cloud_view'):
            self.downloads = Downloads(self.private_root / 'Downloads')
            error = getattr(self, '_cloud_restore_error', '') or self._cloud_setup_error
            self.cloud_choose = toga.Button('Choose credential ZIP…', on_press=self.choose_cloud_package, style=Pack(height=44))
            self.cloud_selected_zip = toga.Label('No ZIP selected', style=Pack(font_size=14))
            self.cloud_import_message = toga.Label(import_hint('Choose a ZIP, then enter its password and tap Load remotes.'), style=Pack(font_size=14))
            self.cloud_password = PasswordInput(placeholder='ZIP password (if encrypted)', on_confirm=self.import_cloud_package, style=Pack(flex=1, height=44))
            self.cloud_import = toga.Button('Load remotes', on_press=self.import_cloud_package, style=Pack(height=44, font_weight='bold'))
            self.cloud_probe = toga.Button('Check rclone engine', on_press=self.probe_cloud, style=Pack(height=44))
            self.cloud_remember = toga.Switch('Save credentials on this device', value=True, style=Pack(height=44))
            self.cloud_package = toga.Label('Credential package: none', style=Pack(font_size=14))
            self.cloud_reload = toga.Button('Reload saved credentials', on_press=self.restore_cloud, style=Pack(height=44))
            self.cloud_remote = toga.Selection(on_change=self.cloud_remote_changed, style=Pack(height=44))
            self.cloud_remote_heading = toga.Label('Choose remote · tap the name below', style=Pack(font_size=14))
            self.cloud_remote_help = toga.Label('Load a credential ZIP to see its remotes.', style=Pack(font_size=14))
            self.cloud_location = toga.TextInput(placeholder='Folder within remote', style=Pack(height=44))
            self.cloud_browse = toga.Button('Browse folder', on_press=self.browse_cloud, style=Pack(flex=1, height=44))
            self.cloud_up = self.rclone_ui.icon_button('up', 'Parent folder', on_press=self.parent_cloud)
            self.cloud_entries = toga.Selection(style=Pack(height=44))
            NativeBrowser = self.rclone_ui.NativeBrowser
            self.remote_browser = NativeBrowser(bounded_pages=True, folder_visible=self.folder_path_visible, selected=self.browser_cloud_selected, open_folder=self.browser_cloud_folder, navigate=self.browser_cloud_location, open_file=self.open_remote_document)
            self.remote_browser.on_item_actions = self.show_remote_item_actions
            self.remote_browser.navigation_controls.remove(self.remote_browser.back_button)
            self.remote_browser.search.placeholder = 'Search this folder'
            self.cloud_open = toga.Button('Open folder', on_press=self.open_cloud_folder, style=Pack(height=44))
            self.cloud_cancel = toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44))
            self.cloud_clear = toga.Button('Forget saved credentials', on_press=self.clear_cloud, style=Pack(height=44))
            self.cloud_lock = toga.Button('Lock connections', on_press=self.lock_cloud, style=Pack(height=48))
            self.cloud_retained_box = toga.Box(style=Pack(direction=COLUMN))
            self.cloud_status = NativeBrowser.status_label(value=error or 'Choose saved or session-only credentials, then import a ZIP. Its password is never saved.',
                                                       style=Pack(height=20, margin_top=14, margin_bottom=14))
            self.download_selector = toga.Selection(style=Pack(height=44))
            self.download_open = toga.Button('Open private copy', on_press=self.open_download, style=Pack(flex=1, height=44))
            self.download_export = toga.Button('Export private copy…', on_press=self.export_download, style=Pack(flex=1, height=44))
            ui = self.rclone_ui
            self.cloud_connections_status = ui.settings_note(error)
            self.cloud_import_entry = toga.Button('Import credential ZIP…', on_press=self.begin_cloud_import, style=Pack(height=48))
            troubleshooting, self.cloud_settings_toggle = ui.settings_disclosure('Advanced & troubleshooting', [
                ui.settings_group([self.cloud_reload, self.cloud_probe, self.cloud_clear])])
            self.cloud_connections_view = ui.settings_page('rclone connections',
                'Your cloud storage, ready when you need it.', [
                    ui.settings_heading('CREDENTIAL PACKAGES'), self.cloud_retained_box,
                    self.cloud_import_entry, ui.settings_note('Import a package exported from Logistics desktop.'),
                    ui.settings_heading('SESSION'), ui.settings_group([self.cloud_lock]),
                    ui.settings_note('Lock to stop access until you unlock again. This also locks SMB connections.'),
                    troubleshooting, self.cloud_connections_status])
            self.cloud_import_view = ui.settings_page('Import credential ZIP',
                'Choose your Logistics credential package.', [
                    self.cloud_choose, self.cloud_selected_zip,
                    ui.settings_group([ui.settings_field('ZIP password (if encrypted)', self.cloud_password)]),
                    self.cloud_import, self.cloud_import_message,
                    ui.settings_heading('STORAGE'), ui.settings_group([self.cloud_remember]),
                    ui.settings_note('Off keeps decoded credentials in memory. Password-protected ZIPs are retained encrypted for future unlocking. The ZIP password is never saved.')])
            self.cloud_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
                toga.Label('Remote files', style=Pack(font_size=22)),
                toga.Button('Manage connections…', on_press=self.show_cloud_connections, style=Pack(height=44)),
                self.cloud_remote_heading, self.cloud_remote, self.cloud_remote_help,
                self.cloud_location, toga.Box(children=[self.cloud_browse, self.cloud_up], style=Pack(direction=ROW)),
                self.cloud_status, self.cloud_cancel, self.remote_browser.widget,
                self.cloud_open,
                toga.Label('Downloaded copies', style=Pack(font_size=18, margin_top=12)), self.download_selector,
                toga.Box(children=[self.download_open, self.download_export], style=Pack(direction=ROW)),
                *self.build_localcrypt()], style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            self.cloud_advanced_view = self.cloud_view
            advanced = self.cloud_advanced_view.content
            for control in (self.cloud_remote, self.cloud_status, self.remote_browser.widget,
                            self.cloud_open, self.cloud_cancel, self.cloud_browse):
                advanced.remove(control)
            self.cloud_up.parent.remove(self.cloud_up)
            self.cloud_open.style.flex = 1
            advanced.add(self.cloud_remote)
            advanced.add(self.cloud_browse)
            advanced.insert(advanced.children.index(self.cloud_location) + 1,
                toga.Button('Browse folder', on_press=self.browse_cloud_path, style=Pack(height=44)))
            self.cloud_remote.style.flex = 1
            self.cloud_browse.text = 'Open remote'
            self.cloud_cancel.text = 'Cancel'
            self.cloud_status.style.font_size = 15
            self.cloud_status.style.flex = 1
            self.cloud_cancel.style.width = 68
            self.cloud_transfer_progress = toga.ProgressBar(max=100, value=0, style=Pack(height=4))
            self.remote_browser.attach_location_header(self.cloud_status, self.cloud_up)
            self.remote_browser.location_bar.update('', remote=True)
            self.cloud_view = toga.Box(children=[
                self.remote_browser.location_bar,
                self.remote_browser.scroll_container()],
                style=Pack(direction=COLUMN, margin=12, flex=1))
            self.refresh_downloads()
            self.set_loaded_remote_names(self.loaded_remote_names())
            self.cloud_package.text = self.loaded_package_label() if self.cloud_client is not None else 'Credential package: none'
            if getattr(self, '_cloud_restored', False):
                self._publish_restored_connections(self.loaded_remote_names())
            self.start_cloud_restore()
            self.set_cloud_busy(self.cloud_busy)
        if getattr(self, 'cloud_remote_generation', getattr(self.cloud_client, 'generation', None)) != getattr(self.cloud_client, 'generation', None):
            self.set_loaded_remote_names(self.loaded_remote_names())
            self.cloud_package.text = self.loaded_package_label()
        if present:
            self.show_view(self.cloud_view, destination='files', route='remote-browser', title='Cloud File Browser')

    async def browse_cloud_path(self, widget=None, **kwargs):
        if await self.browse_cloud(preserve_path=True):
            self.show_cloud()

    def show_cloud_actions(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_view(self.cloud_advanced_view, destination='files', route='remote-actions', title='Remote actions')

    def show_remote_item_actions(self, row=None, *, password_required=False, **kwargs):
        row = row if isinstance(row, dict) else self.cloud_rows.get(self.cloud_entries.value)
        if not row:
            return
        from pathlib import Path
        private_label = self.rclone_ui.private_label
        remote, generation = self.cloud_open_remote, self.cloud_client.generation
        password = PasswordInput(placeholder='Inner ZIP password', style=Pack(height=48))
        status = toga.Label('Enter the comic ZIP password.' if password_required else '', style=Pack(font_size=12))
        async def open_item(widget=None, **kw):
            if self.cloud_client.generation != generation or self.cloud_open_remote != remote:
                password.value = ''
                status.text = 'The connection changed. Browse the remote again.'
                return False
            if row['directory']:
                return await self.browser_cloud_folder(row)
            self.crypt_password.value, password.value = password.value, ''
            return await self.open_remote_document(row)
        password.on_confirm = open_item
        if not password_required:
            actions = [('Open folder' if row['directory'] else 'Open preview', open_item)]
            if not row['directory'] and Path(row['path']).suffix.lower() in {'.cbz', '.zip', '.epub'}:
                actions.append(('Archive password…', lambda: self.show_remote_item_actions(row, password_required=True)))
            return self.remote_browser.show_item_menu(actions)
        controls = [toga.Label(private_label(row['path']), style=Pack(font_size=18))]
        if not row['directory']:
            controls.append(toga.Label('Remote preview · Read-only'))
            if Path(row['path']).suffix.lower() in {'.cbz', '.zip', '.epub'}:
                controls.append(password)
        controls.extend([status, toga.Button('Open folder' if row['directory'] else 'Open preview',
            on_press=open_item, style=Pack(height=48)),
            toga.Button('Back to remote files', on_press=self.show_cloud, style=Pack(height=48))])
        self.remote_item_view = toga.Box(children=controls, style=Pack(direction=COLUMN, margin=12, flex=1))
        self.remote_item_password = password
        self.show_view(self.remote_item_view, destination='files', route='remote-item', title=Path(row['path']).name)
        if password_required:
            password.focus()

    def show_cloud_connections(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        self._cloud_connections_opened = True
        self.refresh_retained_credentials()
        self.show_view(self.cloud_connections_view, destination='settings', route='connections', title='rclone connections')

    async def begin_cloud_import(self, widget=None, **kwargs):
        self.show_cloud_import()
        await self.choose_cloud_package()

    def show_cloud_import(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        self.show_view(self.cloud_import_view, destination='settings', route='import-credentials', title='Import credential ZIP')

    def refresh_retained_credentials(self):
        if not getattr(self, '_cloud_connections_opened', False):
            return
        for child in list(self.cloud_retained_box.children):
            self.cloud_retained_box.remove(child)
        try:
            cache = self.retained_packages()
            rows = sorted(getattr(cache, 'items', {}).items(), key=lambda row: row[1]['zip'].casefold())
            rows = [(key, item) for key, item in rows if self.legacy_name_visible(item['zip'], prefix='legacy')]
        except (OSError, ValueError):
            self.cloud_retained_box.add(toga.Label('Retained ZIPs are unavailable. Unlock the device and try again.'))
            return
        self.cloud_retained_buttons = {}
        records = {item['package_name']: item for item in getattr(self.cloud_client, 'package_records', ())
                   if item['package_name'] not in ('Network shares', 'Session network shares')
                   and self.legacy_name_visible(item['package_name'], prefix='legacy')}
        if not records and self.cloud_client is not None and self.loaded_remote_names():
            name = getattr(self.cloud_client, 'package_name', '')
            if name and name not in ('Network shares', 'Session network shares'):
                records[name] = dict(remotes=self.loaded_remote_names(), saved=False)
        ui = self.rclone_ui
        for name, record in records.items():
            def browse(widget=None, **kwargs):
                self.show_locations()
            names = self.visible_remote_names(record['remotes'])
            row = ui.settings_group([
                toga.Label(import_hint(name), style=Pack(font_weight='bold', margin_top=8)),
                ui.settings_note(f'{len(names)} remotes · ' + ('saved on this device' if record.get('saved') else 'session only')),
                toga.Button('Browse remote files', on_press=browse, enabled=not self.cloud_busy, style=Pack(height=48))])
            self.cloud_retained_box.add(row)
        for key, item in rows:
            if item['zip'] in records:
                continue
            def unlock(widget=None, selected=key, **kwargs):
                if not self.cloud_busy:
                    self.show_retained_unlock(selected, destination='settings', resume=self.show_locations)
            button = toga.Button('Unlock ' + item['zip'], on_press=unlock,
                                 enabled=not self.cloud_busy, style=Pack(height=44))
            self.cloud_retained_buttons[key] = button
            self.cloud_retained_box.add(ui.settings_group([
                toga.Label(import_hint(item['zip']), style=Pack(font_weight='bold', margin_top=8)),
                ui.settings_note('Locked · retained on this device'), button]))
        if not rows and not records:
            self.cloud_retained_box.add(ui.settings_note('No credential packages yet. Import a ZIP to get started.'))
        if hasattr(self, 'cloud_connections_status'):
            self.cloud_connections_status.text = self.cloud_status.value
        if hasattr(self.cloud_connections_view, 'reflow'):
            self.cloud_connections_view.reflow()

    def loaded_remote_names(self):
        client = getattr(self, 'cloud_client', None)
        # Package state is shared across iPad scenes; native selectors are not.
        # Never let an empty or stale selector hide already unlocked remotes.
        records = getattr(client, 'package_records', None)
        if records is not None:
            return self.visible_remote_names([name for item in records for name in item['remotes']])
        generation = getattr(client, 'generation', None)
        if getattr(self, 'cloud_remote_generation', generation) != generation:
            return []
        return [row.value for row in self.cloud_remote.items] if hasattr(self, 'cloud_remote') else []

    def set_loaded_remote_names(self, names):
        records = getattr(self.cloud_client, 'package_records', ())
        if records:
            names = self.visible_remote_names([name for item in records for name in item['remotes']])
        self.cloud_remote_generation = getattr(self.cloud_client, 'generation', None)
        if hasattr(self, 'cloud_remote'):
            self.cloud_remote.items = names

    async def lock_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None or not self.clear_private_reader():
            return
        self.set_cloud_busy(True)
        try:
            self.clear_private_catalog()
            await asyncio.to_thread(self.cloud_client.lock)
            self.set_loaded_remote_names([])
            self.cloud_crypt_remotes = set()
            self.session_credential_packages = []
            self.cloud_password.value = self.crypt_password.value = ''
            if hasattr(self, 'credential_unlock_password'):
                self.credential_unlock_password.value = ''
            self.cloud_pending_zip = None
            self.cloud_selected_zip.text = 'No ZIP selected'
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_open_remote = None
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_package.text = 'Credential session: locked'
            self.cloud_status.value = 'Session locked. Retained ZIPs and saved credentials were kept.'
        except (OSError, ValueError):
            self.cloud_status.value = 'The credential session could not be locked. Try again.'
        finally:
            self.set_cloud_busy(False)

    def show_smb_connection(self, widget=None, **kwargs):
        return self.smb_connection.show_smb_connection(widget, **kwargs)

    def change_smb_guest(self, widget=None, **kwargs):
        return self.smb_connection.change_smb_guest(widget, **kwargs)

    async def connect_smb(self, widget=None, **kwargs):
        return await self.smb_connection.connect_smb(widget, **kwargs)

    def selected_cloud_remote(self):
        try:
            return self.cloud_remote.value
        except IndexError:
            # Native spinners can report the previous row during a source reset.
            return None

    def set_cloud_busy(self, value):
        if getattr(self, '_storage_changing', False) and not value:
            return
        self.cloud_busy = value
        privacy = getattr(self, 'screen_privacy', None)
        if privacy is not None:
            privacy.refresh()
        if not hasattr(self, 'cloud_import_entry'):
            # Storage recovery must work before the cloud browser is created,
            # including when its selected collection drive is unavailable.
            self.refresh_folder_actions()
            return
        for item in (self.cloud_import_entry, self.cloud_settings_toggle, self.cloud_choose, self.cloud_password, self.cloud_import, self.cloud_probe, self.cloud_remote,
                     self.cloud_location, self.cloud_browse, self.cloud_up, self.cloud_entries,
                     self.cloud_open, self.cloud_clear, self.cloud_lock, self.cloud_reload, self.cloud_remember,
                     self.crypt_open, self.crypt_refresh, self.crypt_selector, self.crypt_password):
            item.enabled = not value and self.cloud_client is not None
        for name in ('smb_name', 'smb_host', 'smb_user', 'smb_password', 'smb_domain', 'smb_port',
                     'smb_guest', 'smb_remember', 'smb_connect', 'smb_advanced_toggle'):
            item = getattr(self, name, None)
            if item is not None:
                item.enabled = not value and self.cloud_client is not None
        self.cloud_import.enabled = not value and self.cloud_client is not None and self.cloud_pending_zip is not None
        self.cloud_cancel.enabled = value
        # Request controls take no list space while the browser is idle.
        header = self.remote_browser.location_bar
        if value:
            if self.cloud_cancel not in header.children:
                header.add(self.cloud_cancel)
            if self.cloud_transfer_progress.parent is None:
                header.parent.insert(header.parent.children.index(header) + 1, self.cloud_transfer_progress)
        else:
            if self.cloud_cancel in header.children:
                header.remove(self.cloud_cancel)
            if self.cloud_transfer_progress.parent is not None:
                self.cloud_transfer_progress.parent.remove(self.cloud_transfer_progress)
        if not self.cloud_path:
            self.cloud_up.enabled = True
        self.refresh_folder_actions()
        self.download_open.enabled = self.download_export.enabled = not value and bool(self.download_labels)
        self.refresh_retained_credentials()

    def cloud_remote_changed(self, widget=None, **kwargs):
        self.refresh_cloud_remote_help()
        if hasattr(self, 'download_labels'):
            self.set_cloud_busy(self.cloud_busy)

    def refresh_cloud_remote_help(self):
        if not hasattr(self, 'cloud_remote_help'):
            return
        if not hasattr(self, 'cloud_remote_help'):
            return
        selected = self.selected_cloud_remote()
        if not selected:
            message = 'Load a credential ZIP to see its remotes.'
        elif selected in self.cloud_crypt_remotes:
            message = 'Crypt remote selected: ' + selected + '.\nTap Browse folder to see decrypted filenames.'
        elif self.cloud_crypt_remotes:
            names = sorted(self.cloud_crypt_remotes)
            available = ', '.join(names[:3]) + (f' (+{len(names) - 3} more)' if len(names) > 3 else '')
            message = 'Regular remote selected: ' + selected + '.\nCrypt remotes: ' + available + '.\nTap the remote name above to choose a crypt.'
        else:
            message = 'No crypt remote in the loaded ZIP.\nTo use crypt, include its configuration and its backing remote in the ZIP.'
        self.cloud_remote_help.text = import_hint(message)

    async def _load_crypt_remote_names(self):
        # Alternate client adapters may not expose crypt support.
        kinds = getattr(self.cloud_client, 'crypt_remotes', lambda: ())
        records = getattr(self.cloud_client, 'package_records', ())
        if records and all('crypt_identities' in record for record in records):
            self.cloud_crypt_remotes = {remote for record in records for remote in record['crypt_identities']}
        else:
            self.cloud_crypt_remotes = set(await asyncio.to_thread(kinds))
        try:
            cache = self.retained_packages()
            update = getattr(cache, 'update_crypt_remotes', None)
            if update is not None:
                records = {item['package_name']: item for item in getattr(self.cloud_client, 'package_records', ())}
                for key, item in tuple(cache.items.items()):
                    record = records.get(item['zip'])
                    if record is not None and record.get('document_cache_id') != key:
                        continue
                    if record is not None or item['zip'] == getattr(self.cloud_client, 'package_name', ''):
                        await asyncio.to_thread(update, key, self.cloud_crypt_remotes,
                            aliases=record.get('aliases', {}) if record else {})
        except (OSError, ValueError) as error:
            self.folder_hub_error = 'Could not save folder type metadata: ' + str(error)[:200]
        try:
            await self.refresh_hub_crypt_locations()
        except (OSError, ValueError) as error:
            self.folder_hub_error = str(error)[:300]
        self.refresh_cloud_remote_help()

    def retained_packages(self):
        if getattr(getattr(self, 'cloud_client', None), 'vault', None) is None:
            return None
        if not hasattr(self, 'credential_packages'):
            from features.rclone.mobile.credential_packages import CredentialPackages
            from features.rclone.mobile.credential_vault import ProtectedVault
            self.credential_packages = CredentialPackages(ProtectedVault.for_app(self.app, packages=True), self.cloud_client, document_cache_root=self.app.credential_document_lists.root)
        return self.credential_packages

    def remember_credential_association(self, name, remotes, *, session_only):
        import json
        previous = json.loads(self.preferences.values['remote_packages'])
        packages = [item for item in previous if item['zip'] != name and not item['session_only']]
        association = dict(zip=name, remotes=list(remotes), session_only=session_only)
        sessions = [item for item in getattr(self, 'session_credential_packages', ()) if item['zip'] != name]
        self.session_credential_packages = [*sessions, association] if session_only else sessions
        if session_only:
            return
        packages.append(association)
        if packages[-32:] != previous:
            self.preferences.save(remote_packages=json.dumps(packages[-32:]))

    def visible_remote_names(self, names):
        exclusions = self.rclone_ui.exclusions
        from services.folders.policy import visible_name
        original = {alias: name for item in getattr(self.cloud_client, 'package_records', ())
                    for name, alias in item.get('aliases', {}).items()}
        rules = exclusions()
        return sorted((name for name in names if visible_name(original.get(name, name), rules, remote=True)), key=str.casefold)

    def package_remote_names(self, label, fallback):
        method = getattr(self.cloud_client, 'package_remotes', None)
        return method(label, fallback) if method else fallback

    def remember_loaded_packages(self, label, names, *, session_only):
        visible_remotes = self.rclone_ui.visible_remotes
        records = getattr(self.cloud_client, 'package_records', ())
        if records:
            for item in records:
                self.remember_credential_association(item['package_name'], self.visible_remote_names(item['remotes']), session_only=not item['saved'])
        else:
            self.remember_credential_association(label, self.visible_remote_names(names), session_only=session_only)

    def loaded_package_label(self):
        records = getattr(self.cloud_client, 'package_records', ())
        if not records:
            return 'Credential package: ' + (getattr(self.cloud_client, 'package_name', '') or 'none')
        return 'Loaded:\n' + '\n'.join(item['package_name'] + (' (saved)' if item['saved'] else ' (session only)') for item in records)

    def credential_groups(self, choices=None):
        import json
        from pathlib import Path
        groups = {'All': None}
        associations = {item['zip']: item for item in json.loads(self.preferences.values['remote_packages'])
                        + self.retained_credential_associations() + getattr(self, 'session_credential_packages', [])}
        loaded = set()
        for item in getattr(getattr(self, 'cloud_client', None), 'package_records', ()):
            loaded.add(item['package_name'])
            associations[item['package_name']] = dict(zip=item['package_name'], remotes=item['remotes'])
        available = {copy['remote'] for entry in (self.folder_choices() if choices is None else choices).values()
                     for copy in entry.get('copies', ()) if copy.get('remote')}
        if choices is None:
            # Loaded packages are authoritative while folder discovery is still
            # pending. An explicit choices snapshot still scopes its own rows.
            available.update(self.loaded_remote_names())
        for item in associations.values():
            if item['zip'] in ('Network shares', 'Session network shares'):
                continue
            if not self.legacy_name_visible(Path(item['zip']).name, prefix='legacy'):
                continue
            remotes = set(item['remotes']) & available
            if not remotes and item['zip'] not in loaded:
                continue
            name = Path(item['zip']).name
            base = name[:-4] if name.lower().endswith('.zip') else name
            title = base
            number = 2
            while title in groups:
                title = f'{base} ({number})'
                number += 1
            groups[title] = remotes
        return groups

    def home_unlock_candidates(self):
        """Inspect retained metadata/files only; never restore or decode credentials."""
        try:
            cache = self.retained_packages()
            loaded = {item['package_name'] for item in
                      getattr(getattr(self, 'cloud_client', None), 'package_records', ())}
            return sorted(((key, item) for key, item in getattr(cache, 'items', {}).items()
                           if item['zip'] not in loaded
                           and self.legacy_name_visible(item['zip'], prefix='legacy')
                           and cache.path(key).is_file()), key=lambda row: row[1]['zip'].casefold())
        except (OSError, ValueError):
            return []

    def show_home_unlock(self, widget=None, **kwargs):
        if not self.app.checkpoint():
            return
        self.show_cloud(present=False)
        choices = self.home_unlock_candidates()
        if choices:
            self.show_retained_unlock(choices[0][0], destination='home',
                                      resume=self.app.show_home, choices=choices)
        else:
            self.app.show_home()

    def retained_credential_associations(self):
        try:
            cache = self.retained_packages()
            return [dict(zip=item['zip'], remotes=list(item['remotes']), session_only=True,
                         crypt_remotes=list(item.get('crypt_remotes', ())))
                    for item in getattr(cache, 'items', {}).values()] if cache is not None else []
        except (OSError, ValueError):
            return []

    async def require_remote_credentials_async(self, remote, *, identity=None, resume=None):
        origin = self.navigation_generation
        restore = getattr(self, 'cloud_restore_task', None)
        if restore is not None:
            await asyncio.shield(restore)
            if not self.active_host or self.navigation_generation != origin:
                return False
        if identity is not None and hasattr(self.cloud_client, 'resolve_remote'):
            remote = self.cloud_client.resolve_remote(remote, identity)
        if remote in self.loaded_remote_names() and identity is None:
            return True
        client, generation = self.cloud_client, getattr(self.cloud_client, 'generation', None)
        try:
            current = await asyncio.to_thread(client.connection_identity, remote)
        except (OSError, ValueError, AttributeError):
            current = None
        if (not self.active_host or self.navigation_generation != origin or client is not self.cloud_client
                or generation != getattr(client, 'generation', None)):
            return False
        if current is not None and (identity is None or current == identity):
            return True
        return self.require_remote_credentials(remote, identity=identity, resume=resume, checked=True)

    def require_remote_credentials(self, remote, *, identity=None, resume=None, checked=False):
        """Return immediately when loaded; otherwise present the matching ZIP unlock."""
        if identity is not None and hasattr(self.cloud_client, 'resolve_remote'):
            remote = self.cloud_client.resolve_remote(remote, identity)
        loaded = self.loaded_remote_names()
        if remote in loaded and identity is None:
            return True
        if not checked:
            try:
                current = self.cloud_client.connection_identity(remote)
                if identity is None or current == identity:
                    return True
            except (OSError, ValueError, AttributeError):
                pass
        try:
            cache = self.retained_packages()
            matches = [(key, item) for key, item in cache.matching(remote, identity)
                       if self.legacy_name_visible(item['zip'], prefix='legacy')] if cache else []
        except (OSError, ValueError) as error:
            self.cloud_status.value = str(error)
            matches = []
        if len(matches) == 1:
            self.show_retained_unlock(matches[0][0], remote, identity=identity, resume=resume)
        elif matches:
            box = toga.Box(style=Pack(direction=COLUMN, margin=16))
            box.add(toga.Label('Choose credential ZIP'))
            for key, item in matches:
                def choose(widget=None, selected=key, **kwargs):
                    self.show_retained_unlock(selected, remote, identity=identity, resume=resume)
                box.add(toga.Button(item['zip'], on_press=choose, style=Pack(height=44)))
            self.show_view(box, destination='files', route='choose-credential', title='Unlock connection')
        else:
            self.show_cloud_connections()
            self.cloud_import_message.text = import_hint('Load the credential ZIP for ' + remote + '. Retained password-protected ZIPs need their ZIP password to unlock again.')
        return False

    def show_retained_unlock(self, key, remote=None, *, identity=None, resume=None, destination='files', choices=None):
        cache = self.retained_packages()
        password = self.credential_unlock_password = PasswordInput(placeholder='ZIP password', style=Pack(height=44))
        status = self.credential_unlock_status = toga.Label('')
        selector = None
        if choices:
            labels = {item['zip']: candidate for candidate, item in choices}
            selector = toga.Selection(items=list(labels), style=Pack(height=44))
            selector.on_change = lambda widget, **kw: setattr(password, 'value', '')
        async def unlock(widget=None, **kwargs):
            selected = labels[selector.value] if selector is not None else key
            if self.cloud_busy or getattr(self, 'transfer_busy', False):
                return
            secret = password.value
            password.value = ''
            self.set_cloud_busy(True)
            ready = False
            try:
                if not self.clear_private_reader():
                    raise ValueError('Save or discard private edits before unlocking another credential.')
                self.clear_private_catalog()
                names = await asyncio.to_thread(self.cloud_client.import_package, cache, selected, secret, remember=False)
                await self._load_crypt_remote_names()
                self.set_loaded_remote_names(self.visible_remote_names(names))
                checked_remote = self.cloud_client.resolve_remote(remote, identity) if remote is not None and identity is not None and hasattr(self.cloud_client, 'resolve_remote') else remote
                if checked_remote is not None and (checked_remote not in names or (identity is not None
                        and await asyncio.to_thread(self.cloud_client.connection_identity, checked_remote) != identity)):
                    raise ValueError('This ZIP does not match the folder connection.')
                self.remember_loaded_packages(cache.items[selected]['zip'], names, session_only=True)
                self.cloud_package.text = self.loaded_package_label()
                self.app.credential_document_lists.refresh()
                self.cloud_status.value = 'Credential ZIP unlocked for this app session. Its open and recent file lists are restored.'
                ready = True
            except (OSError, ValueError) as error:
                status.text = import_hint('Unlock failed: ' + str(error)[:160])
            finally:
                secret = None
                self.set_cloud_busy(False)
            if ready:
                self.routes.back()
                if resume is not None:
                    import inspect
                    result = resume()
                    if inspect.isawaitable(result):
                        await result
        visible_remotes = self.rclone_ui.visible_remotes
        password.on_confirm = unlock
        self.credential_unlock_button = toga.Button('Unlock', on_press=unlock, style=Pack(height=44))
        box = toga.Box(children=[toga.Label('Choose credential' if choices else import_hint('Unlock ' + cache.items[key]['zip']), style=Pack(font_size=18)),
            *([selector] if selector is not None else []),
            toga.Label(import_hint('Its ZIP is retained on this device. The password is needed for this session and is never saved.')),
            password, self.credential_unlock_button, status,
            toga.Button('Cancel', on_press=lambda widget, **kw: self.routes.back(), style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=16))
        self.show_view(box, destination=destination, route='unlock-credential', title='Unlock credential')

    async def restore_cloud(self, widget=None, *, initial=False, **kwargs):
        if (self.cloud_busy and not initial) or self.cloud_client is None:
            return
        if not initial and not self.clear_private_reader():
            return
        if not initial:
            self.set_cloud_busy(True)
        self._cloud_restore_error = ''
        try:
            # Initial restore has no old credential state to retire. Home and
            # ordinary local browsers may already be in use while it runs.
            if not initial:
                self.clear_private_catalog()
            names = await asyncio.to_thread(self.cloud_client.restore)
            if not self.active_host:
                return
            await self._load_crypt_remote_names()
            visible_remotes = self.rclone_ui.visible_remotes
            self.set_loaded_remote_names(self.visible_remote_names(names))
            if names and self.cloud_client.package_name:
                self.remember_loaded_packages(self.cloud_client.package_name, names, session_only=False)
            self._cloud_restored = True
            self._publish_restored_connections(names)
        except Exception:
            self._cloud_restore_error = 'Saved credentials are unavailable. Unlock the device and reload, or forget saved credentials to import again.'
            if hasattr(self, 'cloud_status'):
                self.cloud_status.value = self._cloud_restore_error
        finally:
            self.set_cloud_busy(False)

    def _publish_restored_connections(self, names):
        if not hasattr(self, 'cloud_view'):
            return
        self.cloud_entries.items = []
        self.cloud_rows = {}
        self.cloud_open_remote = None
        self.cloud_location.value = self.cloud_path = ''
        self.cloud_package.text = self.loaded_package_label()
        if self.cloud_pending_zip is None and names:
            saved = [item['package_name'] for item in getattr(self.cloud_client, 'package_records', ()) if item['saved']]
            self.cloud_selected_zip.text = import_hint('Saved packages: ' + ', '.join(saved) if saved else 'Loaded ZIP: ' + (self.cloud_client.package_name or 'saved package'))
            self.cloud_import_message.text = import_hint('Loaded remotes are ready. Open Workspaces or Browse remote files to choose a remote, then tap Browse folder.\nChoose another ZIP to add another credential package.')
        self.cloud_status.value = (f'{len(names)} total remote(s) available. Saved packages reloaded; active session-only packages were kept.'
                                   if names else 'No saved credential package. Import a ZIP to get started.')

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

    async def choose_cloud_package(self, widget=None, **kwargs):
        pick_document = self.rclone_ui.pick_document
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            selected = await pick_document(self)
            if selected is None:
                self.cloud_import_message.text = import_hint('ZIP selection cancelled. Your loaded remotes are unchanged.')
                return
            package = await asyncio.to_thread(SelectedCredentialZIP, *selected)
            self.cloud_pending_zip = package
            self.cloud_selected_zip.text = import_hint('Selected ZIP: ' + package.name)
            self.cloud_import_message.text = import_hint('Enter the ZIP password, then tap Load remotes (or Return).\nLeave it blank for an unencrypted ZIP.')
        except Exception as error:
            self.cloud_import_message.text = import_hint('Could not select ZIP: ' + str(error)[:150])
        finally:
            self.set_cloud_busy(False)

    async def import_cloud_package(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        # Retain the direct-call API for native validation clients; the visible
        # Load remotes button is enabled only after Choose ZIP succeeds.
        if self.cloud_pending_zip is None:
            if widget is not None:
                self.cloud_import_message.text = import_hint('Tap Choose credential ZIP first, then enter its password and tap Load remotes.')
                return
            await self.choose_cloud_package()
            if self.cloud_pending_zip is None:
                return
        password = self.cloud_password.value
        self.cloud_password.value = ''
        selected = self.cloud_pending_zip
        self.set_cloud_busy(True)
        self.cloud_import_message.text = 'Loading remotes…'
        try:
            if not self.clear_private_reader():
                self.cloud_import_message.text = import_hint('Save or discard your private edits before loading another package.')
                return
            self.clear_private_catalog()
            names = await asyncio.to_thread(self.cloud_client.import_package, selected, None, password, remember=self.cloud_remember.value)
            await self._load_crypt_remote_names()
            visible_remotes = self.rclone_ui.visible_remotes
            self.remember_loaded_packages(selected.name, names, session_only=not self.cloud_remember.value)
            cache_error = ''
            if not self.cloud_remember.value:
                try:
                    cache = self.retained_packages()
                    if cache is not None:
                        identities = {remote: self.cloud_client.connection_identity(remote) for remote in self.visible_remote_names(self.package_remote_names(selected.name, names))}
                        aliases = next((item.get('aliases', {}) for item in getattr(self.cloud_client, 'package_records', ()) if item['package_name'] == selected.name), {})
                        aliases = {name: alias for name, alias in aliases.items() if alias in identities}
                        metadata = {'aliases': aliases} if aliases else {}
                        crypt = set(self.cloud_crypt_remotes) & set(identities)
                        if crypt:
                            metadata['crypt_remotes'] = sorted(crypt)
                        await asyncio.to_thread(cache.remember, selected, identities, **metadata)
                except (OSError, ValueError) as error:
                    cache_error = ' ZIP not retained; select it again next time. ' + str(error)[:120]
            self.set_loaded_remote_names(self.visible_remote_names(names))
            self.cloud_package.text = self.loaded_package_label()
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_pending_zip = None
            self.cloud_selected_zip.text = import_hint('Loaded ZIP: ' + selected.name)
            self.cloud_import_message.text = import_hint(f'{len(names)} total remote(s) available. Open Workspaces or Browse remote files to choose a remote, then tap Browse folder.' + cache_error)
            self.app.credential_document_lists.refresh()
            self.cloud_status.value = f'{selected.name} loaded ({"saved" if self.cloud_remember.value else "session only"}). {len(names)} total remote(s) available. Open Workspaces to browse. No connection has been made yet.'
        except CredentialBusyError as error:
            self.cloud_status.value = str(error)
            self.cloud_import_message.text = import_hint(str(error))
        except Exception as error:
            self.cloud_status.value = 'Import failed: ' + str(error)[:300]
            self.cloud_import_message.text = import_hint('Could not load ZIP. Check the password and tap Load remotes again.\n' + str(error)[:150])
        finally:
            password = None
            self.set_cloud_busy(False)

    async def browse_cloud(self, widget=None, *, preserve_path=False, **kwargs):
        with self.remote_browser.population_paused():
            if self.cloud_busy:
                return
            if self.cloud_client is None or not self.selected_cloud_remote():
                self.cloud_status.value = 'Choose a remote first. Use Manage connections to load your remotes.'
                return False
            remote, folder = self.selected_cloud_remote(), self.cloud_location.value.strip('/')
            if not preserve_path and self.cloud_open_remote and remote != self.cloud_open_remote:
                folder = ''
                self.cloud_location.value = ''
            previous_rows = self.cloud_rows
            previous_selected = self.cloud_entries.value
            previous_labels = [item.value for item in self.cloud_entries.items]
            generation = getattr(self.cloud_client, 'generation', 0)
            self.cloud_status.value = f'Opening {remote}:{folder}…'
            self.remote_read_busy = True
            self.set_cloud_busy(True)
            self.cloud_rows = {}
            self.cloud_entries.items = []
            try:
                async with self.remote_activity(f'Listing {remote}:{folder or "/"}') as progress:
                    rows = await asyncio.to_thread(self.cloud_client.entries, remote, folder)
                    progress(f'Displaying {len(rows)} items from {remote}:{folder or "/"}')
                    await asyncio.sleep(0)
                    if getattr(self.cloud_client, 'generation', 0) != generation:
                        raise ValueError('Credentials changed while browsing. Reopen the remote.')
                    self.cloud_rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                                       for index, row in enumerate(rows)}
                    self.cloud_entries.items = list(self.cloud_rows)
                    self.cloud_open_remote, self.cloud_path = remote, folder
                    from pathlib import Path
                    from types import SimpleNamespace
                    from commonUtils.runtime.resource_provider import resource_path
                    root = Path('/remote') / remote
                    provider = SimpleNamespace(root=root, remote=remote, relative=lambda path: resource_path(str(Path(path).relative_to(root)) if Path(path).is_absolute() else path))
                    # Online browsing must never open every archive just to fetch covers.
                    self.remote_browser.closed = False
                    self.remote_browser.thumbnail = None
                    self.remote_browser.set_entries(provider, folder, [dict(row, name=Path(row['path']).name, modified='') for row in rows], location=(remote, folder))
                    self.remote_browser.location_bar.update(folder, remote=True,
                        encrypted=remote in self.cloud_crypt_remotes, unlocked=True,
                        session_only=any(remote in record.get('remotes', ()) and not record.get('saved', False)
                                         for record in getattr(self.cloud_client, 'package_records', ())),
                        name=Path(folder).name if folder else remote)
                self.rclone_ui.record_folder(self.cloud_view, self.remote_browser, 'remote-browser', remote, folder,
                                             self.browser_cloud_location)
                self.cloud_status.value = ''
                return True
            except Exception as error:
                self.cloud_status.value = 'Browse failed: ' + str(error)[:300]
                if self.remote_browser.tree is not None and getattr(self.cloud_client, 'generation', 0) == generation:
                    self.cloud_remote.value, self.cloud_location.value = self.cloud_open_remote, self.cloud_path
                    self.cloud_rows = previous_rows
                    self.cloud_entries.items = previous_labels
                    if previous_selected in previous_labels:
                        self.cloud_entries.value = previous_selected
                else:
                    self.remote_browser.stop()
                    self.cloud_rows = {}
                    self.cloud_entries.items = []
                    self.cloud_open_remote = None
                    self.cloud_location.value = self.cloud_path = ''
                return False
            finally:
                self.set_cloud_busy(False)
                self.remote_read_busy = False

    async def parent_cloud(self, widget=None, **kwargs):
        if not self.cloud_path:
            self.show_locations()
            return
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
        self.cloud_status.value = ('Selected folder: ' if row['directory'] else 'Selected file: ') + row['path']

    async def browser_cloud_folder(self, row):
        if self.cloud_busy:
            return False
        return await self.browser_cloud_location((self.cloud_open_remote, row['path']))

    async def browser_cloud_location(self, location):
        if not self.app.routes.folders.restoring:
            self.app.routes.folders.capture()
        if self.cloud_busy:
            return False
        self.cloud_remote.value, self.cloud_location.value = location
        return await self.browse_cloud(preserve_path=True)

    async def open_cloud_folder(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if self.cloud_busy:
            return
        if not row or not row['directory']:
            self.cloud_status.value = 'Select a folder in the list above, then tap Open selected folder.'
            return False
        if self.selected_cloud_remote() != self.cloud_open_remote:
            self.cloud_status.value = 'The remote changed. Tap Browse folder to open it first.'
            return False
        self.cloud_location.value = row['path']
        return await self.browse_cloud()

    async def open_remote_document(self, row=None, **kwargs):
        if self.cloud_busy:
            await explain_remote_busy(self)
            return False
        row = row if isinstance(row, dict) else self.cloud_rows.get(self.cloud_entries.value)
        if not row or row['directory']:
            return False
        if self.selected_cloud_remote() != self.cloud_open_remote:
            self.cloud_status.value = 'The remote changed. Browse the folder again before opening this file.'
            return False
        from features.rclone.remote_policy import direct_kind, LocalCopyRequired, LOCAL_COPY_MESSAGE
        try:
            direct_kind(row['path'], row.get('size', -1))
            if not getattr(self.cloud_client, 'supports_streaming', False):
                raise LocalCopyRequired()
        except LocalCopyRequired:
            await self.main_window.dialog(toga.InfoDialog('Local copy required', LOCAL_COPY_MESSAGE))
            return False
        opening = 'Opening remote file: ' + row['path'] + '…'
        self.show_cloud(present=False)
        self.cloud_status.value = opening
        try:
            from features.rclone.mobile.remote_readers import RemoteReaders
            async with self.remote_activity(opening) as progress:
                opened = await self.open_crypt(
                    copies=RemoteReaders(self.cloud_client, self.cloud_open_remote, progress=progress),
                    key=row['path'])
        except Exception as error:
            # Session setup can fail before the provider reader's error handler.
            self.cloud_status.value = 'Remote opening failed: ' + str(error)[:300]
            await self.main_window.dialog(toga.InfoDialog('Remote preview unavailable',
                str(error)[:200] + '\n\n' + LOCAL_COPY_MESSAGE))
            return False
        if opened:
            self.cloud_status.value = 'Opened remote file: ' + row['path']
        elif self.cloud_status.value.startswith((opening, 'Checking remote', 'Reading remote', 'Preparing remote')):
            self.cloud_status.value = 'The reader could not open this file. Return to Workspaces and try again.'
        return bool(opened)

    def cancel_cloud(self, widget=None, **kwargs):
        if getattr(self, '_crypt_cancel', None) is not None:
            self._crypt_cancel.set()
        for owner in getattr(getattr(self, 'private_sessions', None), 'controllers', {}).values():
            if owner.operation_busy and owner._crypt_cancel is not None:
                owner._crypt_cancel.set()
        if self.cloud_client:
            self.cloud_client.cancel()
            if hasattr(self, 'cloud_status'):
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
            self.set_loaded_remote_names([])
            self.cloud_entries.items = []
            self.cloud_rows = {}
            self.cloud_open_remote = None
            self.cloud_password.value = ''
            self.cloud_pending_zip = None
            self.cloud_selected_zip.text = 'No ZIP selected'
            self.cloud_import_message.text = import_hint('Choose a ZIP, then enter its password and tap Load remotes.')
            self.cloud_package.text = 'Credential package: none'
            cache = self.retained_packages()
            if cache is not None:
                cache.forget()
            self.preferences.save(remote_packages='[]')
            self.session_credential_packages = []
            self.app.credential_document_lists.forget_memory()
            from .document_lists import forget_cache
            forget_cache(self.app.credential_document_lists.root)
            self.cloud_status.value = 'Saved and session credentials and encrypted document lists forgotten. Private downloads remain available.'
        except Exception:
            self.cloud_status.value = 'Could not forget the protected credentials. Unlock the device and retry.'
        finally:
            self.set_cloud_busy(False)

    def refresh_downloads(self, selected=None):
        self.download_labels = {f'{i + 1}. {path.name}': path for i, path in enumerate(self.downloads.items())}
        self.download_selector.items = list(self.download_labels)
        if selected:
            self.download_selector.value = next(key for key, path in self.download_labels.items() if path == selected)

    async def open_download(self, widget=None, *, path=None, destination=None, **kwargs):
        selected = path if path is not None else self.download_labels.get(self.download_selector.value)
        if selected is None:
            return False
        with self.rclone_ui.opening_status(dict(path=str(selected)), destination=destination):
            await asyncio.sleep(0)
            return await self._open_download(path=selected, destination=destination)

    async def _open_download(self, *, path, destination=None):
        from commonUtils.runtime.document_access import LocalDocuments
        destination = destination or self.native_host.state.destination
        if not hasattr(self, 'cloud_view'):
            self.show_cloud(present=False)
        selected = path if path is not None else self.download_labels.get(self.download_selector.value)
        selected = Path(selected) if selected is not None else None
        if selected is not None and Path(selected).suffix.lower() == '.pdf':
            from features.pdf.mobile.copies import PDFCopies
            from commonUtils.runtime.local_files import LocalFiles
            selected = Path(selected)
            return await self.open_crypt(copies=PDFCopies(LocalFiles(selected.parent)), key=selected.name, destination=destination)
        independent = (self.cloud_busy and path is not None
                       and selected.resolve().is_relative_to((collection_path(self.private_root)).resolve()))
        if (self.cloud_busy and not independent) or selected is None:
            return False
        if not independent:
            self.set_cloud_busy(True)
        try:
            ResourceImports = self.rclone_ui.ResourceImports
            collection_root = (None if Path(selected).resolve().is_relative_to(Path(self.private_root).resolve())
                               else collection_path(self.private_root).resolve())
            if (not hasattr(self, 'resource_imports')
                    or self.resource_imports.collection_root != collection_root):
                self.resource_imports = ResourceImports(self.private_root, collection_root=collection_root)
            imported = self.resource_imports.find(selected)
            def remember_folder(provider, resource):
                if not hasattr(self.app, '_document_folder_sources'):
                    self.app._document_folder_sources = {}
                self.app._document_folder_sources[provider, resource] = dict(type='local', path=str(selected))
            if imported is not None:
                remember_folder(imported['provider'], imported['resource'])
                if imported['provider'] == 'library':
                    return await self.open_book(imported['resource'], destination=destination)
                elif self.open_document(imported['resource']):
                    self.show_documents(resume=True, destination=destination)
                else:
                    raise ValueError('The imported copy is unavailable; its index and source were preserved.')
                return True
            if selected.suffix.lower() in {'.epub', '.cbz', '.zip'}:
                catalog = self.reader_manager().catalog
                generation = self.navigation_generation
                record = await asyncio.to_thread(catalog.library_store.import_book, LocalDocuments(), selected)
                self.resource_imports.remember(selected, 'library', record['id'])
                remember_folder('library', record['id'])
                if not self.active_host or self.navigation_generation != generation:
                    return False
                self.refresh_library()
                return await self.open_book(record['id'], destination=destination)
            else:
                generation = self.navigation_generation
                doc = await asyncio.to_thread(self.store.import_document, LocalDocuments(), selected)
                self.resource_imports.remember(selected, 'managed-text', doc.id)
                remember_folder('managed-text', doc.id)
                self.refresh_documents()
                if not self.active_host or self.navigation_generation != generation:
                    return False
                if not self.open_document(doc.id):
                    return False
                self.show_documents(destination=destination)
                return True
        except Exception as error:
            self.cloud_status.value = 'Open failed: ' + str(error)[:300]
            if independent:
                self.file_status.value = self.cloud_status.value
                readers = getattr(self, 'readers', None)
                if readers is not None and readers.active is not None:
                    readers.active.book_status.text = self.cloud_status.value
            return False
        finally:
            if not independent:
                self.set_cloud_busy(False)

    async def export_download(self, widget=None, **kwargs):
        export_file = self.rclone_ui.export_file
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
