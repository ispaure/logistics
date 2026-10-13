"""Native screenshot thumbnails. Markdown resource loading stays disabled."""
from commonUtils.ui import pyside as qt
from .screenshots import image_bytes


class ScreenshotView(qt.QLabel):
    def __init__(self, record, parent=None, *, preview=False):
        super().__init__(parent)
        self.record = record
        self.original = qt.QPixmap()
        self.original.loadFromData(image_bytes(record), 'PNG')
        self.preview = preview
        self.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName('Attached screenshot')
        self.setToolTip('Click to view screenshot')
        self.setCursor(qt.Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(1)
        self.setFixedHeight(90 if preview else 240)
        if preview:
            self.setFixedWidth(120)
        self.fit()

    def fit(self):
        if self.original.isNull():
            self.setText('Screenshot could not be displayed')
        else:
            self.setPixmap(self.original.scaled(max(1, self.width()), self.height(),
                qt.Qt.AspectRatioMode.KeepAspectRatio, qt.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def mousePressEvent(self, event):
        if event.button() == qt.Qt.MouseButton.LeftButton and not self.original.isNull():
            dialog = qt.QDialog(self)
            dialog.setWindowTitle('Screenshot')
            layout = qt.QVBoxLayout(dialog)
            scroll = qt.QScrollArea()
            label = qt.QLabel()
            label.setPixmap(self.original)
            scroll.setWidget(label)
            layout.addWidget(scroll)
            copy = qt.QPushButton('Copy image')
            copy.clicked.connect(lambda: qt.QApplication.clipboard().setPixmap(self.original))
            layout.addWidget(copy)
            dialog.resize(min(1000, self.original.width() + 50), min(800, self.original.height() + 90))
            dialog.exec()
            dialog.deleteLater()
        else:
            super().mousePressEvent(event)
