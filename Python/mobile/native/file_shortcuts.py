"""Bind file move commands to the native listing that owns keyboard focus."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from weakref import ref

_apple_responder = None


def bind(widget, invoke, *, focusable=True, blank=False):
    backend = widget.factory.Button.__module__
    if backend.startswith('toga_android.'):
        return _android_binding(widget._impl.native, invoke, focusable=focusable, blank=blank)


def _android_binding(native, invoke, *, focusable, blank):
    from android.view import KeyEvent, View
    from java import dynamic_proxy

    class FileKeys(dynamic_proxy(View.OnKeyListener)):
        def __init__(self):
            super().__init__()
            self.held = set()

        def onKey(self, view, code, event):
            if code not in (KeyEvent.KEYCODE_X, KeyEvent.KEYCODE_V):
                return False
            if event.getAction() == KeyEvent.ACTION_UP:
                handled = code in self.held
                self.held.discard(code)
                return handled
            if event.getAction() != KeyEvent.ACTION_DOWN or not event.hasModifiers(KeyEvent.META_CTRL_ON):
                return False
            if event.getRepeatCount():
                return code in self.held
            self.held.discard(code)
            if view.isShown() and view.hasWindowFocus() and invoke('x' if code == KeyEvent.KEYCODE_X else 'v'):
                self.held.add(code)
                return True
            return False

    if focusable:
        native.setFocusableInTouchMode(True)
    listener = FileKeys()
    native.setOnKeyListener(listener)
    if blank:
        class FocusOnClick(dynamic_proxy(View.OnClickListener)):
            def onClick(self, view):
                view.requestFocus()

        native.setOnClickListener(FocusOnClick())
    return listener


def _apple_binding(host, listings, invoke):
    from rubicon.objc import ObjCClass, SEL, objc_id, objc_method, objc_property, ns_from_py
    from commonUtils.ui.native.keyboard import native_value

    global _apple_responder
    if _apple_responder is None:
        class LogisticsFileKeys(ObjCClass('UIView')):
            invoke = objc_property(object)

            @objc_method
            def canBecomeFirstResponder(self) -> bool:
                return True

            @objc_method
            def keyCommands(self) -> objc_id:
                if not native_value(self.isFirstResponder):
                    return None
                Key = ObjCClass('UIKeyCommand')
                commands = []
                for key, title in (('x', 'Cut files'), ('v', 'Paste move here')):
                    command = Key.keyCommandWithInput(key, modifierFlags=1 << 20, action=SEL('logisticsMoveFiles:'))
                    command.discoverabilityTitle = title
                    commands.append(command)
                return ns_from_py(commands)

            @objc_method
            def logisticsMoveFiles_(self, command) -> None:
                if native_value(self.isFirstResponder) and native_value(self.window) is not None:
                    self.invoke(str(command.input))

            @objc_method
            def focusFileKeys_(self, gesture) -> None:
                if native_value(self.window) is not None:
                    self.becomeFirstResponder()

        _apple_responder = LogisticsFileKeys
    responder = _apple_responder.alloc().init()
    responder.invoke = invoke
    # Keep one responder on the retained browser when rows, tiles or the
    # empty state replace each other. Only the listing can give it focus.
    host.addSubview(responder)
    for widget in listings:
        native = widget._impl.native
        gesture = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(
            responder, action=SEL('focusFileKeys:'))
        gesture.cancelsTouchesInView = False
        native.userInteractionEnabled = True
        native.addGestureRecognizer(gesture)
        widget._file_key_binding = responder


def focus(widget):
    binding = getattr(widget, '_file_key_binding', None)
    if binding is None:
        return
    if widget.factory.Button.__module__.startswith('toga_iOS.'):
        binding.focusFileKeys(None)
    else:
        native = widget._impl.native
        if native.isShown():
            native.requestFocus()


def focused(widget):
    binding = getattr(widget, '_file_key_binding', None)
    if binding is None:
        return False
    if widget.factory.Button.__module__.startswith('toga_iOS.'):
        from commonUtils.ui.native.keyboard import native_value
        return native_value(binding.isFirstResponder)
    return widget._impl.native.hasFocus()


def install(browser, invoke):
    owner = ref(browser)

    def dispatch(key):
        current = owner()
        return current is not None and not current.closed and invoke(current, key)

    browser.file_key_dispatch = dispatch
    listings = (browser.native_list, browser._tile_scroll, browser.empty_label)
    if browser.widget.factory.Button.__module__.startswith('toga_iOS.'):
        _apple_binding(browser.widget._impl.native, listings, dispatch)
    else:
        for widget in listings:
            widget._file_key_binding = bind(widget, dispatch, blank=widget is browser.empty_label)
