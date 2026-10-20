"""Native floating speech surface, independent of the document's layout tree."""

_apple_dismissal = None


def apple_dismissal_class():
    global _apple_dismissal
    if _apple_dismissal is None:
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method
        from .keyboard import native_value

        class LogisticsSpeechDismissal(ObjCClass('NSObject'), protocols=(ObjCProtocol('UIGestureRecognizerDelegate'),)):
            @objc_method
            def outsideTap_(self, gesture) -> None:
                if self.overlay is not None:
                    self.overlay.panel.hide()

            @objc_method
            def gestureRecognizer_shouldRecognizeSimultaneouslyWithGestureRecognizer_(self, gesture, other) -> bool:
                return True

            @objc_method
            def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                if self.overlay is None or self.overlay.container is None:
                    return False
                native = self.overlay.container.native
                anchor = getattr(getattr(self.overlay.anchor, '_impl', None), 'native', None)
                view = native_value(touch.view)
                while view is not None:
                    if view == native or (anchor is not None and view == anchor):
                        return False
                    view = native_value(view.superview)
                return True

        _apple_dismissal = LogisticsSpeechDismissal
    return _apple_dismissal


class SpeechOverlay:
    def __init__(self, panel, owner, app, *, anchor=None):
        self.anchor = anchor
        self.panel = panel
        self.reposition = lambda: None
        self.container = self.popup = None
        self.dismissal = self.outside_tap = self.window = None
        backend = type(panel._impl).__module__
        if app is not None:
            panel.app, panel.window = app, app.main_window
        if backend.startswith('toga_iOS.'):
            self.apple(app)
        elif backend.startswith('toga_android.'):
            self.android(owner)
        if app is not None:
            from weakref import WeakSet
            if not hasattr(app, '_speech_overlays'):
                app._speech_overlays = WeakSet()
            app._speech_overlays.add(self)
        # The dummy backend retains the same detached panel for host UI tests.

    def apple(self, app):
        from rubicon.objc import CGRect, ObjCClass, SEL
        from toga_iOS.container import Container
        window = app.main_window._impl.native
        self.container = Container(on_refresh=lambda c: None)
        native = self.container.native
        native.backgroundColor = ObjCClass('UIColor').secondarySystemBackgroundColor()
        native.layer.cornerRadius = 16
        native.layer.shadowOpacity = .25
        native.layer.shadowRadius = 8
        native.accessibilityLabel = 'Read aloud controls'

        self.last_size = None

        def layout(container):
            bounds = window.bounds.size
            insets = window.safeAreaInsets
            width = min(320, bounds.width - insets.left - insets.right - 24)
            height = self.panel.overlay_height
            frame = CGRect((bounds.width - insets.right - width - 12, insets.top + 52), (width, height))
            if native.frame != frame:
                native.frame = frame
            size = (width, height)
            if self.last_size != size:
                self.last_size = size
                self.panel.refresh()

        self.reposition = lambda: layout(self.container)
        native.autoresizingMask = 2  # flexible left margin; remeasure on rotation
        self.container.on_native_layout = layout
        self.container.content = self.panel._impl
        window.addSubview(native)
        layout(self.container)
        self.window = window
        self.dismissal = apple_dismissal_class().alloc().init()
        self.dismissal.overlay = self
        self.outside_tap = ObjCClass('UITapGestureRecognizer').alloc().initWithTarget(
            self.dismissal, action=SEL('outsideTap:'))
        self.outside_tap.delegate = self.dismissal
        # Consume dismissal taps, including native navigation-bar copies of the
        # speaker button, so their touch-up cannot reopen the dismissed panel.
        self.outside_tap.cancelsTouchesInView = True
        window.addGestureRecognizer(self.outside_tap)

    def android(self, owner):
        from android.graphics.drawable import ColorDrawable
        from android.view import Gravity
        from android.widget import FrameLayout, PopupWindow
        from toga_android.container import Container
        from java import dynamic_proxy
        context = owner._impl.native.getContext()
        root = FrameLayout(context)
        self.container = Container()
        self.container.init_container(root)
        width = min(self.container.scale_in(320), context.getResources().getDisplayMetrics().widthPixels - self.container.scale_in(24))
        height = self.container.scale_in(self.panel.overlay_height)
        self.container.set_content(self.panel._impl)
        self.container.resize_content(width, height)
        self.popup = PopupWindow(root, width, height, True)
        # Use the current theme's surface color, including dark mode.
        from android.util import TypedValue
        value = TypedValue()
        context.getTheme().resolveAttribute(16842801, value, True)  # colorBackground
        self.popup.setBackgroundDrawable(ColorDrawable(value.data))
        self.popup.setElevation(self.container.scale_in(12))
        self.popup.setOutsideTouchable(True)
        overlay = self

        class Dismissal(dynamic_proxy(PopupWindow.OnDismissListener)):
            def onDismiss(self):
                overlay.panel.hide()

        self.dismissal = Dismissal()
        self.popup.setOnDismissListener(self.dismissal)
        self.popup.showAtLocation(owner._impl.native, Gravity.TOP | Gravity.END,
                                  self.container.scale_in(12), self.container.scale_in(96))
        self.panel.refresh()

        def reposition():
            if self.container is None:
                return
            width = min(self.container.scale_in(320), context.getResources().getDisplayMetrics().widthPixels - self.container.scale_in(24))
            height = self.container.scale_in(self.panel.overlay_height)
            self.container.resize_content(width, height)
            self.popup.update(width, height)
        self.reposition = reposition

    def close(self):
        self.reposition = lambda: None
        if self.outside_tap is not None:
            self.window.removeGestureRecognizer(self.outside_tap)
            self.outside_tap.delegate = None
            self.dismissal.overlay = None
            self.outside_tap = self.window = None
        if self.popup is not None:
            self.popup.setOnDismissListener(None)
            self.popup.dismiss()
            self.popup = None
        self.dismissal = None
        if self.container is not None:
            if hasattr(self.container, 'clear_content'):
                self.container.clear_content()
            else:
                self.container.content = None
                self.container.native.removeFromSuperview()
            self.container = None
