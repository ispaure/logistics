"""Paint LibVLC's SDR memory frames in Qt without a second native video window."""

from commonUtils.ui import pyside as qt


class ImageFrame:
    """The frame operations used by the shared desktop presentation owner."""
    def __init__(self, image):
        self.image = image

    def isValid(self):
        return not self.image.isNull()

    def toImage(self):
        return self.image


class ImageSink(qt.QObject):
    """VLC already decoded the pixels; no Qt Multimedia backend is needed."""
    videoFrameChanged = qt.Signal(object)
    videoSizeChanged = qt.Signal(qt.QSize)

    def __init__(self, parent):
        super().__init__(parent)
        self.frame = ImageFrame(qt.QImage())

    def videoSize(self):
        return self.frame.toImage().size()

    def setImage(self, image):
        previous = self.videoSize()
        self.frame = ImageFrame(image)
        if image.size() != previous:
            self.videoSizeChanged.emit(image.size())
        self.videoFrameChanged.emit(self.frame)


class VideoSurface(qt.QWidget):
    def __init__(self):
        super().__init__()
        self.sink = ImageSink(self)
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
