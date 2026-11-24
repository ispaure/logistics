"""App startup preferences and window commands."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from .forms import page, SettingsLabel
from ..appearance import accessible_name


def application(app):
    box = page('App')
    labels = {
        'home': 'Start at Home',
        'resume': 'Resume last document',
        'keep_open': 'Keep open documents',
    }
    modes = {label: mode for mode, label in labels.items()}
    choice = toga.Selection(items=list(labels.values()),
        value=labels[app.preferences.values['document_restart']], style=Pack(height=48))
    accessible_name(choice, 'On restart')
    box.restart_choice = choice

    def save_restart(widget, **kwargs):
        saved = app.preferences.values['document_restart']
        mode = modes.get(widget.value)
        if mode is None or mode == saved:
            return
        try:
            app.preferences.save(document_restart=mode)
        except (OSError, ValueError) as error:
            widget.value = labels[saved]
            app.settings_status.text = str(error)
        else:
            app.settings_status.text = ''

    choice.on_change = save_restart
    box.add(SettingsLabel('On restart'), choice,
            SettingsLabel('Saved files stay where they are. Recoverable unsaved drafts stay in Documents → Recent.'))
    if app.scene_manager.supported:
        box.add(toga.Button('New window', on_press=app.scene_manager.new_window, style=Pack(height=48)))
        if app.window_id != 'primary':
            box.add(toga.Button('Close window', on_press=lambda widget, **kw:
                app.scene_manager.close_window(app), style=Pack(height=48)))
    return box
