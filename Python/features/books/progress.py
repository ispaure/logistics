"""Book-wide reading progress without eagerly rendering every chapter."""
from bisect import bisect_right
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
            chapter = min(len(self.boundaries) - 2, bisect_right(self.boundaries, fraction) - 1)
            start, end = self.boundaries[chapter:chapter + 2]
            self.requested.emit(chapter, (fraction - start) / (end - start))
