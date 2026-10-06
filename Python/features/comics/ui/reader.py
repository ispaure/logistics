"""Native single-page reader with lazy loading and direction-aware controls."""

from commonUtils.ui import pyside as qt
from .operations import Operation


class PageCanvas(qt.QWidget):
    def __init__(self):
        super().__init__()
        self.pixmap = qt.QPixmap()
        self.message = 'Loading page…'
        self.setMinimumSize(100, 100)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        if self.pixmap.isNull():
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20),
                             qt.Qt.AlignmentFlag.AlignCenter | qt.Qt.TextFlag.TextWordWrap, self.message)
        else:
            size = self.pixmap.size().scaled(self.size(), qt.Qt.AspectRatioMode.KeepAspectRatio)
            target = qt.QRect(qt.QPoint((self.width() - size.width()) // 2,
                                      (self.height() - size.height()) // 2), size)
            painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target, self.pixmap)


def read_image(pages, index):
    data, _ = pages.read_page(index)
    buffer = qt.QBuffer()
    buffer.setData(data)
    buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
    reader = qt.QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.width() * size.height() > 40_000_000:
        reader.setScaledSize(size.scaled(6000, 6000, qt.Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    if image.isNull():
        raise ValueError(reader.errorString() or 'This page could not be displayed')
    return image


class ComicReaderWindow(qt.QMainWindow):
    def __init__(self, pages):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(pages.path.name)
        self.resize(950, 900)
        self.pages = pages
        self.page = 0
        self.busy = False
        self.closing = False
        self.pending_page = None
        container = qt.QWidget()
        layout = qt.QVBoxLayout(container)
        header = qt.QHBoxLayout()
        title = qt.QLabel(pages.path.name)
        title.setTextFormat(qt.Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        header.addWidget(title, 1)
        self.direction = qt.QLabel('Right to left' if pages.right_to_left else 'Left to right')
        header.addWidget(self.direction)
        fullscreen = qt.QPushButton('Full Screen')
        fullscreen.clicked.connect(self.toggle_fullscreen)
        header.addWidget(fullscreen)
        layout.addLayout(header)
        self.canvas = PageCanvas()
        layout.addWidget(self.canvas, 1)
        controls = qt.QHBoxLayout()
        self.previous_button = qt.QPushButton('Previous')
        self.next_button = qt.QPushButton('Next')
        self.previous_button.clicked.connect(lambda: self.go(self.page - 1))
        self.next_button.clicked.connect(lambda: self.go(self.page + 1))
        controls.addWidget(self.next_button if pages.right_to_left else self.previous_button)
        self.progress = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.progress.setAccessibleName('Reading progress')
        self.progress.setLayoutDirection(qt.Qt.LayoutDirection.LeftToRight)
        self.progress.setInvertedAppearance(pages.right_to_left)
        self.progress.setRange(0, max(1, len(pages.pages) - 1))
        self.progress.setEnabled(len(pages.pages) > 1)
        self.progress.valueChanged.connect(self.go)
        controls.addWidget(self.progress, 1)
        self.progress_label = qt.QLabel()
        controls.addWidget(self.progress_label)
        controls.addWidget(self.previous_button if pages.right_to_left else self.next_button)
        layout.addLayout(controls)
        self.setCentralWidget(container)
        forward = -1 if pages.right_to_left else 1
        for key, callback in (('Right', lambda: self.go(self.page + forward)),
                              ('Left', lambda: self.go(self.page - forward)),
                              ('Down', lambda: self.go(self.page + 1)),
                              ('Up', lambda: self.go(self.page - 1)),
                              ('Home', lambda: self.go(0)),
                              ('End', lambda: self.go(len(self.pages.pages) - 1)),
                              ('F11', self.toggle_fullscreen), ('Escape', self.leave_fullscreen)):
            shortcut = qt.QShortcut(qt.QKeySequence(key), self)
            shortcut.activated.connect(callback)
        self.go(0)

    def go(self, index):
        if self.closing:
            return
        index = max(0, min(index, len(self.pages.pages) - 1))
        self.page = index
        blocker = qt.QSignalBlocker(self.progress)
        self.progress.setValue(index)
        blocker.unblock()
        self.progress_label.setText(f'{index + 1} / {len(self.pages.pages)} · {(index + 1) / len(self.pages.pages):.0%}')
        self.previous_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < len(self.pages.pages) - 1)
        self.canvas.pixmap = qt.QPixmap()
        self.canvas.message = 'Loading page…'
        self.canvas.update()
        if self.busy:
            self.pending_page = index
            return
        self.pending_page = None
        self.busy = True
        self.operation = Operation(lambda: read_image(self.pages, index), self)
        self.operation.completed.connect(lambda image, error: self._loaded(index, image, error))
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, index, image, error):
        if self.closing or index != self.page:
            return
        if error:
            self.canvas.message = f'Cannot read page: {error}'
        else:
            self.canvas.pixmap = qt.QPixmap.fromImage(image)
        self.canvas.update()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.closing:
            self.close()
        elif self.pending_page is not None:
            self.go(self.pending_page)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def shutdown(self):
        self.closing = True
        if self.busy:
            self.operation.wait()

    def closeEvent(self, event):
        self.closing = True
        if self.busy:
            self.hide()
            event.ignore()
        else:
            event.accept()
