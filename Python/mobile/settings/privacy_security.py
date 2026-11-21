"""Settings → Privacy & Security controls; access policy remains with its owners."""
import toga
from toga.style import Pack
from .forms import page, SettingsLabel, switch_row


def privacy(app):
    box = page('Privacy & Security')
    box.add(SettingsLabel('Session-only access', style=Pack(font_weight='bold')))
    box.add(SettingsLabel(
        'When you import a credential ZIP as session-only, Logistics keeps the unlocked '
        'credentials in memory. Quitting or choosing Lock session clears them. Logistics '
        'keeps the encrypted ZIP. Unlock it again to reconnect.'))
    box.add(SettingsLabel(
        'When the screen sleeps or you leave the app, Logistics hides protected content. '
        'Enter the credential or session password when you return.'))
    from mobile.clipboard import controller, KEY
    from services.clipboard_policy import DESCRIPTION, LABEL
    policy = controller(app)
    if policy is not None:
        from .forms import save_boolean_switch

        def change(widget, **kwargs):
            if save_boolean_switch(policy.preferences, widget, KEY, change, app.settings_status):
                policy.publish()
                app.settings_status.text = ''

        choice = toga.Switch(LABEL, value=policy.preferences.values[KEY] == 'true',
                             on_change=change, style=Pack(height=48))
        def refresh():
            choice.on_change = None
            try:
                choice.value = policy.preferences.values[KEY] == 'true'
            finally:
                choice.on_change = change

        box._settings_on_open = refresh
        limits = (' The keyboard’s clipboard tools and File Browser moves are separate.'
                  if policy.android else ' Web previews, keyboard tools and File Browser moves are separate.')
        box.add(switch_row(app, LABEL, choice, DESCRIPTION + limits))
    box.add(SettingsLabel('Trusted Wi-Fi', style=Pack(font_weight='bold')))
    from .trusted_wifi import controls as trusted_wifi_controls
    trusted_wifi_controls(app, box)
    box.add(SettingsLabel('Playback while locked', style=Pack(font_weight='bold')))
    app.playlist_speech_choice = toga.Switch('Playlist speech while locked',
        value=app.preferences.values['playlist_speech_when_locked'] == 'true',
        on_change=app.change_playlist_speech, style=Pack(height=48))
    box.add(switch_row(app, 'Playlist speech while locked', app.playlist_speech_choice,
        'Let an ordinary Notes Library playlist that is already playing continue with the screen locked.'))
    app.session_speech_choice = toga.Switch('Session-only speech while locked',
        value=app.preferences.values['session_speech_when_locked'] == 'true',
        on_change=app.change_session_speech, style=Pack(height=48))
    box.add(switch_row(app, 'Session-only speech while locked', app.session_speech_choice,
        'Let read-aloud that is already playing continue when a protected session locks. '
        'Use the system playback controls to pause or resume. A protected playlist can continue through '
        'notes it prepared while unlocked. Protected video pauses, and opening new protected files requires unlocking.'))
    box.add(SettingsLabel('Protected audio outputs', style=Pack(font_weight='bold')))
    from .audio import controls as audio_controls
    audio_controls(app, box)
    return box
