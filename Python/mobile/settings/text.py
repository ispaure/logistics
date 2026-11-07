"""Shared font-size and justification panel for Markdown, Text and EPUB."""
import toga
from toga.style import Pack
from toga.style.pack import ROW, CENTER
from ..preferences import DEFAULTS
from .forms import page, SettingsLabel, switch_row, group_rows, OPTION_FONT_SIZE


def text_size(app, title, key, *, register=True, status=None):
    box = page(title)
    if status is None:
        status = app.settings_status
    from ..control_icons import icon_button
    box.add(SettingsLabel(title + ' font size', style=Pack(font_weight='bold')))
    choice = toga.Selection(items=[str(size) for size in range(12, 33)],
        value=app.preferences.values[key], style=Pack(height=48))
    if register:
        setattr(app, key + '_choice', choice)
    box.font_choice = choice
    def save_size(widget, **kwargs):
        from ..font_scaling import refresh
        if choice.value == app.preferences.values[key]:
            return
        try:
            app.preferences.save(**{key: choice.value})
        except (OSError, ValueError) as error:
            choice.on_change = None
            try:
                choice.value = app.preferences.values[key]
            finally:
                choice.on_change = save_size
            status.text = str(error)
            return
        refresh(app)
        status.text = ''
    choice.on_change = save_size

    def reset(widget, **kwargs):
        choice.value = DEFAULTS[key]

    choice.style.flex = 1
    choice.style.font_size = OPTION_FONT_SIZE
    reset_button = icon_button('reset', f'Reset {title} font size to default', on_press=reset)
    reset_button.style.margin_left = 8
    row = toga.Box(children=[choice, reset_button], style=Pack(direction=ROW, align_items=CENTER))
    row._settings_size_row = True
    group = group_rows([row])
    group._settings_managed_content = True
    box.add(group)
    box.add(SettingsLabel('Pinch while reading to change this size.'))
    if title in {'Markdown', 'EPUB'}:
        justify_key = title.lower() + '_justify'
        justify = toga.Switch('Justify text', value=app.preferences.values[justify_key] == 'true', style=Pack(height=48))
        if register:
            setattr(app, justify_key + '_choice', justify)
        box.justify_choice = justify
        box.add(switch_row(app, 'Justify text', justify,
            'Align text to both the left and right edges.'))
        from .forms import save_boolean_switch

        def save_justify(widget, **kwargs):
            from ..font_scaling import refresh
            if save_boolean_switch(app.preferences, widget, justify_key, save_justify, status):
                refresh(app)
                status.text = ''

        justify.on_change = save_justify
    return box
