"""Toga ImageView extension with native bounded pinch/pan and fit-page paging."""
import toga

_scroll_class = None


def apple_scroll_class():
    global _scroll_class
    if _scroll_class is None:
        from rubicon.objc import ObjCClass, ObjCProtocol, objc_method, objc_property
        from rubicon.objc.runtime import send_super
        from rubicon.objc import objc_id
        from ctypes import c_bool
        class LogisticsComicScroll(ObjCClass('UIScrollView'), protocols=(ObjCProtocol('UIScrollViewDelegate'), ObjCProtocol('UIGestureRecognizerDelegate'))):
            owner = objc_property(object, weak=True)

            @objc_method
            def layoutSubviews(self) -> None:
                send_super(LogisticsComicScroll, self, 'layoutSubviews')
                if self.owner is not None:
                    self.owner.layout_image()

            @objc_method
            def viewForZoomingInScrollView_(self, scroll):
                return self.owner.picture if self.owner is not None else None

            @objc_method
            def scrollViewDidZoom_(self, scroll) -> None:
                if self.owner is not None:
                    self.owner.center_image()

            @objc_method
            def gestureRecognizerShouldBegin_(self, gesture) -> bool:
                if self.owner is not None and gesture in self.owner.swipes:
                    return self.zoomScale <= 1.05
                return bool(send_super(LogisticsComicScroll, self, 'gestureRecognizerShouldBegin:', gesture,
                                       restype=c_bool, argtypes=[objc_id]))

            @objc_method
            def gestureRecognizer_shouldReceiveTouch_(self, gesture, touch) -> bool:
                x = touch.locationInView(self).x
                return 24 < x < self.bounds.size.width - 24

            @objc_method
            def pageSwipe_(self, gesture) -> None:
                if self.owner is not None and self.zoomScale <= 1.05:
                    self.owner.interface.page(-1 if gesture.direction == 1 else 1)
        _scroll_class = LogisticsComicScroll
    return _scroll_class


def apple_backend(interface):
    from toga_iOS.widgets.imageview import ImageView
    from rubicon.objc import ObjCClass, CGRect, CGSize, UIEdgeInsets, SEL
    class Backend(ImageView):
        def create(self):
            self.picture = ObjCClass('UIImageView').alloc().init()
            self.picture.contentMode = 1
            self.last_size = None
            self.native = apple_scroll_class().alloc().init()
            self.native.owner = self
            self.native.delegate = self.native
            self.native.minimumZoomScale, self.native.maximumZoomScale = 1, 6
            self.native.bounces = False
            self.native.accessibilityLabel = 'Comic page. Pinch to zoom; swipe at fit-page size to change pages.'
            self.native.isAccessibilityElement = True
            self.native.clipsToBounds = True
            self.native.addSubview(self.picture)
            self.native.setTranslatesAutoresizingMaskIntoConstraints(False)
            self.native.setAutoresizesSubviews(False)
            self.swipes = []
            for direction in (1, 2):
                gesture = ObjCClass('UISwipeGestureRecognizer').alloc().initWithTarget(self.native, action=SEL('pageSwipe:'))
                gesture.direction, gesture.delegate = direction, self.native
                self.native.addGestureRecognizer(gesture)
                self.native.panGestureRecognizer.requireGestureRecognizerToFail(gesture)
                self.swipes.append(gesture)
            self.add_constraints()

        def set_image(self, image):
            self.native.setZoomScale(1, animated=False)
            self.picture.image = image._impl.native if image else None
            self.last_size = None
            self.layout_image()

        def layout_image(self):
            size = self.native.bounds.size
            key = (size.width, size.height)
            image = getattr(self.interface, 'image', None)
            if image is None or min(key) <= 0 or key == self.last_size:
                return
            self.last_size = key
            zoom = float(self.native.zoomScale)
            self.native.setZoomScale(1, animated=False)
            scale = min(size.width / image.width, size.height / image.height)
            width, height = image.width * scale, image.height * scale
            self.picture.frame = CGRect((0, 0), (width, height))
            self.native.contentSize = CGSize(width, height)
            self.native.setZoomScale(zoom, animated=False)
            self.center_image()

        def center_image(self):
            bounds, content = self.native.bounds.size, self.native.contentSize
            self.native.contentInset = UIEdgeInsets(max(0, (bounds.height - content.height) / 2),
                max(0, (bounds.width - content.width) / 2), 0, 0)
    return Backend(interface=interface)


def android_backend(interface):
    from toga_android.widgets.imageview import ImageView
    from java import jclass, dynamic_proxy
    View = jclass('io.github.ispaure.logistics.ComicView')
    class Backend(ImageView):
        def create(self):
            self.native = View(self._native_activity)
            self.native.setContentDescription('Comic page. Pinch to zoom; swipe at fit-page size to change pages.')
            owner = self
            class Listener(dynamic_proxy(View.PageListener)):
                def page(self, direction):
                    owner.interface.page(direction)
            self.listener = Listener()
            self.native.setPageListener(self.listener)

        def rehint(self):
            super().rehint()
            self.native.setScaleType(self.native.ScaleType.MATRIX)
    return Backend(interface=interface)


class ComicCanvas(toga.ImageView):
    def __init__(self, *args, on_page=None, **kwargs):
        self.on_page = on_page
        super().__init__(*args, **kwargs)

    def _create(self):
        backend = self.factory.ImageView.__module__
        if backend.startswith('toga_iOS.'):
            return apple_backend(self)
        if backend.startswith('toga_android.'):
            return android_backend(self)
        return super()._create()

    def page(self, direction):
        if self.on_page is not None and self.image is not None:
            self.on_page(direction)

    @property
    def zoom_scale(self):
        backend = type(self._impl).__module__
        native = getattr(self._impl, 'native', None)
        if native is None:
            return 1
        if hasattr(self._impl, 'picture'):
            return float(native.zoomScale)
        if backend == __name__:
            return float(native.getZoom())
        return 1

    def set_zoom(self, value):
        value = max(1, min(6, float(value)))
        native = getattr(self._impl, 'native', None)
        if hasattr(self._impl, 'picture'):
            native.setZoomScale(value, animated=False)
        elif native is not None and type(self._impl).__module__ == __name__:
            native.setZoom(value)

    def fit_page(self, widget=None, **kwargs):
        self.set_zoom(1)
