"""Native read-only remote browser and access to existing offline copies."""
from commonUtils.ui.native.password_input import PasswordInput
from features.rclone.mobile.storage_location import collection_path
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from features.rclone.mobile.cloud import CloudClient, CredentialBusyError, Downloads, PACKAGE_LIMIT, download_name
from features.rclone.localcrypt.mobile.ui import LocalCryptUI


from features.rclone.mobile.messages import import_hint
from .credentials_ui import CredentialWorkflow, SelectedCredentialZIP


async def explain_remote_busy(app):
    transferring = getattr(app, 'transfer_busy', False)
    message = ('Cloud previews are unavailable while a transfer is running. Wait for the transfer to finish, or open a Local copy.'
               if transferring else 'The connection is busy. Wait for the current request to finish, then open the file again.')
    app.cloud_status.value = message
    await app.main_window.dialog(toga.InfoDialog('Transfer in progress' if transferring else 'Connection busy', message))




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
            self.cloud_connections_status = ui.settings.note(error)
            self.cloud_import_entry = toga.Button('Import credential ZIP…', on_press=self.begin_cloud_import, style=Pack(height=48))
            troubleshooting, self.cloud_settings_toggle = ui.settings.disclosure('Advanced & troubleshooting', [
                ui.settings.group([self.cloud_reload, self.cloud_probe, self.cloud_clear])])
            self.cloud_connections_view = ui.settings.page('rclone connections',
                'Your cloud storage, ready when you need it.', [
                    ui.settings.heading('CREDENTIAL PACKAGES'), self.cloud_retained_box,
                    self.cloud_import_entry, ui.settings.note('Import a package exported from Logistics desktop.'),
                    ui.settings.heading('SESSION'), ui.settings.group([self.cloud_lock]),
                    ui.settings.note('Lock to stop access until you unlock again. This also locks SMB connections.'),
                    troubleshooting, self.cloud_connections_status])
            self.cloud_import_view = ui.settings.page('Import credential ZIP',
                'Choose your Logistics credential package.', [
                    self.cloud_choose, self.cloud_selected_zip,
                    ui.settings.group([ui.settings.field('ZIP password (if encrypted)', self.cloud_password)]),
                    self.cloud_import, self.cloud_import_message,
                    ui.settings.heading('STORAGE'), ui.settings.group([self.cloud_remember]),
                    ui.settings.note('Off keeps decoded credentials in memory. Password-protected ZIPs are retained encrypted for future unlocking. The ZIP password is never saved.')])
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
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.refresh_retained_credentials()

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
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return await workflow._load_crypt_remote_names()

    def retained_packages(self):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.retained_packages()

    def remember_credential_association(self, name, remotes, *, session_only):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.remember_credential_association(name, remotes, session_only=session_only)

    def visible_remote_names(self, names):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.visible_remote_names(names)

    def package_remote_names(self, label, fallback):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.package_remote_names(label, fallback)

    def remember_loaded_packages(self, label, names, *, session_only):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.remember_loaded_packages(label, names, session_only=session_only)

    def loaded_package_label(self):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.loaded_package_label()

    def credential_groups(self, choices=None):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.credential_groups(choices)

    def home_unlock_candidates(self):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.home_unlock_candidates()

    def show_home_unlock(self, widget=None, **kwargs):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.show_home_unlock(widget, **kwargs)

    def retained_credential_associations(self):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.retained_credential_associations()

    async def require_remote_credentials_async(self, remote, *, identity=None, resume=None):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return await workflow.require_remote_credentials_async(remote, identity=identity, resume=resume)

    def require_remote_credentials(self, remote, *, identity=None, resume=None, checked=False):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.require_remote_credentials(remote, identity=identity, resume=resume, checked=checked)

    def show_retained_unlock(self, key, remote=None, *, identity=None, resume=None, destination='files', choices=None):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow.show_retained_unlock(key, remote, identity=identity, resume=resume, destination=destination, choices=choices)

    async def restore_cloud(self, widget=None, *, initial=False, **kwargs):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return await workflow.restore_cloud(widget, initial=initial, **kwargs)

    def _publish_restored_connections(self, names):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return workflow._publish_restored_connections(names)

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
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return await workflow.choose_cloud_package(widget, **kwargs)

    async def import_cloud_package(self, widget=None, **kwargs):
        workflow = getattr(self, 'credential_workflow', None) or CredentialWorkflow(self)
        return await workflow.import_cloud_package(widget, **kwargs)

    async def browse_cloud(self, widget=None, *, preserve_path=False, **kwargs):
        return await self.browser_workflow.browse(self.cloud_client, self.selected_cloud_remote(),
            self.cloud_location.value.strip('/'), preserve_path=preserve_path)

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
        return self.download_workflow.refresh_downloads(selected)

    async def open_download(self, widget=None, *, path=None, destination=None, **kwargs):
        return await self.download_workflow.open_download(widget, path=path, destination=destination, **kwargs)

    async def _open_download(self, *, path, destination=None):
        return await self.download_workflow._open_download(path=path, destination=destination)

    async def export_download(self, widget=None, **kwargs):
        return await self.download_workflow.export_download(widget, **kwargs)


class CloudBrowserPresentation:
    """Translate browser effects to existing controls and navigation callbacks."""
    def __init__(self, cloud):
        self.cloud = cloud

    def population_paused(self):
        return self.cloud.remote_browser.population_paused()

    def busy(self):
        return self.cloud.cloud_busy

    def selection(self):
        entries = self.cloud.cloud_entries
        return [item.value for item in entries.items], entries.value

    def location(self, remote, folder):
        if remote is not None:
            self.cloud.cloud_remote.value = remote
        self.cloud.cloud_location.value = folder

    def status(self, message):
        self.cloud.cloud_status.value = message

    def set_busy(self, value):
        self.cloud.set_cloud_busy(value)

    def labels(self, labels, selected=None):
        self.cloud.cloud_entries.items = labels
        if selected in labels:
            self.cloud.cloud_entries.value = selected

    def activity(self, stage):
        return self.cloud.remote_activity(stage)

    def current(self, client, generation):
        return (self.cloud.active_host and self.cloud.cloud_client is client
                and getattr(client, 'generation', 0) == generation)

    def has_listing(self):
        return self.cloud.remote_browser.tree is not None

    def publish(self, rows, remote, folder):
        from types import SimpleNamespace
        from commonUtils.runtime.resources.paths import resource_path
        cloud = self.cloud
        root = Path('/remote') / remote
        provider = SimpleNamespace(root=root, remote=remote, relative=lambda path:
            resource_path(str(Path(path).relative_to(root)) if Path(path).is_absolute() else path))
        # Online browsing must not open archives to fetch covers.
        cloud.remote_browser.closed = False
        cloud.remote_browser.thumbnail = None
        cloud.remote_browser.set_entries(provider, folder,
            [dict(row, name=Path(row['path']).name, modified='') for row in rows], location=(remote, folder))
        cloud.remote_browser.location_bar.update(folder, remote=True,
            encrypted=remote in cloud.cloud_crypt_remotes, unlocked=True,
            session_only=any(remote in record.get('remotes', ()) and not record.get('saved', False)
                             for record in getattr(cloud.cloud_client, 'package_records', ())),
            name=Path(folder).name if folder else remote)

    def record(self, remote, folder):
        cloud = self.cloud
        cloud.rclone_ui.record_folder(cloud.cloud_view, cloud.remote_browser, 'remote-browser',
                                     remote, folder, cloud.browser_cloud_location)

    def stop(self):
        self.cloud.remote_browser.stop()
