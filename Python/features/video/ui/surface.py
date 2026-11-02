"""Paint LibVLC's SDR memory frames in Qt without a second native video window."""

from commonUtils.ui import pyside as qt
from PySide6.QtMultimedia import QVideoSink


class VideoSurface(qt.QWidget):
    def __init__(self):
        super().__init__()
        self.sink = QVideoSink(self)
        self.image = qt.QImage()
        self.aspect = qt.Qt.AspectRatioMode.KeepAspectRatio
        self.sink.videoFrameChanged.connect(self.present)
        self.setAccessibleName('Video')

    def videoSink(self):
        return self.sink

    def present(self, frame):
        self.image = frame.toImage() if frame.isValid() else qt.QImage()
        self.update()

    def setAspectRatioMode(self, mode):
        self.aspect = mode
        self.update()

    def paintEvent(self, event):
        with qt.QPainter(self) as painter:
            painter.fillRect(self.rect(), qt.Qt.GlobalColor.black)
            if not self.image.isNull():
                size = self.image.size().scaled(self.size(), self.aspect)
                target = qt.QRectF((self.width() - size.width()) / 2,
                    (self.height() - size.height()) / 2, size.width(), size.height())
                painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(target, self.image)
