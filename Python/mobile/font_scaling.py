"""Per-format text sizing, shared by settings and native pinch gestures."""
import logging
import weakref
from commonUtils.ui.native.text_size import TextSizeBinding

FONT_KEYS = ('markdown_font_size', 'text_font_size', 'epub_font_size')


def font_key(kind):
    return 'markdown_font_size' if kind in {'markdown', '.md', '.markdown'} else 'epub_font_size' if kind in {'epub', '.epub'} else 'text_font_size'


def font_size(host, kind):
    return int(host.preferences.values.get(font_key(kind), host.preferences.values.get('font_size', '16')))


def refresh(host):
    app = getattr(host, 'app', host)
    for binding in list(getattr(app, '_font_bindings', ())):
        binding.apply(font_size(app, binding.kind()))
    for key in FONT_KEYS:
        choice = getattr(app, key + '_choice', None)
        if choice is not None and choice.value != app.preferences.values[key]:
            handler = choice.on_change
            choice.on_change = None
            choice.value = app.preferences.values[key]
            choice.on_change = handler
    for key in ('markdown_justify', 'epub_justify'):
        choice = getattr(app, key + '_choice', None)
        value = app.preferences.values.get(key, 'false') == 'true'
        if choice is not None and choice.value != value:
            handler = choice.on_change
            choice.on_change = None
            choice.value = value
            choice.on_change = handler


def bind(host, widget, kind, *, web=False, formatted=None):
    """The widget retains its listener; the app only keeps weak registrations."""
    app = getattr(host, 'app', host)
    current = getattr(widget, '_font_binding', None)
    if current is not None and not current.closed:
        current.attach_load()
        return current
    binding = widget._font_binding = FontBinding(app, widget, kind, web=web, formatted=formatted)
    if not hasattr(app, '_font_bindings'):
        app._font_bindings = weakref.WeakSet()
    app._font_bindings.add(binding)
    binding.install()
    binding.attach_load()
    return binding


class FontBinding(TextSizeBinding):
    def __init__(self, app, widget, kind, *, web=False, formatted=None):
        self.app = weakref.ref(app)
        self.kind = kind if callable(kind) else lambda: kind
        owner, target = weakref.ref(app), weakref.ref(widget)
        def alive():
            widget = target()
            return (owner() is not None and widget is not None
                    and not getattr(widget, 'private_closed', False)
                    and not getattr(widget, 'closed', False))
        def saved(size):
            current = owner()
            if current is not None:
                current.preferences.save(**{font_key(self.kind()): str(size)})
        def alignment():
            current = owner()
            key = font_key(self.kind()).replace('_font_size', '_justify')
            return 'justify' if current is not None and current.preferences.values.get(key, 'false') == 'true' else 'start'
        def report(error):
            logging.getLogger(__name__).warning('Could not save text size: %s', error)
            status = getattr(owner(), 'settings_status', None)
            if status is not None:
                status.text = str(error)
        super().__init__(widget, loop=app.loop,
            get_size=lambda: font_size(owner(), self.kind()) if owner() is not None else 16,
            save_size=saved, changed=lambda: refresh(owner()) if owner() is not None else None,
            active=lambda: owner() is not None and owner().active_host, alive=alive,
            alignment=alignment, alignment_variable='--logistics-text-align',
            web=web, formatted=formatted, on_error=report,
            previous_touch=getattr(widget, '_keyboard_touch', None))
