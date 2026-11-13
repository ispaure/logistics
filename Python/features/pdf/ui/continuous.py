"""Qt's continuous document view and its memory-only input."""
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import QScroller


class ContinuousPDFView(QPdfView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPageMode(QPdfView.PageMode.MultiPage)
        self.setPageSpacing(10)
        self.setZoomMode(QPdfView.ZoomMode.FitInView)
        QScroller.grabGesture(self.viewport(), QScroller.ScrollerGestureType.TouchGesture)

    def wheelEvent(self, event):
        # Trackpads provide pixel deltas. Qt's standard scroll bar handles
        # angle deltas from a mouse wheel, including partial wheel steps.
        delta = event.pixelDelta()
        if delta.isNull():
            super().wheelEvent(event)
            return
        QScroller.scroller(self.viewport()).stop()
        vertical = self.verticalScrollBar()
        horizontal = self.horizontalScrollBar()
        vertical.setValue(vertical.value() - delta.y())
        horizontal.setValue(horizontal.value() - delta.x())
        event.accept()

    def jump(self, index):
        QScroller.scroller(self.viewport()).stop()
        navigator = self.pageNavigator()
        if navigator.currentPage() == index:
            # A repeat jump also returns to the top of the selected page.
            navigator.currentPageChanged.emit(index)
        else:
            navigator.jump(index, QPointF())


def load_pdf(parent, data):
    buffer = QBuffer(parent)
    buffer.setData(QByteArray(data))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    document = QPdfDocument(parent)
    document.load(buffer)
    if document.status() != QPdfDocument.Status.Ready or not document.pageCount():
        document.close()
        buffer.close()
        buffer.setData(QByteArray())
        document.deleteLater()
        buffer.deleteLater()
        raise ValueError('Cannot open PDF. It may be damaged or password protected.')
    return document, buffer
