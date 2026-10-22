"""SMB connection form, secret consumption and asynchronous connection workflow."""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol
import toga
from toga.style import Pack
from toga.style.pack import COLUMN
from commonUtils.ui.native.password_input import PasswordInput
from .messages import import_hint


@dataclass
class SMBFormState:
    # Unbuilt controls intentionally raise AttributeError, preserving lazy creation.
    smb_account: Any = field(init=False, repr=False)
    smb_advanced_toggle: Any = field(init=False, repr=False)
    smb_connect: Any = field(init=False, repr=False)
    smb_domain: Any = field(init=False, repr=False)
    smb_guest: Any = field(init=False, repr=False)
    smb_help_toggle: Any = field(init=False, repr=False)
    smb_host: Any = field(init=False, repr=False)
    smb_name: Any = field(init=False, repr=False)
    smb_password: Any = field(init=False, repr=False)
    smb_port: Any = field(init=False, repr=False)
    smb_remember: Any = field(init=False, repr=False)
    smb_signin: Any = field(init=False, repr=False)
    smb_status: Any = field(init=False, repr=False)
    smb_user: Any = field(init=False, repr=False)
    smb_view: Any = field(init=False, repr=False)


class ConnectionHost(Protocol):
    cloud_busy: bool
    cloud_client: Any
    rclone_ui: Any
    active_host: bool
    cloud_remote: Any
    cloud_location: Any
    cloud_path: str
    cloud_open_remote: str | None
    cloud_rows: dict
    cloud_entries: Any
    cloud_package: Any

    def show_cloud(self, *, present: bool = True) -> None: ...
    def show_view(self, view: Any, **kwargs: Any) -> None: ...
    def set_cloud_busy(self, busy: bool) -> None: ...
    def set_loaded_remote_names(self, names: list[str]) -> None: ...
    def visible_remote_names(self, names: list[str]) -> list[str]: ...
    def remember_loaded_packages(self, package: str, names: list[str], *, session_only: bool) -> None: ...
    def loaded_package_label(self) -> str: ...
    async def _load_crypt_remote_names(self) -> None: ...
    async def browse_cloud(self) -> None: ...


class SMBConnection:
    def __init__(self, cloud: ConnectionHost, form: SMBFormState):
        self.cloud, self.form = cloud, form

    def show_smb_connection(self, widget=None, **kwargs):
        cloud, form = self.cloud, self.form
        cloud.show_cloud(present=False)
        if cloud.cloud_busy:
            return
        if not hasattr(form, 'smb_view'):
            form.smb_name = toga.TextInput(placeholder='Connection name (e.g. Home Mac)', style=Pack(height=44))
            form.smb_host = toga.TextInput(placeholder='Server IP or hostname (e.g. 192.168.1.10)', style=Pack(height=44))
            form.smb_user = toga.TextInput(placeholder='Your server account', style=Pack(height=44))
            form.smb_password = PasswordInput(placeholder='Share password', style=Pack(height=44))
            form.smb_domain = toga.TextInput(value='WORKGROUP', style=Pack(height=44))
            form.smb_port = toga.TextInput(value='445', style=Pack(height=44))
            form.smb_remember = toga.Switch('Save credentials on this device', value=True, style=Pack(height=44))
            ui = cloud.rclone_ui
            form.smb_status = ui.settings.note('')
            form.smb_guest = toga.Switch('Connect as guest', value=False, on_change=self.change_smb_guest, style=Pack(height=44))
            form.smb_account = toga.Box(children=[ui.settings.field('Username', form.smb_user),
                ui.settings.field('Password', form.smb_password)], style=Pack(direction=COLUMN))
            form.smb_signin = ui.settings.group([form.smb_guest, form.smb_account])
            advanced, form.smb_advanced_toggle = ui.settings.disclosure('Advanced options', [
                ui.settings.group([ui.settings.field('Domain', form.smb_domain), ui.settings.field('Port', form.smb_port)])])
            help_box, form.smb_help_toggle = ui.settings.disclosure('Need help connecting?', [
                ui.settings.note('Use the same network or VPN. On a Mac, enable File Sharing, turn on SMB, and allow your account. Use a hostname or IP without smb:// or a share path.')])
            form.smb_connect = toga.Button('Connect & browse shares', on_press=self.connect_smb, style=Pack(height=48))
            form.smb_view = ui.settings.page('SMB shares', 'Connect to a Mac, PC, or NAS on your network.', [
                ui.settings.heading('NEW CONNECTION'),
                ui.settings.group([ui.settings.field('Connection name', form.smb_name), ui.settings.field('Server address', form.smb_host)]),
                ui.settings.note('Use a hostname or IP address. Choose a share after connecting.'),
                ui.settings.heading('SIGN IN'), form.smb_signin, advanced,
                ui.settings.group([form.smb_remember]), ui.settings.note('Turn off to connect for this session only.'),
                form.smb_connect, help_box, form.smb_status])
        form.smb_connect.enabled = cloud.cloud_client is not None
        cloud.show_view(form.smb_view, destination='settings', route='smb-connection', title='SMB shares')

    def change_smb_guest(self, widget=None, **kwargs):
        cloud, form = self.cloud, self.form
        form.smb_password.value = ''
        if form.smb_guest.value:
            if form.smb_account.parent is not None:
                form.smb_signin.remove(form.smb_account)
        elif form.smb_account.parent is None:
            form.smb_signin.add(form.smb_account)
        if hasattr(form, 'smb_view'):
            form.smb_view.reflow()

    async def connect_smb(self, widget=None, **kwargs):
        cloud, form = self.cloud, self.form
        if cloud.cloud_busy or cloud.cloud_client is None:
            return
        name, host, user, domain, port = (control.value.strip() for control in
            (form.smb_name, form.smb_host, form.smb_user, form.smb_domain, form.smb_port))
        password = form.smb_password.value
        form.smb_password.value = ''
        if form.smb_guest.value:
            user, password = 'guest', ''
        if not name or not host or not user:
            form.smb_status.text = 'Enter a connection name, server address, and username, or choose guest access.'
            return
        remember = form.smb_remember.value
        cloud.set_cloud_busy(True)
        form.smb_connect.enabled = False
        form.smb_status.text = 'Adding connection…'
        try:
            names = await asyncio.to_thread(cloud.cloud_client.add_smb, name, host, user, password,
                                           domain, port or '445', remember=remember)
            if not cloud.active_host:
                return
            visible_remotes = cloud.rclone_ui.visible_remotes
            cloud.set_loaded_remote_names(cloud.visible_remote_names(names))
            await cloud._load_crypt_remote_names()
            cloud.cloud_remote.value = name
            cloud.cloud_location.value = cloud.cloud_path = ''
            cloud.cloud_open_remote = None
            cloud.cloud_rows = {}
            cloud.cloud_entries.items = []
            cloud.remember_loaded_packages(cloud.cloud_client.package_name, names, session_only=not remember)
            cloud.cloud_package.text = cloud.loaded_package_label()
            form.smb_status.text = 'Connection added. Browse a share and choose Pull… for an offline folder.'
        except Exception as error:
            form.smb_status.text = import_hint('Could not add connection: ' + str(error)[:180])
            return
        finally:
            cloud.set_cloud_busy(False)
            form.smb_connect.enabled = True
        cloud.show_cloud()
        await cloud.browse_cloud()

