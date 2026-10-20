"""Per-format text sizing, shared by settings and native pinch gestures."""
import logging
import inspect
import math
import weakref

FONT_KEYS = ('markdown_font_size', 'text_font_size', 'epub_font_size')
_apple_target = None


def native_backend(widget):
    # CodeInput and private WebViews supply subclasses outside Toga's namespace.
    return getattr(widget, 'backend_name', None) or next(
        (base.__module__ for base in type(widget._impl).__mro__
         if base.__module__.startswith(('toga_iOS.', 'toga_android.'))),
        type(widget._impl).__module__)


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
    if current is not None:
        current.attach_load()
        return current
    binding = widget._font_binding = FontBinding(app, widget, kind, web=web, formatted=formatted)
    if not hasattr(app, '_font_bindings'):
        app._font_bindings = weakref.WeakSet()
    app._font_bindings.add(binding)
    binding.install()
    binding.attach_load()
    return binding


class FontBinding:
    def __init__(self, app, widget, kind, *, web=False, formatted=None):
        self.app = weakref.ref(app)
        self.widget = weakref.ref(widget)
        self.kind = kind if callable(kind) else lambda: kind
        self.web = web
        self.formatted = weakref.ref(formatted) if formatted else lambda: None
        self.start = None
        self.size = None
        self.task = None

    def gesture(self, state, scale=1):
        app = self.app()
        if app is None or self.widget() is None or not app.active_host:
            return
        if state == 'begin':
            self.disable_web_zoom()
            self.start = font_size(app, self.kind())
            self.size = self.start
        elif self.start is not None and state == 'change' and math.isfinite(scale) and scale > 0:
            self.size = min(32, max(12, int(self.start * scale + .5)))
            self.apply(self.size)
        elif self.start is not None and state in {'end', 'cancel'}:
            size, self.start = self.size, None
            if state == 'end' and size != font_size(app, self.kind()):
                try:
                    app.preferences.save(**{font_key(self.kind()): str(size)})
                except (OSError, ValueError) as error:
                    logging.getLogger(__name__).warning('Could not save text size: %s', error)
                    status = getattr(app, 'settings_status', None)
                    if status is not None:
                        status.text = str(error)
            refresh(app)

    def apply(self, size):
        widget, app = self.widget(), self.app()
        if widget is None or app is None or getattr(widget, 'private_closed', False):
            return
        formatted = self.formatted()
        if formatted is not None:
            if formatted.closed:
                return
            formatted.font_size = size
        self.size = size
        if not self.web:
            widget.style.font_size = size
        elif self.task is None or self.task.done():
            self.task = app.loop.create_task(self.apply_web())

    async def apply_web(self):
        applied = None
        try:
            while True:
                widget = self.widget()
                app = self.app()
                if widget is None or app is None or getattr(widget, 'private_closed', False):
                    return
                formatted = self.formatted()
                if formatted is not None and formatted.closed:
                    return
                key = font_key(self.kind()).replace('_font_size', '_justify')
                alignment = 'justify' if app.preferences.values.get(key, 'false') == 'true' else 'start'
                current = (self.size, alignment)
                if applied == current:
                    return
                applied = current
                # Reflow the existing DOM: retain editor selection, undo and book anchor.
                await widget.evaluate_javascript(
                    "(()=>{const viewport=document.querySelector('meta[name=viewport]');"
                    "if(viewport)viewport.content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no';"
                    f"document.body.style.fontSize='{applied[0]}px';"
                    f"document.documentElement.style.setProperty('--logistics-text-align','{alignment}');"
                    "window.dispatchEvent(new Event('resize'));})()")
        except Exception:
            logging.getLogger(__name__).debug('Text surface retired during font update', exc_info=True)

    def disable_web_zoom(self):
        widget = self.widget()
        if self.web and widget is not None and native_backend(widget).startswith('toga_iOS.'):
            # WebKit creates its scroll pinch recognizer lazily after loading.
            pinch = widget._impl.native.scrollView.pinchGestureRecognizer
            if pinch is not None:
                if hasattr(self, 'recognizer') and getattr(self, '_web_pinch', None) != pinch:
                    # WebKit may re-enable zoom during layout. Its recognizer
                    # must wait for our text-size gesture to fail as well.
                    pinch.requireGestureRecognizerToFail(self.recognizer)
                    self._web_pinch = pinch
                pinch.enabled = False

    def attach_load(self):
        widget = self.widget()
        if not self.web or widget is None or getattr(self, '_load_handler', None) is widget.on_webview_load:
            return
        previous = widget.on_webview_load
        binding = weakref.ref(self)
        async def loaded(widget, **kwargs):
            result = previous(**kwargs)
            if inspect.isawaitable(result):
                await result
            current = binding()
            if current is not None and current.app() is not None:
                current.disable_web_zoom()
                current.apply(font_size(current.app(), current.kind()))
        widget.on_webview_load = loaded
        self._load_handler = widget.on_webview_load

    def install(self):
        widget = self.widget()
        backend = native_backend(widget)
        if backend.startswith('toga_iOS.'):
            self.install_apple(widget._impl.native)
        elif backend.startswith('toga_android.'):
            self.install_android(widget._impl.native)

    def install_apple(self, native):
        global _apple_target
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property, SEL
        if _apple_target is None:
            class LogisticsTextPinch(ObjCClass('NSObject'), protocols=[ObjCProtocol('UIGestureRecognizerDelegate')]):
                binding = objc_property(object, weak=True)

                @objc_method
                def changed_(self, gesture) -> None:
                    states = {1: 'begin', 2: 'change', 3: 'end', 4: 'cancel', 5: 'cancel'}
                    if int(gesture.state) in states:
                        self.binding.gesture(states[int(gesture.state)], float(gesture.scale))

                @objc_method
                def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                    return not bool(other.isKindOfClass(ObjCClass('UIPinchGestureRecognizer')))
            _apple_target = LogisticsTextPinch
        self.target = _apple_target.new()
        self.target.binding = self
        self.recognizer = ObjCClass('UIPinchGestureRecognizer').alloc().initWithTarget(self.target, action=SEL('changed:'))
        self.recognizer.delegate = self.target
        self.recognizer.cancelsTouchesInView = True
        self.disable_web_zoom()
        native.addGestureRecognizer(self.recognizer)

    def install_android(self, native):
        from java import dynamic_proxy
        from android.view import View, MotionEvent
        binding = weakref.proxy(self)
        previous = getattr(self.widget(), '_keyboard_touch', None)
        class Touch(dynamic_proxy(View.OnTouchListener)):
            def __init__(self):
                super().__init__()
                self.distance = None
                self.scaling = False

            def onTouch(self, view, event):
                action = event.getActionMasked()
                if action == MotionEvent.ACTION_DOWN:
                    self.scaling, self.distance = False, None
                if event.getPointerCount() >= 2 and action != MotionEvent.ACTION_POINTER_UP:
                    distance = math.hypot(event.getX(0) - event.getX(1), event.getY(0) - event.getY(1))
                    if self.distance is None and distance > 0:
                        self.distance, self.scaling = distance, True
                        binding.gesture('begin')
                        # Cancel caret/scroll tracking before taking this gesture.
                        cancel = MotionEvent.obtain(event)
                        cancel.setAction(MotionEvent.ACTION_CANCEL)
                        view.onTouchEvent(cancel)
                        cancel.recycle()
                    if self.distance:
                        view.getParent().requestDisallowInterceptTouchEvent(True)
                        binding.gesture('change', distance / self.distance)
                if self.scaling:
                    if action in (MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL, MotionEvent.ACTION_POINTER_UP):
                        binding.gesture('cancel' if action == MotionEvent.ACTION_CANCEL else 'end')
                        self.distance = None
                    return True
                return bool(previous.onTouch(view, event)) if previous is not None else False
        self.listener = Touch()
        if self.web:
            native.getSettings().setSupportZoom(False)
        native.setOnTouchListener(self.listener)
