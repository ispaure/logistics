"""Trusted Wi-Fi preference controls, saved separately from session authentication."""
import json
import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW
from .forms import SettingsLabel, switch_row, fit_section, settings_presentation
from ..trusted_wifi import read_ssid, request_access, access_state, network_names


def controls(app, box):
    choice = toga.Switch('Skip session password on trusted Wi-Fi',
        value=app.preferences.values['session_trusted_wifi'] == 'true', style=Pack(height=48))
    box.add(switch_row(app, 'Skip session password on trusted Wi-Fi', choice,
        'Skip repeat password prompts after sleep or switching apps on listed Wi-Fi networks, '
        'for already-unlocked session-only credentials. Off by default. Passwords are never saved. '
        'App restart and manual session locking still require authentication. '
        'Wi-Fi names can be duplicated; this is a convenience setting.'))
    manage = toga.Button('Trusted Wi-Fi networks…', enabled=choice.value,
        on_press=lambda widget, **kwargs: show(app), style=Pack(height=48))
    management = toga.Box(style=Pack(direction=COLUMN))
    if choice.value:
        management.add(manage)
    box.add(management)
    status = SettingsLabel('')
    box.add(status)
    saving = False
    def save(widget, **kwargs):
        nonlocal saving
        if saving:
            return
        saving = True
        try:
            app.preferences.save(session_trusted_wifi='true' if choice.value else 'false')
            manage.enabled = choice.value
            # Settings presentation reparents buttons into rounded groups. Keep
            # a stable owner instead of assuming the button remains a direct child.
            if manage.parent is not None:
                manage.parent.remove(manage)
            management.clear()
            if choice.value:
                management.add(manage)
                settings_presentation(management)
            status.text = ''
        except (OSError, ValueError) as error:
            choice.value = app.preferences.values['session_trusted_wifi'] == 'true'
            status.text = str(error)
        finally:
            saving = False
        fit_section(box, app.adaptive.content_width('settings'))
    choice.on_change = save
    return choice, manage


def show(app):
    box = toga.Box(style=Pack(direction=COLUMN, margin=16))
    box.add(SettingsLabel('Trusted Wi-Fi networks', style=Pack(font_size=22)))
    box.add(SettingsLabel('Only listed network names skip repeat prompts. Public or unlisted Wi-Fi, '
        'cellular, and unavailable Wi-Fi information require your session password. '
        'The list is saved on this device. Names match exactly, including case and spaces.'))
    status = SettingsLabel('')
    current = SettingsLabel('Current Wi-Fi: identification not enabled.')
    entry = toga.TextInput(placeholder='Wi-Fi network name (SSID)', style=Pack(height=48))
    rows = toga.Box(style=Pack(direction=COLUMN))
    allowed = False
    def fit():
        fit_section(box, app.adaptive.content_width('settings'))
    async def refresh(widget=None, **kwargs):
        if not allowed or access_state(app) != 'granted':
            add_button.enabled = False
            current.text = 'Current Wi-Fi: identification not enabled. You can enter a network name below.'
            fit()
            return None
        ssid = await read_ssid(app)
        current.text = 'Current Wi-Fi: ' + (ssid or 'Unavailable. Check precise location access, location services and your Wi-Fi connection, then try Add current network again.')
        fit()
        return ssid
    def save(names):
        try:
            network_names(json.dumps(names))
            app.preferences.save(trusted_wifi_networks=json.dumps(names))
            render()
            status.text = 'Trusted networks saved.'
            fit()
            return True
        except (OSError, ValueError) as error:
            status.text = str(error)
        fit()
        return False
    def add(name):
        names = network_names(app.preferences.values['trusted_wifi_networks'])
        if not name:
            status.text = 'Enter a Wi-Fi name or connect to a readable Wi-Fi network.'
            fit()
            return
        if name in names:
            status.text = 'This network is already trusted.'
            fit()
        elif save([*names, name]):
            entry.value = ''
    def render():
        rows.clear()
        for name in network_names(app.preferences.values['trusted_wifi_networks']):
            def remove(widget, name=name, **kwargs):
                save([value for value in network_names(app.preferences.values['trusted_wifi_networks']) if value != name])
            remove_button = toga.Button('−', on_press=remove,
                style=Pack(width=48, height=48, color='#c62828', font_size=24))
            backend = type(remove_button._impl).__module__
            if backend.startswith('toga_iOS.'):
                remove_button._impl.native.accessibilityLabel = 'Remove ' + name
            elif backend.startswith('toga_android.'):
                remove_button._impl.native.setContentDescription('Remove ' + name)
            rows.add(toga.Box(children=[SettingsLabel(name, style=Pack(flex=1)),
                remove_button], style=Pack(direction=ROW)))
        if not rows.children:
            rows.add(SettingsLabel('No trusted networks. Session passwords will still be required.'))
    async def identify():
        nonlocal allowed
        try:
            state = access_state(app)
            if state != 'granted':
                message = ('Allow Logistics to identify your current Wi-Fi network using precise foreground '
                    'location permission? No location updates are collected. You can decline and still enter network names manually.')
                if state == 'settings':
                    message = ('Wi-Fi identification needs precise foreground location access. The system cannot '
                        'show the permission prompt again. Enable location access and Precise Location for Logistics '
                        'in system Settings, then reopen this panel. You can still enter network names manually.')
                    await app.main_window.dialog(toga.InfoDialog('Allow Wi-Fi identification', message))
                    return
                if not await app.main_window.dialog(toga.ConfirmDialog('Allow Wi-Fi identification?', message)):
                    return
            allowed = await request_access(app)
            add_button.enabled = allowed
            if allowed:
                await refresh()
            else:
                status.text = ('Wi-Fi identification is not allowed. You can enter network names manually. '
                    'Reopen this panel to try again, or enable precise location access for Logistics in system Settings.')
        except Exception:
            allowed = False
            add_button.enabled = False
            status.text = ('Could not allow Wi-Fi identification. Check Logistics location permissions in system Settings. '
                'You can still enter network names manually.')
        finally:
            fit()
    box.add(current)
    async def add_current(widget=None, **kwargs):
        if allowed:
            ssid = await refresh()
            if ssid:
                add(ssid)
    add_button = toga.Button('Add current network', on_press=add_current,
        enabled=False, style=Pack(height=48))
    box.add(add_button)
    box.add(entry)
    box.add(toga.Button('Add network name', on_press=lambda widget, **kwargs: add(entry.value), style=Pack(height=48)))
    box.add(rows)
    box.add(status)
    render()
    app.show_view(toga.ScrollContainer(content=box, horizontal=False, style=Pack(flex=1)),
                  destination='settings', route='trusted-wifi', title='Trusted Wi-Fi networks')
    app.loop.create_task(identify())
