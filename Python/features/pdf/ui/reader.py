"""Independent Qt PDF reader with continuous page scrolling."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from PySide6.QtCore import QByteArray, QEvent, QTimer
from .continuous import ContinuousPDFView, load_pdf
from features.pdf.document import MAX_PDF
from services.documents.storage import read_local_bytes


class PDFWindow(qt.QMainWindow):
    document_editor_id = 'pdf'
    document_editor_name = 'PDF Reader'

    def __init__(self, name, data, *, annotation_provider=None, annotation_path=None):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(Path(name).name)
        self.setWindowFilePath(str(name))
        self.resize(850, 1000)
        try:
            self.document, self.buffer = load_pdf(self, data)
        except ValueError:
            self.deleteLater()
            raise
        self.position_state = None
        self._position_ready = False
        if annotation_provider is not None or Path(name).is_absolute():
            from hashlib import sha256
            from commonUtils.filesystem.storage import cache_directory
            from services.documents.progress import open_progress

            self.position_state = open_progress(
                annotation_provider, annotation_path if annotation_provider is not None else name,
                cache_directory(create=False), kind='desktop-pdf', revision=sha256(data).hexdigest(),
            )
        self.position_timer = QTimer(self)
        self.position_timer.setSingleShot(True)
        self.position_timer.setInterval(300)
        self.position_timer.timeout.connect(self.flush_position)
        self.view = ContinuousPDFView(self)
        self.view.setDocument(self.document)
        self.view.viewport().installEventFilter(self)
        self.view.installEventFilter(self)
        self.start = None
        self.dragged = False
        root = qt.QWidget(self)
        layout = qt.QVBoxLayout(root)
        from commonUtils.ui.readers.layout import READER_LAYOUT
        layout.setContentsMargins(*READER_LAYOUT.desktop_margins)
        layout.setSpacing(READER_LAYOUT.spacing)
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
        self.undo_jump = qt.QPushButton('Undo page jump')
        self.undo_jump.hide()
        self.undo_jump.clicked.connect(self.undo_link_jump)
        controls.addWidget(self.undo_jump)
        self.link_return = None
        self.link_timer = QTimer(self)
        self.link_timer.setSingleShot(True)
        self.link_timer.timeout.connect(self.clear_link_return)
        controls.addStretch(1)
        self.find_button = reader_button(self, 'Find in PDF', text='Find in PDF')
        self.find_button.setCheckable(True)
        controls.addWidget(self.find_button)
        if annotation_provider is not None:
            from features.pdf.annotation import LABEL
            from .annotation import annotate_pdf
            self.actions_button = qt.QToolButton()
            self.actions_button.setText('⋯')
            self.actions_button.setAccessibleName('PDF actions')
            self.actions_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
            self.actions_menu = qt.QMenu(self.actions_button)
            self.actions_menu.addAction(LABEL).triggered.connect(
                lambda: annotate_pdf(annotation_provider, annotation_path, self))
            self.actions_button.setMenu(self.actions_menu)
            controls.addWidget(self.actions_button)
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
        self.view.pageNavigator().currentPageChanged.connect(self.sync_page)
        saved = self.position_state.load() if self.position_state is not None else {}
        if (self.position_state is not None and self.position_state.can_import_legacy
                and self.position_state.load_status == 'absent' and self.position_state.mode == 'encrypted'):
            from services.documents.reader_positions import desktop_state

            previous = desktop_state(annotation_provider, annotation_path, 'pdf')
            legacy = previous.load()
            if previous.locked_state:
                self.position_state.load_status = 'locked'
                self.position_state.retire()
            if type(legacy.get('page')) is int and 0 <= legacy['page'] < self.document.pageCount():
                saved = legacy
                self.position_state.save(saved)
        page = saved.get('page', 0)
        page = page if type(page) is int and 0 <= page < self.document.pageCount() else 0
        self.go(page)
        self._saved_scroll = saved.get('scroll_fraction')
        self._saved_page = page or None
        self.view.verticalScrollBar().valueChanged.connect(self.observe_position)
        self._position_ready = True
        if self.position_state is not None:
            self.position_notice(self.position_state.load_status)

    def show_find(self):
        self.find_button.setChecked(True)
        self.search.input.setFocus()
        self.search.input.selectAll()

    def clear_link_return(self):
        self.link_timer.stop()
        self.link_return = None
        self.undo_jump.hide()

    def offer_link_return(self, previous):
        if self.index != previous:
            self.link_return = previous
            self.undo_jump.show()
            self.link_timer.start(3000)

    def undo_link_jump(self):
        previous = self.link_return
        self.clear_link_return()
        if previous is not None:
            self.go(previous)

    def go(self, index):
        if not 0 <= index < self.document.pageCount():
            return
        if self._position_ready and not self.isVisible():
            self._saved_scroll, self._saved_page = None, index
        self.clear_link_return()
        from services.documents.ui.page_transition import page_slide
        slide = page_slide(self.view.viewport())
        slide.begin(index - getattr(self, 'index', index), vertical=True)
        self.view.jump(index)
        self.sync_page(self.view.pageNavigator().currentPage())
        slide.finish()

    def sync_page(self, index):
        changed = index != getattr(self, 'index', index)
        if changed:
            self.clear_link_return()
        self.index = index
        self.number.blockSignals(True)
        self.number.setValue(index + 1)
        self.number.blockSignals(False)
        self.previous.setEnabled(index > 0)
        self.following.setEnabled(index + 1 < self.document.pageCount())

    def showEvent(self, event):
        super().showEvent(event)
        saved, self._saved_scroll = self._saved_scroll, None
        page, self._saved_page = self._saved_page, None
        if type(saved) in (int, float) and 0 <= saved <= 1:
            bar = self.view.verticalScrollBar()
            bar.setValue(round(saved * bar.maximum()))
        elif page is not None:
            self.view.jump(page)

    def observe_position(self):
        if self._position_ready and self.position_state is not None:
            bar = self.view.verticalScrollBar()
            value = dict(page=self.index, scroll_fraction=bar.value() / max(1, bar.maximum()))
            if self.position_state.observe(value) is not None:
                self.position_timer.start()

    def flush_position(self):
        if self.position_state is not None:
            self.position_notice(self.position_state.flush())

    def position_notice(self, status):
        from services.documents.ui.position_notice import position_notice

        message = position_notice(self.position_state, status)
        if message:
            self.statusBar().showMessage(message)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == qt.Qt.MouseButton.LeftButton:
            self.start = event.position()
            self.dragged = False
        elif kind == QEvent.Type.MouseMove and self.start is not None:
            delta = event.position() - self.start
            if self.dragged or delta.manhattanLength() >= qt.QApplication.startDragDistance():
                bar = self.view.verticalScrollBar()
                bar.setValue(bar.value() - round(delta.y()))
                self.start = event.position()
                self.dragged = True
                return True
        elif kind == QEvent.Type.MouseButtonRelease and self.start is not None:
            self.start = None
            if self.dragged:
                return True
            previous = self.index
            QTimer.singleShot(0, self, lambda: self.offer_link_return(previous))
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        self.position_timer.stop()
        self._position_ready = False
        self.flush_position()
        if self.position_state is not None:
            self.position_state.retire()
        self.clear_link_return()
        self.search.dispose()
        self.view.setDocument(None)
        self.document.close()
        self.buffer.close()
        self.buffer.setData(QByteArray())
        super().closeEvent(event)


def open_pdf(path, parent=None):
    data = read_local_bytes(path, max_bytes=MAX_PDF)
    from services.documents.storage import local_document_resource
    with local_document_resource(path, max_bytes=MAX_PDF) as resource:
        window = PDFWindow(str(path), data, annotation_provider=resource.provider, annotation_path=resource.path)
    from services.documents.ui.editors import retain
    retain(window)
    return window
