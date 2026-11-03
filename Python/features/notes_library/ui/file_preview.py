"""Library-owned read-only file preview with asynchronous PDF page navigation."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress


class PreviewBrowser(qt.QStackedWidget):
    def __init__(self):
        super().__init__()
        self.content, self.pixmap = None, qt.QPixmap()
        self.video = None
        self.details = qt.QTextBrowser()
        self.details.setOpenLinks(False)
        self.details.setOpenExternalLinks(False)
        self.scroll = qt.QScrollArea()
        self.scroll.setAlignment(qt.Qt.AlignmentFlag.AlignHCenter | qt.Qt.AlignmentFlag.AlignTop)
        self.canvas = qt.QLabel()
        self.canvas.setStyleSheet('background: white')
        self.scroll.setWidget(self.canvas)
        self.addWidget(self.details)
        self.addWidget(self.scroll)

    def set_content(self, content):
        self.clear()
        self.content = content
        if content.image:
            data = content.image
            buffer = qt.QBuffer()
            buffer.setData(data)
            buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
            from features.images.ui.decoding import read_oriented
            self.pixmap = qt.QPixmap.fromImage(read_oriented(qt.QImageReader(buffer), data))
            if self.pixmap.isNull():
                self.details.setPlainText('Cannot decode this image.')
                self.setCurrentWidget(self.details)
                return
            self.setCurrentWidget(self.scroll)
            self.fit_image()
            self.scroll.verticalScrollBar().setValue(0)
        else:
            self.details.setHtml(content.html())
            self.setCurrentWidget(self.details)

    def toHtml(self):
        return self.content.html() if self.content is not None else ''

    def toPlainText(self):
        return self.details.toPlainText()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_image()

    def fit_image(self):
        if not self.pixmap.isNull():
            width = min(self.pixmap.width(), max(1, self.scroll.viewport().width() - 16))
            scaled = self.pixmap.scaledToWidth(width, qt.Qt.TransformationMode.SmoothTransformation)
            self.canvas.setPixmap(scaled)
            self.canvas.resize(scaled.size())

    def clear(self):
        if self.video is not None:
            self.removeWidget(self.video)
            self.video.retire()
            self.video = None
        self.content, self.pixmap = None, qt.QPixmap()
        self.canvas.clear()
        self.details.clear()


class LibraryFilePreview(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.preview, self.index = None, 0
        self.retired = []
        layout = qt.QVBoxLayout(self)
        row = qt.QHBoxLayout()
        self.previous = qt.QPushButton('Previous page')
        self.following = qt.QPushButton('Next page')
        self.page_label = qt.QLabel()
        self.previous.clicked.connect(lambda: self.show_page(self.index - 1))
        self.following.clicked.connect(lambda: self.show_page(self.index + 1))
        for widget in (self.previous, self.page_label, self.following):
            row.addWidget(widget)
        layout.addLayout(row)
        self.browser = PreviewBrowser()
        layout.addWidget(self.browser, 1)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self.completed)
        layout.addWidget(self.operation)
        self.operation.hide()

    @property
    def busy(self):
        return self.operation.busy

    def hideEvent(self, event):
        if self.browser.video is not None:
            self.browser.video.player.pause()
        super().hideEvent(event)

    def load(self, preview, content):
        self.clear()
        self.preview, self.index = preview, 0
        self.browser.set_content(content)
        if preview.video_url:
            from pathlib import PurePosixPath
            from commonUtils.ui.markdown.videos import VideoCard
            self.browser.video = VideoCard(self.browser, preview.video_url, PurePosixPath(preview.path).name)
            self.browser.addWidget(self.browser.video)
            self.browser.setCurrentWidget(self.browser.video)
        self.update_controls()

    def update_controls(self):
        count = self.preview.count if self.preview else 0
        self.previous.setVisible(count > 1)
        self.following.setVisible(count > 1)
        self.page_label.setVisible(count > 1)
        self.page_label.setText(f'Page {self.index + 1} of {count}')
        self.previous.setEnabled(not self.busy and self.index > 0)
        self.following.setEnabled(not self.busy and self.index + 1 < count)

    def show_page(self, index):
        if self.busy or self.preview is None or not 0 <= index < self.preview.count:
            return
        preview = self.preview
        self.operation.start(lambda report, cancelled: (index, preview.content(index)), message='Reading page…')
        self.update_controls()

    def completed(self, result, error):
        self.operation.hide()
        for preview in self.retired:
            preview.close()
        self.retired.clear()
        if self.preview is not None:
            if not error and not self.operation.cancelled.is_set():
                index, content = result
                self.browser.set_content(content)
                self.index = index
            self.update_controls()
            if error:
                self.page_label.setText(error)
        self.idle.emit()

    def clear(self):
        self.operation.request_cancel()
        self.browser.clear()
        if self.preview is not None:
            preview, self.preview = self.preview, None
            # Page workers must finish before the library retires their bytes.
            if self.busy:
                self.retired.append(preview)
            else:
                preview.close()
