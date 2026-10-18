"""One persisted magnifier percentage for image readers and app windows."""
from weakref import WeakKeyDictionary, WeakSet, ref

LEVELS = tuple(range(150, 251, 20))
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
    for choice, saved in tuple(_choices.items()):
        owner = saved()
        if owner is not None and owner.path == path:
            handler, choice.on_change = choice.on_change, None
            try:choice.value = str(value) + '%'
            finally:choice.on_change = handler


def save(preferences, value):
    if type(value) is not int or value not in LEVELS:
        raise ValueError('Choose 150–250%, in 20% steps.')
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
        canvas.magnifier_zoom = int(preferences.values['magnifier_zoom'])
        canvas.on_magnifier_zoom = changed
        _canvases[canvas] = ref(preferences)
    return view


def setting(app):
    import toga
    from toga.style import Pack
    preferences = app.preferences
    _preferences.add(preferences)
    choice = toga.Selection(items=[str(value)+'%' for value in LEVELS],
        value=preferences.values['magnifier_zoom']+'%', style=Pack(height=48))
    _choices[choice] = ref(preferences)
    def changed(widget, **kwargs):
        try:save(preferences, int(widget.value.removesuffix('%')))
        except (OSError, ValueError) as error:
            refresh(preferences)
            report(app, error)
    choice.on_change = changed
    return choice
