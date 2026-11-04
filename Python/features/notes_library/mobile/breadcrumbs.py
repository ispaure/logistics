"""A shrinking breadcrumb viewport that reveals its end after native layout."""
import toga


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
