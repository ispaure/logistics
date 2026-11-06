"""Settings → Workspaces: visibility and links to storage/connection owners."""
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
        from .reader_history import migration_controls
        migration_controls(app, box)
        box.add(page_button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)))
        box.add(page_button('SMB shares…', on_press=app.show_smb_connection, style=Pack(height=48)))
    return box
