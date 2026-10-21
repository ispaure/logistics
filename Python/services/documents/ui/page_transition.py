"""Short content-only page slides for the three desktop document readers."""
from PySide6.QtCore import QEvent, QEasingCurve, QVariantAnimation, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget


class PageSlide(QWidget):
    """Move the outgoing page over live replacement content, never the toolbar."""
    def __init__(self, surface):
        super().__init__(surface)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()
        self.image = QPixmap()
        self.direction = 0
        self.vertical = False
        self.progress = 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(220)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self.advance)
        self.animation.finished.connect(self.clear)
        surface.installEventFilter(self)

    def begin(self, direction, *, vertical=False):
        self.clear()
        surface = self.parentWidget()
        if not direction or not surface.isVisible() or surface.size().isEmpty():
            return
        self.direction = 1 if direction > 0 else -1
        self.vertical = vertical
        self.image = surface.grab()

    def finish(self):
        if self.image.isNull():
            return
        self.setGeometry(self.parentWidget().rect())
        self.progress = 0.0
        self.show()
        self.raise_()
        self.animation.start()

    def advance(self, value):
        self.progress = float(value)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        offset = -self.direction * self.progress
        painter.drawPixmap(0 if self.vertical else round(offset * self.width()),
                           round(offset * self.height()) if self.vertical else 0, self.image)

    def clear(self):
        self.animation.stop()
        self.hide()
        self.image = QPixmap()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Hide, QEvent.Type.Close):
            self.clear()
        return False


def page_slide(surface):
    slide = getattr(surface, '_document_page_slide', None)
    if slide is None:
        slide = surface._document_page_slide = PageSlide(surface)
    return slide
