"""Persistent opt-in controls for the experimental outer-display accessory."""
import toga
from toga.style import Pack
from services.mobile_features import enabled

from ..reader_cover_display import BOOK_COVER, COMIC_COVER, native_bridge
from .forms import save_boolean_switch, switch_row


def available(app):
    return bool(getattr(app, '_hinge_status', 0) and native_bridge(app) is not None)


def controls(app, box):
    if not available(app):
        return
    status = app.settings_status
    for feature, key, title in (
        ('books', BOOK_COVER, 'Book cover on outer display'),
        ('comics', COMIC_COVER, 'Comic cover on outer display'),
    ):
        if not enabled(app.preferences, feature):
            continue
        add_switch(app, box, status, key, title)


def add_switch(app, box, status, key, title):
    switch = toga.Switch(title, value=app.preferences.values[key] == 'true', style=Pack(height=48))

    def save(widget, **kwargs):
        if save_boolean_switch(app.preferences, widget, key, save, status):
            status.text = ''
            from ..external_display import sync
            sync(app)

    switch.on_change = save
    box.add(switch_row(app, title, switch,
        'Experimental on iPhone Duo. This keeps the camera and outer display running while you read, '
        'which can drain the battery noticeably faster. The camera needs permission and shows a green '
        'indicator. It runs without a preview or recording. Session-only and protected documents are excluded.'))
