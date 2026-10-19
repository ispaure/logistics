"""Dismiss native keyboards on outside taps without consuming the tap."""

_apple_delegate = None


def native_value(value):
    return value() if callable(value) else value


def _tuck_control(control, compact):
    mounted = getattr(control, '_keyboard_mount', None)
    if compact and mounted is None and control.parent is not None:
        parent = control.parent
        index = parent.children.index(control)
        following = parent.children[index + 1] if index + 1 < len(parent.children) else None
        control._keyboard_mount = parent, following, index
        # Pack.display does not remove native Android child views. Reparent
        # the same control so it frees space without leaving a touch overlay.
        parent.remove(control)
    elif not compact and mounted is not None:
        parent, following, index = mounted
        control._keyboard_mount = None
        if control.parent is None:
            index = parent.children.index(following) if following in parent.children else min(index, len(parent.children))
            parent.insert(index, control)


def _fit_toolbar(toolbar, compact):
    heights = getattr(toolbar, '_keyboard_heights', {})
    if compact:
        for control in toolbar.children:
            if control.style.height is not None and control.style.height > 44:
                heights.setdefault(control, control.style.height)
                control.style.height = 44
        toolbar._keyboard_heights = heights
    elif heights:
        toolbar._keyboard_heights = {}
        for control, height in heights.items():
            control.style.height = height


def _fit_source(editor, compact):
    native = getattr(editor._impl, 'native', None)
    if native is None or not hasattr(native, 'getPaddingTop'):
        return
    saved = getattr(editor, '_keyboard_padding', None)
    if compact:
        if saved is None:
            editor._keyboard_padding = native.getPaddingTop(), native.getPaddingBottom(), editor.style.margin_top
        if native.getPaddingTop() or native.getPaddingBottom():
            native.setPadding(native.getPaddingLeft(), 0, native.getPaddingRight(), 0)
        if editor.style.margin_top:
            editor.style.margin_top = 0
    elif saved is not None:
        editor._keyboard_padding = None
        top, bottom, margin = saved
        native.setPadding(native.getPaddingLeft(), top, native.getPaddingRight(), bottom)
        editor.style.margin_top = margin


def fit_editors(app):
    """Reserve the short Android IME viewport for text and its main toolbar."""
    adapter = getattr(getattr(app, 'native_host', None), 'adapter', None)
    if adapter is None or not hasattr(adapter, 'keyboard_chrome'):
        return
    compact = adapter.keyboard_chrome is not None
    for owner in tuple(getattr(app, 'text_views', {}).values()):
        _fit_toolbar(owner.toolbar, compact)
        _fit_source(owner.editor, compact)
        for control in (owner.source_tools, owner.status):
            _tuck_control(control, compact)
        margin = 0 if compact else 12
        if owner.document_view.style.margin_top != margin:
            owner.document_view.style.margin = margin
    manager = getattr(app, 'private_sessions', None)
    for owner in tuple(getattr(manager, 'controllers', {}).values()):
        footer = getattr(owner, 'crypt_markdown_footer', None)
        if footer is not None:
            _fit_toolbar(owner.reader_toolbar, compact)
            _fit_source(owner.crypt_text, compact)
            _tuck_control(footer, compact)


def install(app):
    if not type(app.main_window._impl).__module__.startswith('toga_iOS.'):
        return
    global _apple_delegate
    from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, SEL
    if _apple_delegate is None:
        class LogisticsKeyboardDismissal(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
            @objc_method
            def outsideTap_(self, gesture) -> None:
                pass

            @objc_method
            def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                touched = view = native_value(touch.view)
                # Text controls must keep selection, cursor and keyboard behavior.
                while view is not None:
                    if (view.isKindOfClass(ObjCClass('UITextField'))
                            or (view.isKindOfClass(ObjCClass('UITextView')) and native_value(view.editable))
                            or view.isKindOfClass(ObjCClass('WKWebView'))):
                        return False
                    view = native_value(view.superview)
                window = native_value(touched.window) if touched is not None else None
                if window is not None:
                    window.endEditing(True)
                # Observe only: buttons, scrolling and other gestures still win.
                return False
        _apple_delegate = LogisticsKeyboardDismissal
    app._keyboard_delegate = _apple_delegate.alloc().init()
    app._keyboard_tap = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(
        app._keyboard_delegate, action=SEL('outsideTap:'))
    app._keyboard_tap.delegate = app._keyboard_delegate
    app._keyboard_tap.cancelsTouchesInView = False
    app.main_window._impl.native.addGestureRecognizer(app._keyboard_tap)


def bind_browser(browser):
    """Android browser controls and empty space dismiss a focused search field."""
    if not type(browser.search._impl).__module__.startswith('toga_android.'):
        return
    from android.content import Context
    from android.view import View, MotionEvent, ViewGroup
    from android.widget import EditText
    from java import dynamic_proxy
    search = browser.search._impl.native

    class OutsideTouch(dynamic_proxy(View.OnTouchListener)):
        def onTouch(self, view, event):
            if event.getAction() == MotionEvent.ACTION_DOWN and search.hasFocus():
                search.clearFocus()
                manager = view.getContext().getSystemService(Context.INPUT_METHOD_SERVICE)
                manager.hideSoftInputFromWindow(search.getWindowToken(), 0)
            return False

    browser._keyboard_touch = OutsideTouch()

    def bind(view):
        if isinstance(view, EditText):
            return
        view.setOnTouchListener(browser._keyboard_touch)
        if isinstance(view, ViewGroup):
            for index in range(view.getChildCount()):
                bind(view.getChildAt(index))
    bind(browser.widget._impl.native)
