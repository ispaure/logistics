"""Settings → Workspaces: visibility and links to storage/connection owners."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from services.mobile_features import enabled
from .forms import page, switch_row, page_button


def workspaces(app):
    box = page('Workspaces')
    if type(app._impl).__module__.startswith('toga_android.'):
        box.add(page_button('File storage…', on_press=app.show_collection_storage, style=Pack(height=48)))
    app.show_legacy_choice = toga.Switch('Show Legacy',
        value=getattr(app, 'show_legacy_session', False),
        on_change=app.change_show_legacy, style=Pack(height=48))
    box.add(switch_row(app, 'Show Legacy', app.show_legacy_choice,
        'Show older folders and credentials named Legacy. Resets when the app closes.'))
    if enabled(app.preferences, 'rclone'):
        from mobile import transfer_notification_native
        if transfer_notification_native.supported(app):
            add_transfer_notification_setting(app, box)
        from .reader_history import migration_controls
        migration_controls(app, box)
        box.add(page_button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)))
        box.add(page_button('SMB shares…', on_press=app.show_smb_connection, style=Pack(height=48)))
    return box


def add_transfer_notification_setting(app, box):
    from mobile.transfer_notification_native import request
    from mobile.transfer_notifications import PREFERENCE

    def change(widget, **kwargs):
        widget.enabled = False

        def finish(granted):
            if not app.active_host:
                return
            try:
                app.preferences.save(**{PREFERENCE: 'true' if granted else 'false'})
            except (OSError, ValueError):
                status.text = 'The setting could not be saved.'
            else:
                status.text = ('Background notifications enabled.' if granted else
                               'Enable notifications in system settings to receive background transfer results.'
                               if widget.value else '')
            widget.value = app.preferences.values[PREFERENCE] == 'true'
            widget.enabled = True

        if not widget.value:
            finish(False)
        else:
            try:
                request(app, finish)
            except Exception:
                finish(False)

    toggle = toga.Switch('Background transfer notifications',
        value=app.preferences.values[PREFERENCE] == 'true', on_change=change, style=Pack(height=48))
    status = toga.Label('')
    box.add(switch_row(app, 'Background transfer notifications', toggle,
        'Get a system notification for long transfers that finish while Logistics is in the background.'))
    box.add(status)
