"""Device-wide video playback settings on iPhone and iPad."""
import toga
from toga.style import Pack

from .forms import page, save_boolean_switch, switch_row


def video(app):
    box = page('Video')
    key = 'native_video_airplay'
    title = 'Native AirPlay video'
    switch = toga.Switch(title, value=app.preferences.values[key] == 'true', style=Pack(height=48))

    def changed(widget, *args, **kwargs):
        if save_boolean_switch(app.preferences, widget, key, changed, app.settings_status):
            app.settings_status.text = ''

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
    box.add(switch_row(app, title, switch,
        'Show an AirPlay picker in the Logistics player for compatible local MP4, MOV, M4V and MKV files. '
        'Applies when you reopen a video.'))
    return box
