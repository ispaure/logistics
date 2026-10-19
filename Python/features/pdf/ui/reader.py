"""Independent Qt PDF reader with vertical, single-page navigation."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QEvent, QPoint
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from features.pdf.document import read_pdf


class PDFWindow(qt.QMainWindow):
    document_editor_id = 'pdf'
    document_editor_name = 'PDF Reader'

    def __init__(self, name, data):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(Path(name).name)
        self.setWindowFilePath(str(name))
        self.resize(850, 1000)
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(data))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.document = QPdfDocument(self)
        self.document.load(self.buffer)
        if self.document.status() != QPdfDocument.Status.Ready or not self.document.pageCount():
            self.document.close()
            self.buffer.close()
            self.deleteLater()
            raise ValueError('Cannot open PDF. It may be damaged or password protected.')
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitInView)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self.view.viewport().setAttribute(qt.Qt.WidgetAttribute.WA_AcceptTouchEvents)
        self.start = None
        self.wheel_delta = 0
        root = qt.QWidget(self)
        layout = qt.QVBoxLayout(root)
        controls = qt.QHBoxLayout()
        from commonUtils.ui.readers.reader_chrome import reader_button, ReaderFullscreen
        self.previous = reader_button(self, 'Previous page', icon='previous')
        self.following = reader_button(self, 'Next page', icon='next')
        self.number = qt.QSpinBox()
        self.number.setRange(1, self.document.pageCount())
        self.number.setPrefix('Page ')
        self.number.setSuffix(f' / {self.document.pageCount()}')
        self.number.setKeyboardTracking(False)
        self.number.valueChanged.connect(lambda value: self.go(value - 1))
        self.previous.clicked.connect(lambda: self.go(self.index - 1))
        self.following.clicked.connect(lambda: self.go(self.index + 1))
        for widget in (self.previous, self.number, self.following):
            controls.addWidget(widget)
        controls.addStretch(1)
        self.find_button = reader_button(self, 'Find in PDF', text='Find in PDF')
        self.find_button.setCheckable(True)
        controls.addWidget(self.find_button)
        self.fullscreen_action = qt.QAction('Full screen', self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setShortcut('F11')
        self.addAction(self.fullscreen_action)
        self.fullscreen = ReaderFullscreen(self, self.fullscreen_action)
        self.fullscreen_action.triggered.connect(self.fullscreen.toggle)
        controls.addWidget(reader_button(self, 'Full screen', action=self.fullscreen_action, icon='fullscreen'))
        layout.addLayout(controls)
        from .search import PDFSearchBar
        self.search = PDFSearchBar(data, self.go, self)
        layout.addWidget(self.search)
        self.search.hide()
        self.find_button.toggled.connect(self.search.setVisible)
        from PySide6.QtGui import QShortcut, QKeySequence
        self.find_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        self.find_shortcut.activated.connect(self.show_find)
        layout.addWidget(self.view)
        self.setCentralWidget(root)
        self.document.pageCountChanged.connect(lambda count: self.number.setMaximum(max(1, count)))
        self.view.pageNavigator().currentPageChanged.connect(self.sync_page)
        self.go(0)

    def show_find(self):
        self.find_button.setChecked(True)
        self.search.input.setFocus()
        self.search.input.selectAll()

    def go(self, index):
        if not 0 <= index < self.document.pageCount():
            return
        self.view.pageNavigator().jump(index, QPoint(0, 0))
        self.sync_page(index)

    def sync_page(self, index):
        self.index = index
        self.number.blockSignals(True)
        self.number.setValue(index + 1)
        self.number.blockSignals(False)
        self.previous.setEnabled(index > 0)
        self.following.setEnabled(index + 1 < self.document.pageCount())

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.Wheel:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            self.wheel_delta += delta
            if abs(self.wheel_delta) >= 120:
                self.go(self.index + (1 if self.wheel_delta < 0 else -1))
                self.wheel_delta = 0
            return True
        if kind in (QEvent.Type.TouchBegin, QEvent.Type.MouseButtonPress):
            self.start = event.points()[0].position() if kind == QEvent.Type.TouchBegin else event.position()
            if kind == QEvent.Type.TouchBegin:
                return True
        elif kind == QEvent.Type.TouchUpdate:
            return True
        elif kind == QEvent.Type.TouchCancel:
            self.start = None
            return True
        elif kind in (QEvent.Type.TouchEnd, QEvent.Type.MouseButtonRelease) and self.start is not None:
            end = event.points()[0].position() if kind == QEvent.Type.TouchEnd else event.position()
            delta = end - self.start
            self.start = None
            if abs(delta.y()) >= 50 and abs(delta.y()) > abs(delta.x()):
                self.go(self.index + (1 if delta.y() < 0 else -1))
                return True
        elif kind == QEvent.Type.KeyPress:
            key = event.key()
            if key in (qt.Qt.Key.Key_Down, qt.Qt.Key.Key_PageDown, qt.Qt.Key.Key_Up, qt.Qt.Key.Key_PageUp):
                self.go(self.index + (1 if key in (qt.Qt.Key.Key_Down, qt.Qt.Key.Key_PageDown) else -1))
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        self.search.dispose()
        self.view.setDocument(None)
        self.document.close()
        self.buffer.close()
        self.buffer.setData(QByteArray())
        super().closeEvent(event)


def open_pdf(path, parent=None):
    with Path(path).open('rb') as stream:
        data = read_pdf(stream)
    window = PDFWindow(str(path), data)
    from services.documents.ui.editors import retain
    retain(window)
    return window
