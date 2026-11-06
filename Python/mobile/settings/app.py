"""App startup preferences and window commands."""
import toga
from toga.style import Pack
from .forms import page, switch_row


def application(app):
    box = page('App')
    app.restore_choice = toga.Switch('Restore last document',
        value=app.preferences.values['restore_last_document'] == 'true', style=Pack(height=48))
    app.clear_documents_choice = toga.Switch('Clear on restart',
        value=app.preferences.values['clear_unmodified_documents_on_restart'] == 'true',
        style=Pack(height=48))
    box.add(switch_row(app, 'Restore last document', app.restore_choice,
        'Resume the last active document when the app starts.'))
    box.add(switch_row(app, 'Close saved documents on restart', app.clear_documents_choice,
        'Close documents with no unsaved changes when the app restarts. Files and drafts are kept. '
        'The last active document stays open if Restore last document is on.'))
    if app.scene_manager.supported:
        box.add(toga.Button('New window', on_press=app.scene_manager.new_window, style=Pack(height=48)))
        if app.window_id != 'primary':
            box.add(toga.Button('Close window', on_press=lambda widget, **kw:
                app.scene_manager.close_window(app), style=Pack(height=48)))
    app.restore_choice.on_change = app.save_preferences
    app.clear_documents_choice.on_change = app.save_preferences
    return box
