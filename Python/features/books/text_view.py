"""Restricted archive-local resource loading for Qt EPUB rich text."""
from commonUtils.ui import pyside as qt
from .epub import BookError, resolve_href
from commonUtils.ui.page_wheel import PageWheel


class BookText(qt.QTextBrowser):
    """Load images only from the current EPUB, never URLs or local disk paths."""
    pageTurn = qt.Signal(int)
    paginationChanged = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.book = None
        self.wheel = PageWheel()
        self.navigation_enabled = False
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setAccessibleName('Book chapter')
        self.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._page = 0
        self._adjusting_range = False
        self.verticalScrollBar().rangeChanged.connect(self._page_range_changed)

    @property
    def page_height(self):
        return max(1, self.viewport().height())

    @property
    def page_count(self):
        return max(1, self.document().pageCount())

    @property
    def page_index(self):
        return min(self.page_count - 1, self._page)

    def _page_range_changed(self, *args):
        if self._adjusting_range:
            return
        self._adjusting_range = True
        try:
            self.verticalScrollBar().setRange(0, (self.page_count - 1) * self.page_height)
            self.verticalScrollBar().setValue(self.page_index * self.page_height)
        finally:
            self._adjusting_range = False

    def repaginate(self):
        # Qt's paginated layout breaks between text lines instead of clipping a
        # sentence at the bottom of a screen. The scrollbar is an internal page
        # offset only; users navigate via page turns.
        self.document().setPageSize(qt.QSizeF(max(1, self.viewport().width()), self.page_height))
        self.document().markContentsDirty(0, self.document().characterCount())
        self.document().documentLayout().documentSize()

    def show_page(self, index):
        # QTextEdit normally aligns a short final page to the bottom of its
        # content. Allow its full page offset so backward/forward turns remain
        # aligned even when the last page contains only a few lines.
        self._page = max(0, min(index, self.page_count - 1))
        self._page_range_changed()
        self.viewport().update()
        self.paginationChanged.emit()

    def location(self):
        return self.cursorForPosition(qt.QPoint(0, 0)).position()

    def show_location(self, offset):
        offset = max(0, min(int(offset), self.document().characterCount() - 1))
        block = self.document().findBlock(offset)
        line = block.layout().lineForTextPosition(offset - block.position())
        y = self.document().documentLayout().blockBoundingRect(block).top()
        if line.isValid():
            y += line.y()
        self.show_page(int(y // self.page_height))

    def resizeEvent(self, event):
        offset = self.location() if self.book else 0
        super().resizeEvent(event)
        self.repaginate()
        if self.book:
            self.show_location(offset)
        # Font/theme changes and splitter resizing can invalidate the backing
        # store after this resize callback. Repaint the newly paginated page once
        # the parent layout has also settled.
        qt.QTimer.singleShot(0, self.viewport(), self.viewport().update)

    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
            event.accept()
            return
        navigation_keys = (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right, qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down,
                           qt.Qt.Key.Key_PageUp, qt.Qt.Key.Key_PageDown, qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End, qt.Qt.Key.Key_Space)
        if not self.navigation_enabled and event.key() in navigation_keys:
            event.accept()
            return
        if event.key() == qt.Qt.Key.Key_Space and event.modifiers() == qt.Qt.KeyboardModifier.ShiftModifier:
            self.pageTurn.emit(-1)
            event.accept()
            return
        if event.modifiers() == qt.Qt.KeyboardModifier.NoModifier:
            if event.key() in (qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End):
                self.show_page(0 if event.key() == qt.Qt.Key.Key_Home else self.page_count - 1)
                event.accept()
                return
            forward = (qt.Qt.Key.Key_Right, qt.Qt.Key.Key_PageDown, qt.Qt.Key.Key_Space)
            backward = (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_PageUp)
            if event.key() in forward + backward:
                self.pageTurn.emit(1 if event.key() in forward else -1)
                event.accept()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        event.accept()
        if self.navigation_enabled:
            direction = self.wheel.direction(event)
            if direction:
                self.pageTurn.emit(direction)

    def loadResource(self, kind, url):
        if not self.book or kind != qt.QTextDocument.ResourceType.ImageResource:
            return None
        if url.scheme() != 'epub' or url.host():
            return None
        try:
            path, _ = resolve_href('', url.path(qt.QUrl.ComponentFormattingOption.FullyEncoded).lstrip('/'))
            data = self.book.read(path)
            buffer = qt.QBuffer()
            buffer.setData(qt.QByteArray(data))
            buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
            reader = qt.QImageReader(buffer)
            size = reader.size()
            if not size.isValid() or size.width() * size.height() > 40_000_000:
                return None
            image = reader.read()
            bounds = qt.QSize(max(100, self.viewport().width() - 48), max(100, self.viewport().height() - 48))
            if image.width() > bounds.width() or image.height() > bounds.height():
                image = image.scaled(bounds, qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation)
            return image
        except (OSError, BookError):
            return None
