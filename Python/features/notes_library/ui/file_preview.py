"""Library-owned read-only file preview with continuous PDF scrolling."""
from commonUtils.ui import pyside as qt
from PySide6.QtCore import QByteArray
from features.pdf.ui.continuous import ContinuousPDFView, load_pdf


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
    def __init__(self, parent):
        super().__init__(parent)
        self.preview, self.index = None, 0
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
        self.pdf = ContinuousPDFView()
        self.pdf.pageNavigator().currentPageChanged.connect(self.sync_page)
        self.browser.addWidget(self.pdf)
        self.pdf_buffer = None

    def hideEvent(self, event):
        if self.browser.video is not None:
            self.browser.video.player.pause()
        super().hideEvent(event)

    def load(self, preview, content):
        self.clear()
        self.preview, self.index = preview, 0
        if preview.document is not None:
            document, self.pdf_buffer = load_pdf(self.pdf, preview.document.data)
            self.pdf.setDocument(document)
            self.pdf.verticalScrollBar().setValue(0)
            self.pdf.jump(0)
            self.browser.setCurrentWidget(self.pdf)
        else:
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
        self.previous.setEnabled(self.index > 0)
        self.following.setEnabled(self.index + 1 < count)

    def show_page(self, index):
        if self.pdf.document() is not None and 0 <= index < self.pdf.document().pageCount():
            self.pdf.jump(index)

    def sync_page(self, index):
        self.index = index
        self.update_controls()

    def clear(self):
        document = self.pdf.document()
        if document is not None:
            self.pdf.setDocument(None)
            document.close()
            document.deleteLater()
            self.pdf_buffer.close()
            self.pdf_buffer.setData(QByteArray())
            self.pdf_buffer.deleteLater()
            self.pdf_buffer = None
        self.browser.clear()
        if self.preview is not None:
            self.preview.close()
            self.preview = None
