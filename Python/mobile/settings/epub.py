"""One EPUB Settings page for the category and the reader shortcut."""
import sys

import toga
from toga.style import Pack

from features.books.mobile.typography import THEMES, font_families
from ..appearance import accessible_name, batch_surfaces, surface
from .forms import SettingsLabel, fit_section, save_boolean_switch, settings_presentation, switch_row
from .text import text_size


def epub(app, *, from_reader=False):
    status = SettingsLabel('') if from_reader else app.settings_status
    box = text_size(app, 'EPUB', 'epub_font_size', register=not from_reader, status=status)
    values = app.preferences.values

    def sync_category():
        if from_reader:
            section = app.settings_navigation.sections.built.get('EPUB')
            if section is not None:
                section._settings_on_open()

    def sync(control, value):
        handler = control.on_change
        control.on_change = None
        try:
            control.value = value
        finally:
            control.on_change = handler

    def add(label, key, control, decode=str, encode=str):
        accessible_name(control, label)

        def save(widget, **kwargs):
            try:
                value = encode(widget.value)
                if value != app.preferences.values[key]:
                    app.preferences.save(**{key: value})
                    sync_category()
            except (ValueError, OSError) as error:
                status.text = str(error)
                if isinstance(control, toga.Selection) or isinstance(error, OSError):
                    sync(control, decode(app.preferences.values[key]))
                return
            status.text = ''

        control.on_change = save
        box.add(SettingsLabel(label, style=Pack(font_weight='bold')), control)
        updates[key] = (control, decode)

    def select(label, key, items):
        add(label, key, toga.Selection(items=list(items), value=values[key], style=Pack(height=48)))

    def whole(value):
        if value is None or value != int(value):
            raise ValueError('Enter a whole number.')
        return str(int(value))

    updates = {'epub_font_size': (box.font_choice, str),
               'epub_justify': (box.justify_choice, lambda value: value == 'true')}
    select('Reading font', 'reading_font', sorted(set(font_families()) | {values['reading_font']}, key=str.casefold))
    add('Line spacing (%)', 'line_spacing', toga.NumberInput(min=100, max=220, step=5,
        value=int(values['line_spacing']), style=Pack(height=48)), int, whole)
    def width(value):
        return 0 if value == 'auto' else int(value)
    add('Maximum width (480–1400, or 0 for automatic)', 'reading_width', toga.NumberInput(min=0, max=1400, step=20,
        value=width(values['reading_width']), style=Pack(height=48)), width,
        lambda value: 'auto' if value == 0 else whole(value))
    select('Page margins', 'reading_margin', ('8', '16', '24', '32'))
    select('Theme (system follows device)', 'reading_theme', THEMES)
    box.volume_pages = None
    if sys.platform == 'android':
        key = 'epub_volume_pages'
        switch = box.volume_pages = toga.Switch('Volume buttons turn pages',
            value=values[key] == 'true', style=Pack(height=48))

        def save_volume(widget, **kwargs):
            if save_boolean_switch(app.preferences, widget, key, save_volume, status):
                sync_category()
                status.text = ''

        switch.on_change = save_volume
        box.add(switch_row(app, 'Volume buttons turn pages', switch,
            'Volume down goes to the next page. Volume up goes to the previous page. Only while reading.'))
        updates[key] = (switch, lambda value: value == 'true')

    def on_open():
        for key, (control, decode) in updates.items():
            value = decode(app.preferences.values[key])
            if control.value != value:
                sync(control, value)

    box.epub_controls = {key: control for key, (control, _) in updates.items()}
    box._settings_on_open = on_open
    if from_reader:
        box.add(status)
    return box


def show_from_reader(owner, *, provider=False):
    app = owner.app
    if (owner.cloud_busy if provider else owner.book_busy):
        return False
    with batch_surfaces():
        if not hasattr(app, 'settings_navigation'):
            app.show_settings(present=False)
        box = epub(app, from_reader=True)
        surface(box, radius=0, background='settings_background', outlined=False, eink_outlined=False)
        settings_presentation(box)
        fit_section(box, app.adaptive.content_width('settings', full=True))
        view = toga.ScrollContainer(horizontal=False, content=box, style=Pack(flex=1))
    if app.show_view(view, destination='settings', route='epub-settings', title='EPUB',
                     retain_private=owner if provider else None):
        from ..reading.epub_resume import bridge_for
        owner._epub_return_pending = True
        bridge = bridge_for(owner, provider)
        if bridge is not None:
            bridge.suspend_input()
        return True
    return False
