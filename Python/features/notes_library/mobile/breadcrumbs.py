"""A shrinking breadcrumb viewport that reveals its end after native layout."""
from weakref import WeakMethod

import toga

_apple_pan_target = None


def fit_labels(labels, width, measure):
    """Share the row among every crumb while the touch targets fit."""
    separator = 12 * max(0, len(labels) - 1)
    full = sum(max(44, measure(label) + 12) for label in labels)
    if full + separator <= width or 34 * len(labels) + separator > width:
        return labels, 44
    # Reserve room for each remaining crumb, and give unused room to longer names.
    remaining = width - separator
    result = []
    for index, label in enumerate(labels):
        available = remaining / (len(labels) - index)
        if measure(label) + 12 > available:
            prefix = label
            while prefix and measure(prefix + '…') + 12 > available:
                prefix = prefix[:-1]
            label = prefix + '…'
        result.append(label)
        remaining -= max(34, measure(label) + 12)
    return result, 34


class BreadcrumbScroll(toga.ScrollContainer):
    # Native Toga scroll views default to a 100-unit intrinsic minimum. Four
    # adjacent controls need this viewport to yield that space on narrow phones.
    _MIN_WIDTH = 0
    _MIN_HEIGHT = 0

    def __init__(self, *args, **kwargs):
        self._pending_end = None
        self._end_generation = 0
        self._needs_end = False
        super().__init__(*args, **kwargs)
        if type(self._impl).__module__.startswith('toga_iOS.'):
            # Keep ownership of horizontal drags even when the path fits.
            self._impl.native.alwaysBounceHorizontal = True

    def watch_swipes(self, expand):
        handler = WeakMethod(expand)

        def expand_if_active(delta):
            callback = handler()
            return callback is not None and callback(delta)

        backend = type(self._impl).__module__
        if backend.startswith('toga_iOS.'):
            from rubicon.objc import ObjCClass, SEL, objc_method
            global _apple_pan_target
            if _apple_pan_target is None:
                class LogisticsBreadcrumbPan(ObjCClass('NSObject')):
                    @objc_method
                    def moved_(self, gesture) -> None:
                        if int(gesture.state) != 3:
                            return
                        delta = gesture.translationInView(gesture.view)
                        if abs(delta.x) >= 10 and abs(delta.x) > abs(delta.y):
                            self.expand(delta.x)
                _apple_pan_target = LogisticsBreadcrumbPan
            self._pan_target = _apple_pan_target.alloc().init()
            self._pan_target.expand = expand_if_active
            self._impl.native.panGestureRecognizer.addTarget(self._pan_target, action=SEL('moved:'))
        elif backend.startswith('toga_android.'):
            from android.view import View, ViewConfiguration
            from java import dynamic_proxy
            native = self._impl.hScrollView
            slop = ViewConfiguration.get(native.getContext()).getScaledTouchSlop()
            previous = getattr(self._impl, 'hScrollListener', None)
            class Touch(dynamic_proxy(View.OnTouchListener)):
                start = None

                def onTouch(self, view, event):
                    action = event.getActionMasked()
                    if action == 0:
                        self.start = event.getRawX(), event.getRawY()
                        if view != native:
                            view.getParent().requestDisallowInterceptTouchEvent(True)
                    elif action == 2 and self.start is not None:
                        dx = event.getRawX() - self.start[0]
                        dy = event.getRawY() - self.start[1]
                        if abs(dx) > slop and abs(dx) > abs(dy):
                            self.start = None
                            if expand_if_active(dx):
                                return True
                    elif action in (1, 3, 5):
                        self.start = None
                    return bool(previous.onTouch(view, event)) if view == native and previous else False

            self._swipe_touch = Touch()
            native.setOnTouchListener(self._swipe_touch)

    def watch_button(self, button):
        listener = getattr(self, '_swipe_touch', None)
        if listener is not None:
            button._impl.native.setOnTouchListener(listener)

    def cancel_pending_end(self):
        self._end_generation += 1
        self._needs_end = False
        if self._pending_end is not None:
            self._pending_end.cancel()
            self._pending_end = None

    def _layout_ready(self):
        backend = type(self._impl).__module__
        if backend.startswith('toga_android.'):
            native, content = self._impl.native, self._impl.native_content
            if native.isLayoutRequested() or content.isLayoutRequested():
                return False
            density = native.getResources().getDisplayMetrics().density
            width, content_width = native.getWidth() / density, content.getWidth() / density
        elif backend.startswith('toga_iOS.'):
            native = self._impl.native
            width, content_width = float(native.bounds.size.width), float(native.contentSize.width)
        else:
            return True
        expected = max(width, self.content.layout.width)
        return (width > 0 and abs(width - self.layout.content_width) <= 1
                and abs(content_width - expected) <= 1)

    def retry_end(self, loop, *, valid):
        """Resume an unmounted request on a later presentation refresh."""
        if self._needs_end and self._pending_end is None:
            self.reveal_end(loop, valid=valid)

    def reveal_end(self, loop, *, valid):
        """Wait for measured content; retire stale requests on navigation/close."""
        self.cancel_pending_end()
        self._needs_end = True
        generation = self._end_generation
        def reveal(attempt=0):
            self._pending_end = None
            if generation != self._end_generation:
                return
            if not valid():
                self._needs_end = False
                return
            if not self._layout_ready():
                # Yield to UIKit/Android layout instead of clamping to a stale
                # zero maximum on the first asyncio turn. Bound retries to avoid
                # retaining a hidden/unmounted viewport indefinitely.
                if attempt < 60:
                    self._pending_end = loop.call_later(1 / 60, reveal, attempt + 1)
                return
            self._needs_end = False
            self.horizontal_position = self.max_horizontal_position
        self._pending_end = loop.call_soon(reveal)
