"""Dismiss native keyboards on outside taps without consuming the tap."""

_apple_delegate = None


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
                view = touch.view
                # Text controls must keep selection, cursor and keyboard behavior.
                while view is not None:
                    if (view.isKindOfClass(ObjCClass('UITextField'))
                            or (view.isKindOfClass(ObjCClass('UITextView')) and view.editable)
                            or view.isKindOfClass(ObjCClass('WKWebView'))):
                        return False
                    view = view.superview
                touch.view.window.endEditing(True)
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
