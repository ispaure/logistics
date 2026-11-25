"""Settings → Appearance: accent, seasonal snow and Android E Ink."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import toga
from toga.style import Pack
from .forms import page, switch_row


def appearance(app):
    box = page('Appearance')
    from .accent import AccentControls
    app.accent_controls = AccentControls(app)
    box.add(app.accent_controls)
    app.snow_choice = toga.Switch('Seasonal snow',
        value=app.preferences.values['seasonal_snow'] == 'true', style=Pack(height=48))
    box.add(switch_row(app, 'Seasonal snow', app.snow_choice,
        'Show falling snow from December 15 to January 2. Hidden in high-contrast / E Ink mode.'))
    app.snow_choice.on_change = app.change_seasonal_snow
    if not type(app._impl).__module__.startswith('toga_android.'):
        return box
    app.android_eink_choice = toga.Switch('High contrast / E Ink',
        value=app.preferences.values['android_eink'] == 'true', style=Pack(height=48))
    box.add(switch_row(app, 'High contrast / E Ink', app.android_eink_choice,
        'Use black text on white, simpler panels, and clearer controls and selections. '
        'Overrides dark mode and reader colors. Images stay unchanged.'))
    app.android_eink_choice.on_change = app.change_android_eink
    return box
