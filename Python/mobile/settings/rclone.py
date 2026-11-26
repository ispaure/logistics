"""Settings for rclone connections and selected folder downloads."""

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "marcandre.voyer@gmail.com"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack

from .forms import SettingsLabel, page, page_button, save_boolean_switch, switch_row


def rclone(app):
    box = page('rclone')
    key = 'rclone_parallel_folder_downloads'
    title = 'Parallel folder downloads'
    switch = toga.Switch(title, value=app.preferences.values[key] == 'true', style=Pack(height=48))
    status = SettingsLabel('')

    def changed(widget, **kwargs):
        if save_boolean_switch(app.preferences, widget, key, changed, status):
            status.text = ''

    def refresh():
        value = app.preferences.values[key] == 'true'
        if switch.value != value:
            switch.on_change = None
            try:
                switch.value = value
            finally:
                switch.on_change = changed

    switch.on_change = changed
    box._settings_on_open = refresh
    box.add(page_button('rclone connections…', on_press=app.show_cloud_connections, style=Pack(height=48)),
            switch_row(app, title, switch,
                'Copy up to 10 files at once when downloading a folder that supports resume. '
                'Turn this off to copy one file at a time and keep resume available. '
                'Applies when you start or resume a download.'),
            status)
    return box
