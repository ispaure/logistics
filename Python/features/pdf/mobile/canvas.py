"""Vertical page gestures, deliberately independent of comic reading direction."""
import toga

_target_class = None


def swipe_direction(dx, dy):
    if abs(dy) >= 50 and abs(dy) > abs(dx):
        return 1 if dy < 0 else -1
    return 0


class PDFCanvas(toga.ImageView):
    def __init__(self, *args, on_page=None, **kwargs):
        self.on_page = on_page
        super().__init__(*args, **kwargs)

    def page(self, direction):
        if self.on_page is not None and self.image is not None:
            self.on_page(direction)

    def _create(self):
        backend = self.factory.ImageView.__module__
        if backend.startswith('toga_iOS.'):
            from toga_iOS.widgets.imageview import ImageView
            from rubicon.objc import ObjCClass, objc_method, objc_property, SEL
            global _target_class
            if _target_class is None:
                class LogisticsPDFGestures(ObjCClass('NSObject')):
                    owner = objc_property(object, weak=True)

                    @objc_method
                    def swipe_(target, gesture) -> None:
                        if target.owner is not None:
                            target.owner.interface.page(1 if gesture.direction == 4 else -1)
                _target_class = LogisticsPDFGestures
            class AppleView(ImageView):
                def create(inner):
                    super().create()
                    inner.target = _target_class.alloc().init()
                    inner.target.owner = inner
                    inner.native.userInteractionEnabled = True
                    inner.native.accessibilityLabel = 'PDF page. Swipe up for next page, down for previous page.'
                    for direction in (4, 8):
                        gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(inner.target, action=SEL('swipe:'))
                        gesture.direction = direction
                        inner.native.addGestureRecognizer(gesture)
            return AppleView(interface=self)
        if backend.startswith('toga_android.'):
            from toga_android.widgets.imageview import ImageView
            from java import jclass, dynamic_proxy
            class AndroidView(ImageView):
                def create(inner):
                    super().create()
                    inner.start = None
                    class Listener(dynamic_proxy(jclass('android.view.View$OnTouchListener'))):
                        def onTouch(listener, native, event):
                            action = event.getActionMasked()
                            if action == 0:
                                inner.start = event.getX(), event.getY()
                            elif action == 1 and inner.start is not None:
                                x, y = inner.start
                                inner.start = None
                                direction = swipe_direction(event.getX() - x, event.getY() - y)
                                if direction:
                                    inner.interface.page(direction)
                                native.performClick()
                            elif action in (3, 5):
                                inner.start = None
                            return True
                    inner.listener = Listener()
                    inner.native.setOnTouchListener(inner.listener)
                    inner.native.setContentDescription('PDF page. Swipe up for next page, down for previous page.')
            return AndroidView(interface=self)
        return super()._create()

    def dispose(self):
        self.on_page = None
        self.image = None
        if hasattr(self._impl, 'target'):
            self._impl.native.userInteractionEnabled = False
        if hasattr(self._impl, 'listener'):
            self._impl.native.setOnTouchListener(None)
            self._impl.listener = None


class PDFTools:
    """Compact page jump and text search, leaving the reading area clear."""
    def __init__(self, controls):
        from toga.style import Pack
        from toga.style.pack import COLUMN
        self.panel = toga.Box(children=controls, style=Pack(direction=COLUMN, margin_top=8))
        self.button = toga.Button('Pages & search', on_press=self.toggle, style=Pack(height=44))
        self.widget = toga.Box(children=[self.button], style=Pack(direction=COLUMN))

    def toggle(self, widget=None, **kwargs):
        if self.panel in self.widget.children:
            self.close()
        else:
            self.widget.add(self.panel)
            self.button.text = 'Hide pages & search'

    def close(self):
        if self.panel in self.widget.children:
            self.widget.remove(self.panel)
        self.button.text = 'Pages & search'
