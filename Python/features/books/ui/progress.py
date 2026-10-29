"""Book-wide reading progress without eagerly rendering every chapter."""
from features.books.locations import book_boundaries, book_location, LayoutPages
from commonUtils.ui import pyside as qt


class BookProgress(qt.QWidget):
    requested = qt.Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setAccessibleName('Whole book progress; click to jump')
        self.boundaries = [0, 1]
        self.markers = []
        self.fraction = 0
        self.setCursor(qt.Qt.CursorShape.PointingHandCursor)
        self.setEnabled(False)
        self.book = self.owner = None
        self.pages = LayoutPages(0)
        self.count_error = False
        self.counter = qt.QTimer(self)
        self.counter.setSingleShot(True)
        self.counter.timeout.connect(self._count_next)

    def set_book(self, book):
        self.counter.stop()
        self.book = book
        self.pages = LayoutPages(len(book.spine))
        self.count_error = False
        self.boundaries = book_boundaries(book)
        self._update_markers()
        self.setEnabled(False)
        self.update()

    def _update_markers(self):
        self.markers = []
        for entry in self.book.chapters:
            index = self.book.spine.index(entry.path)
            start, end = self.boundaries[index:index + 2]
            offset = self.book.section_offsets.get((entry.path, entry.fragment), 0)
            self.markers.append((start + (end - start) * offset, entry.depth,
                                 entry.label, entry.fragment))

    def update_position(self, owner):
        if owner._closing:
            return dict(fraction=None, text='Closing book…', mobile='Closing book…')
        if self.book is not owner.book:
            self.set_book(owner.book)
        self.owner = owner
        text = owner.text
        key = (text.viewport().width(), text.page_height, text.font().toString(),
               text.styleSheet(), owner.spacing.value())
        if self.pages.reset(key):
            self.counter.stop()
            self.count_error = False
        self.pages.record(owner._current, text.page_count)
        position = self.pages.position(owner._current, text.page_index, owner.spread.step)
        if self.pages.complete:
            self.counter.stop()
            self.boundaries = self.pages.boundaries
            self._update_markers()
            self.fraction = position['fraction']
            self.setEnabled(True)
            self.setToolTip(position['text'] + ' · click to jump')
        else:
            self.setEnabled(False)
            self.fraction = 0
            self.setToolTip('Counting pages for this font and window size')
            if not self.counter.isActive() and not self.count_error:
                self.counter.start(60)
            if self.count_error:
                position['text'] = 'Page count unavailable · ' + f'Chapter {owner._current + 1} of {len(self.pages.counts)}'
                position['mobile'] = position['text']
        self.update()
        return position

    def _count_next(self):
        owner = self.owner
        if owner is None or owner.book is not self.book or owner._closing or self.pages.complete:
            return
        if owner.worker is not None or owner._loading:
            self.counter.start(100)
            return
        from features.books.ui.text_view import BookText
        from features.books.ui.content import chapter_html
        measure = BookText(self)
        measure.setAttribute(qt.Qt.WidgetAttribute.WA_DontShowOnScreen)
        try:
            index = self.pages.counts.index(None)
            measure.book = self.book
            measure.setStyleSheet(owner.text.styleSheet())
            measure.setFont(owner.text.font())
            measure.document().setDefaultFont(owner.text.document().defaultFont())
            measure.resize(owner.text.size())
            measure.show()
            path = self.book.spine[index]
            base = qt.QUrl(); base.setScheme('epub'); base.setPath('/' + path)
            measure.document().setBaseUrl(base)
            measure.setHtml(chapter_html(self.book, path, foreground=owner._rendered_colors[1],
                                        spacing=owner.spacing.value()))
            measure.repaginate()
            self.pages.record(index, measure.page_count)
        except (OSError, ValueError):
            self.count_error = True
        finally:
            measure.clear()
            measure.book = None
            measure.hide()
            measure.deleteLater()
        owner._position_changed()

    def clear(self):
        self.counter.stop()
        self.book = self.owner = None
        self.pages = LayoutPages(0)
        self.markers = []
        self.fraction = 0
        self.setEnabled(False)
        self.update()

    def set_position(self, chapter, position):
        start, end = self.boundaries[chapter:chapter + 2]
        self.fraction = start + (end - start) * max(0, min(1, position))
        self.setToolTip(f'{self.fraction:.0%} through the book · click to jump')
        self.update()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        track = self._track_rect()
        painter.setPen(qt.Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(qt.QPalette.ColorRole.Mid))
        painter.drawRoundedRect(track, 3, 3)
        filled = qt.QRectF(track); filled.setWidth(track.width() * self.fraction)
        painter.setBrush(self.palette().color(qt.QPalette.ColorRole.Highlight))
        painter.drawRoundedRect(filled, 3, 3)
        for fraction, depth, label, fragment in self.markers:
            height = self._marker_height(depth)
            role = qt.QPalette.ColorRole.Highlight if fraction <= self.fraction else qt.QPalette.ColorRole.Mid
            painter.setPen(qt.QPen(self.palette().color(role), 1))
            x = track.left() + track.width() * fraction
            painter.drawLine(qt.QPointF(x, track.center().y() - height / 2), qt.QPointF(x, track.center().y() + height / 2))

        painter.setPen(qt.Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(qt.QPalette.ColorRole.Highlight))
        painter.drawEllipse(qt.QPointF(track.left() + track.width() * self.fraction,
                                      track.center().y()), 5, 5)

    def _track_rect(self):
        return qt.QRectF(6, self.height() / 2 - 3, max(1, self.width() - 12), 6)

    @staticmethod
    def _marker_height(depth):
        return max(8, 14 - depth * 4)

    def mouseReleaseEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton and self.isEnabled():
            track = self._track_rect()
            fraction = max(0, min(1, (event.position().x() - track.left()) / track.width()))
            if self.pages.complete:
                chapter, page = self.pages.locate(fraction)
                position = page / max(1, self.pages.counts[chapter] - 1)
            else:
                chapter, position = book_location(self.boundaries, fraction)
            self.requested.emit(chapter, position)
