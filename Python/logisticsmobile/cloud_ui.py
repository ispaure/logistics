"""Native remote-file browser and private downloads; no remote mutations."""
import asyncio
from contextlib import contextmanager
from io import BytesIO
from textwrap import fill
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .cloud import CloudClient, Downloads, PACKAGE_LIMIT, download_name
from .localcrypt_ui import LocalCryptUI
from .copy_ui import CopyUI


def import_hint(text):
    # Toga's native Label is single-line by default. Explicit short lines
    # keep the next action visible on narrow phones without clipping.
    return '\n'.join(fill(line, width=38) for line in text.splitlines())


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


class CloudUI(CopyUI, LocalCryptUI):
    def show_cloud(self, widget=None, *, present=True, **kwargs):
        if not hasattr(self, 'cloud_view'):
            self.cloud_busy = False
            self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_crypt_remotes = set()
            self.downloads = Downloads(self.private_root / 'Downloads')
            self.cloud_client = getattr(self, 'cloud_client', None)
            error = ''
            if self.cloud_client is None:
                try:
                    from .credential_vault import ProtectedVault
                    self.cloud_client = CloudClient(vault=ProtectedVault.for_app(self))
                except Exception:
                    error = 'The native remote engine or device credential protection is unavailable.'
            self.cloud_pending_zip = None
            self.cloud_add_smb = toga.Button('Add SMB / Mac share…', on_press=self.show_smb_connection, style=Pack(height=44))
            self.cloud_choose = toga.Button('Choose credential ZIP…', on_press=self.choose_cloud_package, style=Pack(height=44))
            self.cloud_selected_zip = toga.Label('No ZIP selected', style=Pack(font_size=14))
            self.cloud_import_message = toga.Label(import_hint('Choose a ZIP, then enter its password and tap Load remotes.'), style=Pack(font_size=14))
            self.cloud_password = toga.PasswordInput(placeholder='ZIP password (if encrypted)', on_confirm=self.import_cloud_package, style=Pack(flex=1, height=44))
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
            self.cloud_up = toga.Button('Parent folder', on_press=self.parent_cloud, style=Pack(flex=1, height=44))
            self.cloud_entries = toga.Selection(style=Pack(height=44))
            from .browser_ui import FileBrowser as NativeBrowser
            self.remote_browser = NativeBrowser(folder_visible=self.folder_path_visible, selected=self.browser_cloud_selected, open_folder=self.browser_cloud_folder, navigate=self.browser_cloud_location)
            self.cloud_open = toga.Button('Open folder', on_press=self.open_cloud_folder, style=Pack(height=44))
            self.cloud_download = toga.Button('Download private copy', on_press=self.download_cloud, style=Pack(height=44))
            self.cloud_download_help = toga.Label('', style=Pack(font_size=14))
            self.cloud_downloaded_folder = None
            self.cloud_folder_open = toga.Button('Open downloaded folder', on_press=self.open_downloaded_folder,
                                                enabled=False, style=Pack(height=44))
            self.cloud_cancel = toga.Button('Cancel request', on_press=self.cancel_cloud, style=Pack(height=44))
            self.cloud_clear = toga.Button('Forget saved credentials', on_press=self.clear_cloud, style=Pack(height=44))
            self.cloud_status = toga.MultilineTextInput(value=error or 'Choose saved or session-only credentials, then import a ZIP. Its password is never saved.',
                                                       readonly=True, style=Pack(height=72))
            self.download_selector = toga.Selection(style=Pack(height=44))
            self.download_open = toga.Button('Open private copy', on_press=self.open_download, style=Pack(flex=1, height=44))
            self.download_export = toga.Button('Export private copy…', on_press=self.export_download, style=Pack(flex=1, height=44))
            self.cloud_connections_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
                toga.Label('Remote connections', style=Pack(font_size=22)),
                self.cloud_add_smb,
                self.cloud_choose, self.cloud_selected_zip, self.cloud_import_message,
                toga.Box(children=[self.cloud_password, self.cloud_import], style=Pack(direction=ROW)),
                self.cloud_remember, toga.Label('Off: use credentials only for this app session.'),
                self.cloud_package, self.cloud_reload, self.cloud_probe, self.cloud_clear,
                toga.Button('Browse remote files', on_press=self.show_cloud, style=Pack(height=44))],
                style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            self.cloud_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
                toga.Label('Remote files', style=Pack(font_size=22)),
                toga.Button('Manage connections…', on_press=self.show_cloud_connections, style=Pack(height=44)),
                self.cloud_remote_heading, self.cloud_remote, self.cloud_remote_help,
                self.cloud_location, toga.Box(children=[self.cloud_browse, self.cloud_up], style=Pack(direction=ROW)),
                self.cloud_status, self.cloud_cancel, self.remote_browser.widget,
                self.cloud_open, self.cloud_download_help, self.cloud_download, self.cloud_folder_open,
                toga.Label('Downloaded copies', style=Pack(font_size=18, margin_top=12)), self.download_selector,
                toga.Box(children=[self.download_open, self.download_export], style=Pack(direction=ROW)),
                *self.build_localcrypt()], style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
            self.cloud_advanced_view = self.cloud_view
            advanced = self.cloud_advanced_view.content
            for control in (self.cloud_remote, self.cloud_status, self.remote_browser.widget,
                            self.cloud_open, self.cloud_download, self.cloud_folder_open, self.cloud_cancel, self.cloud_browse):
                advanced.remove(control)
            from commonUtils.ui.native.presentation import scroll_content
            from .action_menu import FeatureCommands
            self.cloud_actions_button = toga.Button('•••', style=Pack(width=44, height=44))
            self.cloud_actions = FeatureCommands(self.cloud_actions_button, self, [
                ('Browse path…', self.show_cloud_actions),
                ('Pin current folder', self.pin_remote_folder),
                ('Downloaded copies…', self.show_cloud_actions), ('Encrypted offline copies…', self.show_cloud_actions),
                ('Manage connections…', self.show_cloud_connections)], self.show_cloud_actions)
            self.cloud_download.style.flex = self.cloud_open.style.flex = 1
            advanced.add(self.cloud_remote)
            advanced.add(self.cloud_browse)
            advanced.add(self.cloud_download)
            advanced.add(self.cloud_folder_open)
            advanced.insert(advanced.children.index(self.cloud_location) + 1,
                toga.Button('Browse folder', on_press=self.browse_cloud_path, style=Pack(height=44)))
            self.cloud_copy_button = toga.Button('Copy to device…', on_press=self.choose_cloud_copy, style=Pack(height=48))
            self.cloud_copy_folder = toga.Button('Copy this folder…', on_press=self.copy_current_folder, style=Pack(height=48))
            self.cloud_locations = toga.Button('Folder Hub', on_press=self.show_locations, style=Pack(height=44, flex=1))
            self.cloud_remote.style.flex = 1
            self.cloud_browse.text = 'Open remote'
            self.cloud_cancel.text = 'Cancel'
            self.cloud_status.style.height = 40
            self.cloud_status.style.font_size = 12
            self.cloud_transfer_progress = toga.ProgressBar(max=100, value=0, style=Pack(height=12))
            advanced.add(self.cloud_copy_folder)
            self.cloud_view = toga.Box(children=[
                toga.Box(children=[self.cloud_locations, self.cloud_actions_button], style=Pack(direction=ROW)),
                self.cloud_status,
                self.cloud_transfer_progress,
                toga.ScrollContainer(horizontal=False, content=scroll_content(self.remote_browser.widget), style=Pack(flex=1)),
                self.cloud_copy_button,
                self.cloud_cancel],
                style=Pack(direction=COLUMN, margin=12, flex=1))
            self.refresh_downloads()
            self.set_cloud_busy(False)
            if self.cloud_client is not None and getattr(self.cloud_client, 'vault', None) is not None:
                self.set_cloud_busy(True)
                self.cloud_restore_task = self.loop.create_task(self.restore_cloud(initial=True))
        if present:
            self.show_view(self.cloud_view, destination='files', route='remote-browser', title='Remote file browser')

    async def browse_cloud_path(self, widget=None, **kwargs):
        if await self.browse_cloud(preserve_path=True):
            self.show_cloud()

    def show_cloud_actions(self, widget=None, **kwargs):
        if not self.cloud_busy:
            self.show_view(self.cloud_advanced_view, destination='files', route='remote-actions', title='Remote actions')

    def show_cloud_connections(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        self.show_view(self.cloud_connections_view, destination='settings', route='connections', title='Remote connections')

    def show_smb_connection(self, widget=None, **kwargs):
        self.show_cloud(present=False)
        if self.cloud_busy:
            return
        if not hasattr(self, 'smb_view'):
            self.smb_name = toga.TextInput(placeholder='Connection name (e.g. Home Mac)', style=Pack(height=44))
            self.smb_host = toga.TextInput(placeholder='Server IP or hostname (e.g. 192.168.1.10)', style=Pack(height=44))
            self.smb_user = toga.TextInput(placeholder='Username (or guest)', style=Pack(height=44))
            self.smb_password = toga.PasswordInput(placeholder='Share password', style=Pack(height=44))
            self.smb_domain = toga.TextInput(value='WORKGROUP', style=Pack(height=44))
            self.smb_port = toga.TextInput(value='445', style=Pack(height=44))
            self.smb_remember = toga.Switch('Save credentials on this device', value=True, style=Pack(height=44))
            self.smb_status = toga.Label('', style=Pack(font_size=12))
            self.smb_connect = toga.Button('Add connection and browse', on_press=self.connect_smb, style=Pack(height=44))
            self.smb_view = toga.ScrollContainer(horizontal=False, content=toga.Box(children=[
                toga.Label('SMB / Mac share', style=Pack(font_size=22)),
                toga.Label(import_hint('On your Mac, enable File Sharing with SMB and allow your account. Use the server address without smb:// or a share path. Connect on the same network or VPN.')),
                toga.Label('Connection name'), self.smb_name, toga.Label('Server'), self.smb_host,
                toga.Label('Username'), self.smb_user, toga.Label('Password'), self.smb_password,
                toga.Label('Domain'), self.smb_domain, toga.Label('Port'), self.smb_port,
                self.smb_remember, toga.Label(import_hint('Off keeps connections only for this app session. Reloading saved credentials replaces session connections.')),
                self.smb_connect, self.smb_status], style=Pack(direction=COLUMN, margin=12)), style=Pack(flex=1))
        self.smb_connect.enabled = self.cloud_client is not None
        self.show_view(self.smb_view, destination='files', route='smb-connection', title='SMB / Mac share')

    async def connect_smb(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        name, host, user, domain, port = (control.value.strip() for control in
            (self.smb_name, self.smb_host, self.smb_user, self.smb_domain, self.smb_port))
        password = self.smb_password.value
        self.smb_password.value = ''
        remember = self.smb_remember.value
        self.set_cloud_busy(True)
        self.smb_connect.enabled = False
        self.smb_status.text = 'Adding connection…'
        try:
            names = await asyncio.to_thread(self.cloud_client.add_smb, name, host, user, password,
                                           domain, port or '445', remember=remember)
            if not self.active_host:
                return
            from .folder_hub import visible_remotes
            self.cloud_remote.items = visible_remotes(names)
            await self._load_crypt_remote_names()
            self.cloud_remote.value = name
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_package.text = 'Connections: ' + self.cloud_client.package_name
            self.smb_status.text = 'Connection added. Browse a share and choose Pull… for an offline folder.'
        except Exception as error:
            self.smb_status.text = import_hint('Could not add connection: ' + str(error)[:180])
            return
        finally:
            self.set_cloud_busy(False)
            self.smb_connect.enabled = True
        self.show_cloud()
        await self.browse_cloud()

    def selected_cloud_remote(self):
        try:
            return self.cloud_remote.value
        except IndexError:
            # Native spinners can report the previous row during a source reset.
            return None

    def set_cloud_busy(self, value):
        self.cloud_busy = value
        for item in (self.cloud_add_smb, self.cloud_choose, self.cloud_password, self.cloud_import, self.cloud_probe, self.cloud_remote,
                     self.cloud_location, self.cloud_browse, self.cloud_up, self.cloud_entries,
                     self.cloud_open, self.cloud_download, self.cloud_clear, self.cloud_reload, self.cloud_remember,
                     self.crypt_download, self.crypt_open, self.crypt_refresh, self.crypt_selector, self.crypt_password):
            item.enabled = not value and self.cloud_client is not None
        self.cloud_import.enabled = not value and self.cloud_client is not None and self.cloud_pending_zip is not None
        is_crypt = self.selected_cloud_remote() in self.cloud_crypt_remotes
        self.cloud_download.enabled = not value and self.cloud_client is not None
        self.cloud_download.text = 'Download decrypted' if is_crypt else 'Download'
        self.cloud_folder_open.enabled = not value and self.cloud_downloaded_folder is not None
        self.cloud_download_help.text = import_hint('Decrypted copy: saved unencrypted in Private downloads.\nEncrypted copy: kept encrypted in LocalCrypt.') if is_crypt else ''
        self.crypt_download.enabled = not value and self.cloud_client is not None and self.selected_cloud_remote() in self.cloud_crypt_remotes
        self.cloud_cancel.enabled = value
        self.refresh_cloud_copy_actions()
        self.refresh_folder_actions()
        self.download_open.enabled = self.download_export.enabled = not value and bool(self.download_labels)

    def refresh_cloud_copy_actions(self):
        if not hasattr(self, 'cloud_copy_button'):
            return
        ready = (not self.cloud_busy and self.cloud_client is not None
                 and self.selected_cloud_remote() == self.cloud_open_remote)
        self.cloud_copy_button.enabled = ready and bool(self.cloud_rows.get(self.cloud_entries.value))
        self.cloud_copy_folder.enabled = ready and bool(self.cloud_path)

    def cloud_remote_changed(self, widget=None, **kwargs):
        self.refresh_cloud_remote_help()
        if hasattr(self, 'download_labels'):
            self.set_cloud_busy(self.cloud_busy)

    def refresh_cloud_remote_help(self):
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
        # Alternate client adapters may expose ordinary downloads only.
        kinds = getattr(self.cloud_client, 'crypt_remotes', lambda: ())
        self.cloud_crypt_remotes = set(await asyncio.to_thread(kinds))
        self.refresh_cloud_remote_help()

    def retained_packages(self):
        if getattr(self.cloud_client, 'vault', None) is None:
            return None
        if not hasattr(self, 'credential_packages'):
            from .credential_packages import CredentialPackages
            from .credential_vault import ProtectedVault
            self.credential_packages = CredentialPackages(ProtectedVault.for_app(self, packages=True), self.cloud_client)
        return self.credential_packages

    def remember_credential_association(self, name, remotes, *, session_only):
        import json
        packages = json.loads(self.preferences.values['remote_packages'])
        packages = [item for item in packages if item['zip'] != name]
        packages.append(dict(zip=name, remotes=list(remotes), session_only=session_only))
        self.preferences.save(remote_packages=json.dumps(packages[-32:]))

    def credential_groups(self):
        import json
        from pathlib import Path
        groups = {'All': None}
        for item in json.loads(self.preferences.values['remote_packages']):
            if not self.legacy_name_visible(Path(item['zip']).name, prefix='legacy'):
                continue
            title = Path(item['zip']).stem
            if title in groups:
                title = item['zip']
            groups[title] = set(item['remotes'])
        return groups

    def require_remote_credentials(self, remote, *, identity=None, resume=None):
        """Return immediately when loaded; otherwise present the matching ZIP unlock."""
        loaded = [row.value for row in self.cloud_remote.items]
        if remote in loaded and identity is None:
            return True
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
            self.cloud_import_message.text = import_hint('Load the credential ZIP for ' + remote + '. Previously loaded ZIPs can be retained for password-only unlocking after this update.')
        return False

    def show_retained_unlock(self, key, remote, *, identity=None, resume=None):
        cache = self.retained_packages()
        password = self.credential_unlock_password = toga.PasswordInput(placeholder='ZIP password', style=Pack(height=44))
        status = self.credential_unlock_status = toga.Label('')
        async def unlock(widget=None, **kwargs):
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
                names = await asyncio.to_thread(self.cloud_client.import_package, cache, key, secret, remember=False)
                await self._load_crypt_remote_names()
                self.cloud_remote.items = visible_remotes(names)
                if remote not in names or (identity is not None and self.cloud_client.connection_identity(remote) != identity):
                    raise ValueError('This ZIP does not match the folder connection.')
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
        from .folder_hub import visible_remotes
        password.on_confirm = unlock
        self.credential_unlock_button = toga.Button('Unlock', on_press=unlock, style=Pack(height=44))
        box = toga.Box(children=[toga.Label(import_hint('Unlock ' + cache.items[key]['zip']), style=Pack(font_size=18)),
            toga.Label(import_hint('Its ZIP is retained on this device. The password is needed for this session and is never saved.')),
            password, self.credential_unlock_button, status,
            toga.Button('Cancel', on_press=lambda widget, **kw: self.routes.back(), style=Pack(height=44))],
            style=Pack(direction=COLUMN, margin=16))
        self.show_view(box, destination='files', route='unlock-credential', title='Unlock credential')

    async def restore_cloud(self, widget=None, *, initial=False, **kwargs):
        if (self.cloud_busy and not initial) or self.cloud_client is None:
            return
        if not self.clear_private_reader():
            return
        self.set_cloud_busy(True)
        try:
            self.clear_private_catalog()
            names = await asyncio.to_thread(self.cloud_client.restore)
            await self._load_crypt_remote_names()
            from .folder_hub import visible_remotes
            self.cloud_remote.items = visible_remotes(names)
            if names and self.cloud_client.package_name:
                self.remember_credential_association(self.cloud_client.package_name, visible_remotes(names), session_only=False)
            self.cloud_entries.items = []
            self.cloud_rows = {}
            self.cloud_open_remote = None
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_package.text = 'Credential package: ' + (self.cloud_client.package_name or 'none')
            if self.cloud_pending_zip is None and names:
                self.cloud_selected_zip.text = import_hint('Saved ZIP: ' + (self.cloud_client.package_name or 'saved package'))
                self.cloud_import_message.text = import_hint('Saved remotes are ready. Choose a remote below, then tap Browse folder.\nTo replace them, choose another ZIP.')
            self.cloud_status.value = (f'{len(names)} saved remote(s) restored. Choose a remote, then browse.'
                                       if names else 'No saved credential package. Import a ZIP to get started.')
        except Exception:
            self.cloud_status.value = 'Saved credentials are unavailable. Unlock the device and reload, or forget saved credentials to import again.'
        finally:
            self.set_cloud_busy(False)

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
        from .pickers import pick_document
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
            from .folder_hub import visible_remotes
            self.remember_credential_association(selected.name, visible_remotes(names), session_only=not self.cloud_remember.value)
            cache_error = ''
            try:
                cache = self.retained_packages()
                if cache is not None and not self.cloud_remember.value:
                    identities = {remote: self.cloud_client.connection_identity(remote) for remote in visible_remotes(names)}
                    await asyncio.to_thread(cache.remember, selected, identities)
            except (OSError, ValueError) as error:
                cache_error = ' ZIP could not be retained; choose it again next launch: ' + str(error)[:100]
            self.cloud_remote.items = visible_remotes(names)
            self.cloud_package.text = 'Logistics credential package: ' + getattr(self.cloud_client, 'package_name', 'Imported ZIP')
            self.cloud_location.value = self.cloud_path = ''
            self.cloud_open_remote = None
            self.cloud_rows = {}
            self.cloud_entries.items = []
            self.cloud_pending_zip = None
            self.cloud_selected_zip.text = import_hint('Loaded ZIP: ' + selected.name)
            self.cloud_import_message.text = import_hint(f'{len(names)} remote(s) loaded. Choose a remote below, then tap Browse folder.' + cache_error)
            self.cloud_status.value = f'{len(names)} {'saved' if self.cloud_remember.value else 'session'} remote(s) loaded. Choose a remote, then browse. No connection has been made yet.'
        except Exception as error:
            self.cloud_status.value = 'Import failed: ' + str(error)[:300]
            self.cloud_import_message.text = import_hint('Could not load ZIP. Check the password and tap Load remotes again.\n' + str(error)[:150])
        finally:
            password = None
            self.set_cloud_busy(False)

    async def browse_cloud(self, widget=None, *, preserve_path=False, **kwargs):
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
        self.cloud_status.value = f'Opening {remote}:{folder}…'
        self.set_cloud_busy(True)
        self.cloud_rows = {}
        self.cloud_entries.items = []
        try:
            rows = await asyncio.to_thread(self.cloud_client.entries, remote, folder)
            self.cloud_rows = {f'{index + 1}. {"Folder" if row["directory"] else "File"}: {row["path"]}': row
                               for index, row in enumerate(rows)}
            self.cloud_entries.items = list(self.cloud_rows)
            self.cloud_open_remote, self.cloud_path = remote, folder
            from pathlib import Path
            from types import SimpleNamespace
            import base64
            from commonUtils.runtime.resource_provider import resource_path
            root = Path('/remote') / remote
            provider = SimpleNamespace(root=root, remote=remote, relative=lambda path: resource_path(str(Path(path).relative_to(root)) if Path(path).is_absolute() else path))
            generation = getattr(self.cloud_client, 'generation', 0)
            def list_children(path, *, cancelled):
                if cancelled() or getattr(self.cloud_client, 'generation', 0) != generation:
                    raise ValueError('Search cancelled or credentials changed.')
                values = self.cloud_client.entries(remote, path)
                if cancelled() or getattr(self.cloud_client, 'generation', 0) != generation:
                    raise ValueError('Search cancelled or credentials changed.')
                return [dict(row, name=Path(row['path']).name, modified='') for row in values]
            provider.list = list_children
            password = self.crypt_password.value
            client = self.cloud_client
            def thumbnail(row, size, cancelled):
                if cancelled() or not getattr(client, 'supports_streaming', False):
                    return b''
                if Path(row['path']).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp', '.zip', '.cbz', '.epub'}:
                    return b''
                result = client.request('remote_thumbnail', remote=remote, path=row['path'], password=password, width=size[0], height=size[1])
                return base64.b64decode(result['data'], validate=True) if not cancelled() else b''
            self.remote_browser.closed = False
            self.remote_browser.thumbnail = thumbnail
            self.remote_browser.set_entries(provider, folder, [dict(row, name=Path(row['path']).name, modified='') for row in rows], location=(remote, folder))
            self.cloud_status.value = (f'{remote}:{folder} · {len(rows)} items.\nTap folders to open them. Select a file to copy, or use Copy this folder.' if rows else f'{remote}:{folder} is empty.')
            return True
        except Exception as error:
            self.cloud_status.value = 'Browse failed: ' + str(error)[:300]
            if self.remote_browser.tree is not None:
                self.cloud_remote.value, self.cloud_location.value = self.cloud_open_remote, self.cloud_path
                self.cloud_rows = previous_rows
                self.cloud_entries.items = list(previous_rows)
                if previous_selected is not None:
                    self.cloud_entries.value = previous_selected
            return False
        finally:
            self.set_cloud_busy(False)

    async def parent_cloud(self, widget=None, **kwargs):
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
            self.refresh_cloud_copy_actions()
            return
        label = next((label for label, value in self.cloud_rows.items() if value['path'] == row['path']), None)
        if label is None:
            label = 'Search: ' + row['path']
            self.cloud_rows[label] = row
            self.browser_cloud_selected(None)
        self.cloud_entries.value = label
        self.cloud_status.value = ('Selected folder: ' if row['directory'] else 'Selected file: ') + row['path']
        self.refresh_cloud_copy_actions()

    async def browser_cloud_folder(self, row):
        if self.cloud_busy:
            return False
        return await self.browser_cloud_location((self.cloud_open_remote, row['path']))

    async def browser_cloud_location(self, location):
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

    async def download_cloud(self, widget=None, **kwargs):
        row = self.cloud_rows.get(self.cloud_entries.value)
        if self.cloud_busy:
            return
        if not row:
            self.cloud_status.value = 'Select a file or folder in the list above, then tap Download.'
            return False
        if self.selected_cloud_remote() != self.cloud_open_remote:
            self.cloud_status.value = 'The remote changed. Tap Browse folder to open it first.'
            return False
        self.cloud_status.value = 'Downloading ' + row['path'] + '…'
        self.set_cloud_busy(True)
        try:
            name = download_name(row['path'])
            decrypted = self.cloud_open_remote in self.cloud_crypt_remotes
            if row['directory']:
                from .folder_download import pull_folder
                from threading import Event
                self._crypt_cancel = Event()
                remote = self.cloud_open_remote
                def progress(count, path):
                    self.loop.call_soon_threadsafe(setattr, self.cloud_status, 'value', f'Downloading folder: {count} files saved\n{path}')
                target = await asyncio.to_thread(pull_folder, self.cloud_client, remote, row['path'],
                    self.private_root / 'LocalFiles', decrypted=decrypted, cancelled=self._crypt_cancel.is_set, progress=progress)
                self.cloud_downloaded_folder = target.name
                self.cloud_status.value = f'Downloaded folder to On this device/{target.name}.\nThis is an unencrypted local copy. The remote original is unchanged.'
                return True
            target = await asyncio.to_thread(self.downloads.fetch, self.cloud_client,
                                            self.cloud_open_remote, row['path'], decrypted=decrypted)
            self.refresh_downloads(target)
            self.cloud_status.value = (f'Downloaded decrypted {name} to Private downloads; this copy is unencrypted. Tap Open private copy below.' if decrypted
                                       else f'Downloaded {name}. Tap Open private copy below. The remote original was preserved.')
        except Exception as error:
            self.cloud_status.value = 'Download failed: ' + str(error)[:300]
        finally:
            if row['directory']:
                self._crypt_cancel = None
            self.set_cloud_busy(False)

    async def open_downloaded_folder(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_downloaded_folder is None:
            return
        await self.show_local_location()
        await self.browser_file_location(('Local files', self.cloud_downloaded_folder))

    def cancel_cloud(self, widget=None, **kwargs):
        if getattr(self, '_crypt_cancel', None) is not None:
            self._crypt_cancel.set()
        if self.cloud_client:
            self.cloud_client.cancel()
            self.cloud_status.value = 'Cancelling the remote request…'

    async def clear_cloud(self, widget=None, **kwargs):
        if self.cloud_busy or self.cloud_client is None:
            return
        self.set_cloud_busy(True)
        try:
            if not self.clear_private_reader():
                return
            self.clear_private_catalog()
            if hasattr(self, 'pull_jobs'):
                self.pull_jobs.forget_private()
            await asyncio.to_thread(self.cloud_client.clear)
            self.cloud_crypt_remotes = set()
            self.cloud_remote.items = self.cloud_entries.items = []
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
            self.cloud_status.value = 'Saved and session credentials forgotten. Private downloads remain available.'
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
        from commonUtils.runtime.document_access import LocalDocuments
        selected = path if path is not None else self.download_labels.get(self.download_selector.value)
        independent = (self.cloud_busy and getattr(self, 'transfer_busy', False) and path is not None
                       and selected.resolve().is_relative_to((self.private_root / 'LocalFiles').resolve()))
        if (self.cloud_busy and not independent) or selected is None:
            return
        destination = destination or ('files' if self.native_host.state.destination == 'files' else 'documents')
        if not independent:
            self.set_cloud_busy(True)
        try:
            from .resource_imports import ResourceImports
            if not hasattr(self, 'resource_imports'):
                self.resource_imports = ResourceImports(self.private_root)
            imported = self.resource_imports.find(selected)
            if imported is not None:
                if imported['provider'] == 'library':
                    await self.open_book(imported['resource'], destination=destination)
                elif self.open_document(imported['resource']):
                    self.show_documents(resume=True, destination=destination)
                else:
                    raise ValueError('The imported copy is unavailable; its index and source were preserved.')
                return
            if selected.suffix.lower() in {'.epub', '.cbz', '.zip'}:
                catalog = self.reader_manager().catalog
                generation = self.navigation_generation
                record = await asyncio.to_thread(catalog.library_store.import_book, LocalDocuments(), selected)
                self.resource_imports.remember(selected, 'library', record['id'])
                if not self.active_host or (independent and self.navigation_generation != generation):
                    return
                self.refresh_library()
                await self.open_book(record['id'], destination=destination)
            else:
                doc = await asyncio.to_thread(self.store.import_document, LocalDocuments(), selected)
                self.resource_imports.remember(selected, 'managed-text', doc.id)
                self.refresh_documents()
                self.open_document(doc.id)
                self.show_documents(destination=destination)
        except Exception as error:
            self.cloud_status.value = 'Open failed: ' + str(error)[:300]
            if independent:
                self.file_status.value = self.cloud_status.value
                readers = getattr(self, 'readers', None)
                if readers is not None and readers.active is not None:
                    readers.active.book_status.text = self.cloud_status.value
            else:
                self.show_cloud()
        finally:
            if not independent:
                self.set_cloud_busy(False)

    async def export_download(self, widget=None, **kwargs):
        from .pickers import export_file
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
