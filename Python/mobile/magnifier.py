"""One persisted magnifier percentage for image readers and app windows."""
from weakref import WeakKeyDictionary, WeakSet, ref

MIN_ZOOM, MAX_ZOOM, ZOOM_STEP = 150, 300, 10
LEVELS = tuple(range(MIN_ZOOM, MAX_ZOOM + 1, ZOOM_STEP))
RANGE_ERROR = 'Choose magnifier zoom from 150–300%, in 10 percentage point steps.'
_canvases = WeakKeyDictionary()
_choices = WeakKeyDictionary()
_preferences = WeakSet()


def refresh(preferences):
    """Broadcast an already loaded setting without writing it again."""
    _preferences.add(preferences)
    path = preferences.path
    value = int(preferences.values['magnifier_zoom'])
    for other in tuple(_preferences):
        if other is not preferences and other.path == path:
            other.reload()
    for canvas, saved in tuple(_canvases.items()):
        owner = saved()
        if owner is not None and owner.path == path:
            canvas.magnifier_zoom = value
    for choice, (saved, label, title) in tuple(_choices.items()):
        owner = saved()
        if owner is not None and owner.path == path:
            handler, choice.on_change = choice.on_change, None
            try:
                choice.value = value
                caption = label()
                if caption is not None:
                    caption.text = f'{title} · {value}%'
            finally:
                choice.on_change = handler


def save(preferences, value):
    if type(value) is not int or value not in LEVELS:
        raise ValueError(RANGE_ERROR)
    # Another app window may have saved unrelated settings in the meantime.
    preferences.reload()
    preferences.save(magnifier_zoom=str(value))
    refresh(preferences)


def report(app, error):
    import toga
    if app is not None and app.active_host:
        app.loop.create_task(app.main_window.dialog(toga.InfoDialog('Magnifier zoom was not saved', str(error))))


def bind(host, view):
    preferences = host.preferences
    app = ref(getattr(host, 'app', host))
    _preferences.add(preferences)
    def changed(canvas, value):
        try:
            save(preferences, value)
            return True
        except (OSError, ValueError) as error:
            report(app(), error)
            return False
    for canvas in getattr(view, 'canvases', [view]):
        canvas.configure_magnifier(MIN_ZOOM, MAX_ZOOM, ZOOM_STEP)
        canvas.magnifier_zoom = int(preferences.values['magnifier_zoom'])
        canvas.on_magnifier_zoom = changed
        _canvases[canvas] = ref(preferences)
    return view


def setting(app, title='Comic & PDF magnifier zoom'):
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN
    from .appearance import accessible_name
    from .reader_progress import style_slider
    from .settings.forms import SettingsLabel

    preferences = app.preferences
    _preferences.add(preferences)
    value = int(preferences.values['magnifier_zoom'])
    label = SettingsLabel(f'{title} · {value}%', style=Pack(font_weight='bold'))
    choice = app.magnifier_choice = toga.Slider(min=MIN_ZOOM, max=MAX_ZOOM,
        tick_count=len(LEVELS), value=value, style=Pack(height=56))
    accessible_name(choice, title)
    style_slider(choice)
    _choices[choice] = (ref(preferences), ref(label), title)

    def changed(widget, **kwargs):
        value = LEVELS[widget.tick_value - 1]
        if value == int(preferences.values['magnifier_zoom']):
            return
        try:
            save(preferences, value)
        except (OSError, ValueError) as error:
            refresh(preferences)
            report(app, error)

    choice.on_change = changed
    row = toga.Box(children=[label, choice], style=Pack(direction=COLUMN, margin_top=12))
    row._settings_managed_content = True
    return row
