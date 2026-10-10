"""Book-wide reading progress without eagerly rendering every chapter."""
from bisect import bisect_right
from commonUtils.ui import pyside as qt


class BookProgress(qt.QWidget):
    requested = qt.Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setAccessibleName('Whole book progress; click to jump')
        self.boundaries = [0, 1]
        self.markers = []
        self.fraction = 0
        self.setCursor(qt.Qt.CursorShape.PointingHandCursor)
        self.setEnabled(False)

    def set_book(self, book):
        weights = [max(1, book.resource_sizes.get(path, 1)) for path in book.spine]
        total = sum(weights)
        self.boundaries = [0]
        for weight in weights:
            self.boundaries.append(self.boundaries[-1] + weight / total)
        self.markers = []
        for entry in book.chapters:
            index = book.spine.index(entry.path)
            start, end = self.boundaries[index:index + 2]
            offset = book.section_offsets.get((entry.path, entry.fragment), 0)
            self.markers.append((start + (end - start) * offset, entry.depth,
                                 entry.label, entry.fragment))
        self.setEnabled(True)
        self.update()

    def set_position(self, chapter, position):
        start, end = self.boundaries[chapter:chapter + 2]
        self.fraction = start + (end - start) * max(0, min(1, position))
        self.setToolTip(f'{self.fraction:.0%} through the book · click to jump')
        self.update()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.RenderHint.Antialiasing)
        track = qt.QRectF(4, 11, max(1, self.width() - 8), 6)
        painter.setPen(qt.Qt.PenStyle.NoPen)
        painter.setBrush(self.palette().color(qt.QPalette.ColorRole.Mid))
        painter.drawRoundedRect(track, 3, 3)
        filled = qt.QRectF(track); filled.setWidth(track.width() * self.fraction)
        painter.setBrush(self.palette().color(qt.QPalette.ColorRole.Highlight))
        painter.drawRoundedRect(filled, 3, 3)
        painter.setPen(qt.QPen(self.palette().color(qt.QPalette.ColorRole.Text), 1))
        for fraction, depth, label, fragment in self.markers:
            height = max(5, 16 - depth * 4)
            x = track.left() + track.width() * fraction
            painter.drawLine(qt.QPointF(x, 14 - height / 2), qt.QPointF(x, 14 + height / 2))

    def mouseReleaseEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton and self.isEnabled():
            fraction = max(0, min(1, (event.position().x() - 4) / max(1, self.width() - 8)))
            chapter = min(len(self.boundaries) - 2, bisect_right(self.boundaries, fraction) - 1)
            start, end = self.boundaries[chapter:chapter + 2]
            self.requested.emit(chapter, (fraction - start) / (end - start))
