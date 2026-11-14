"""Native settings controls for rclone credential packages and ZIP import."""
import toga
from toga.style import Pack

from commonUtils.ui.native.password_input import PasswordInput


def build_credential_import_controls(cloud):
    """Create controls reused by the chooser and the encrypted ZIP form."""
    async def choose(widget, **kwargs):
        await cloud.credential_workflow.choose_cloud_package(automatic=True)

    async def unlock(widget, **kwargs):
        await cloud.credential_workflow.import_cloud_package(interactive=True)

    cloud.cloud_choose = toga.Button('Choose credential ZIP…', on_press=choose, style=Pack(height=44))
    cloud.cloud_selected_zip = cloud.rclone_ui.settings.note('')
    cloud.cloud_import_message = cloud.rclone_ui.settings.note('Choose a credential ZIP to add its connections.')
    cloud.cloud_password = PasswordInput(placeholder='ZIP password (if encrypted)', on_confirm=unlock, style=Pack(flex=1, height=44))
    cloud.cloud_import = toga.Button('Unlock', on_press=unlock, style=Pack(height=44, font_weight='bold'))
    cloud.cloud_probe = toga.Button('Check rclone engine', on_press=cloud.probe_cloud, style=Pack(height=44))
    cloud.cloud_remember = toga.Switch('Save credentials on this device', value=True, style=Pack(height=44))
    cloud.cloud_package = toga.Label('Credential package: none', style=Pack(font_size=14))
    cloud.cloud_reload = toga.Button('Reload saved credentials', on_press=cloud.restore_cloud, style=Pack(height=44))


def build_credential_pages(cloud, error):
    """Build the retained Credential Packages and Import credential ZIP pages."""
    ui = cloud.rclone_ui
    cloud.cloud_connections_status = ui.settings.note(error)
    cloud.cloud_import_entry = toga.Button('Import credential ZIP…', on_press=cloud.begin_cloud_import, style=Pack(height=48))
    troubleshooting, cloud.cloud_settings_toggle = ui.settings.disclosure('Advanced & troubleshooting', [
        ui.settings.group([cloud.cloud_reload, cloud.cloud_probe]),
        ui.settings.heading('Credential removal'), ui.settings.group([cloud.cloud_clear])])
    cloud.cloud_connections_view = ui.settings.page('Credential Packages',
        '', [cloud.cloud_retained_box,
            cloud.cloud_import_entry, ui.settings.note('Import a package exported from Logistics desktop.'),
            ui.settings.heading('SESSION'), ui.settings.group([cloud.cloud_lock]),
            ui.settings.note('Lock to stop access until you unlock again. This also locks SMB connections.'),
            troubleshooting, cloud.cloud_connections_status])
    cloud.cloud_import_view = ui.settings.page('Import credential ZIP',
        'Choose a package exported from Logistics desktop.', [
            cloud.cloud_choose, cloud.cloud_selected_zip, cloud.cloud_import_message])


def build_credential_password_page(cloud, package):
    """Move the retained password and feedback controls into the unlock form."""
    ui = cloud.rclone_ui
    for control in (cloud.cloud_password, cloud.cloud_import, cloud.cloud_import_message):
        if control.parent is not None:
            control.parent.remove(control)
    cloud.cloud_import_message.text = 'This ZIP is encrypted. Your password is never saved.'
    return ui.settings.page('Unlock credential ZIP', package.name, [
        ui.settings.group([ui.settings.field('ZIP password', cloud.cloud_password)]),
        cloud.cloud_import_message, cloud.cloud_import,
        toga.Button('Choose a different ZIP…', on_press=cloud.begin_cloud_import, style=Pack(height=48)),
        toga.Button('Cancel', on_press=lambda widget: cloud._finish_cloud_import(), style=Pack(height=48))])
