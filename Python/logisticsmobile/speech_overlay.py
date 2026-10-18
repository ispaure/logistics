"""Native floating speech surface, independent of the document's layout tree."""


class SpeechOverlay:
    def __init__(self, panel, owner, app):
        self.panel = panel
        self.reposition = lambda: None
        self.container = self.popup = None
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
        from rubicon.objc import CGRect, ObjCClass
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

    def android(self, owner):
        from android.graphics.drawable import ColorDrawable
        from android.view import Gravity
        from android.widget import FrameLayout, PopupWindow
        from toga_android.container import Container
        context = owner._impl.native.getContext()
        root = FrameLayout(context)
        self.container = Container()
        self.container.init_container(root)
        width = min(self.container.scale_in(320), context.getResources().getDisplayMetrics().widthPixels - self.container.scale_in(24))
        height = self.container.scale_in(self.panel.overlay_height)
        self.container.set_content(self.panel._impl)
        self.container.resize_content(width, height)
        self.popup = PopupWindow(root, width, height, False)
        # Use the current theme's surface color, including dark mode.
        from android.util import TypedValue
        value = TypedValue()
        context.getTheme().resolveAttribute(16842801, value, True)  # colorBackground
        self.popup.setBackgroundDrawable(ColorDrawable(value.data))
        self.popup.setElevation(self.container.scale_in(12))
        self.popup.setOutsideTouchable(False)
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
        if self.popup is not None:
            self.popup.dismiss()
            self.popup = None
        if self.container is not None:
            if hasattr(self.container, 'clear_content'):
                self.container.clear_content()
            else:
                self.container.content = None
                self.container.native.removeFromSuperview()
            self.container = None
