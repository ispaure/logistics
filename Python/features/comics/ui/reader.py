"""Native adaptive-spread reader with deliberate adjacent-file navigation."""

import time
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reading import comic_siblings, visible_pages
from .operations import Operation


class PageCanvas(qt.QWidget):
    resized = qt.Signal()

    def __init__(self):
        super().__init__()
        self.pixmaps = ()
        self.visual_pages = ()
        self.message = 'Loading page…'
        self.setMinimumSize(100, 100)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Expanding)

    @property
    def pixmap(self):
        return self.pixmaps[0][1] if self.pixmaps else qt.QPixmap()

    def set_pages(self, pages, right_to_left):
        self.pixmaps = tuple(reversed(pages)) if right_to_left else tuple(pages)
        self.visual_pages = tuple(index for index, _ in self.pixmaps)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.fillRect(self.rect(), self.palette().brush(qt.QPalette.ColorRole.Base))
        if not self.pixmaps:
            painter.setPen(self.palette().color(qt.QPalette.ColorRole.Text))
            painter.drawText(self.rect().adjusted(20, 20, -20, -20),
                             qt.Qt.AlignmentFlag.AlignCenter | qt.Qt.TextFlag.TextWordWrap, self.message)
            return
        gap = 8 if len(self.pixmaps) == 2 else 0
        ratios = [pixmap.width() / pixmap.height() for _, pixmap in self.pixmaps]
        height = min(self.height(), (self.width() - gap) / sum(ratios))
        width = sum(ratios) * height + gap
        x, y = (self.width() - width) / 2, (self.height() - height) / 2
        painter.setRenderHint(qt.QPainter.RenderHint.SmoothPixmapTransform)
        for ratio, (_, pixmap) in zip(ratios, self.pixmaps):
            target = qt.QRectF(x, y, ratio * height, height)
            painter.drawPixmap(target, pixmap, qt.QRectF(pixmap.rect()))
            x += target.width() + gap


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


def read_candidates(pages, index):
    images = {index: read_image(pages, index)}
    if index + 1 < len(pages.pages) and index not in pages.double_pages and images[index].width() < images[index].height():
        try:
            images[index + 1] = read_image(pages, index + 1)
        except Exception:
            # A damaged following page must not prevent reading this page.
            pass
    return images


def read_previous(pages, index, viewport, mode):
    """Choose the previous spread from its actual images after a seek or resize."""
    if index > 0:
        images = read_candidates(pages, index - 1)
        sizes = {page: (image.width(), image.height()) for page, image in images.items()}
        if visible_pages(index - 1, sizes, viewport, mode, pages.double_pages) == (index - 1, index):
            return index - 1, images
    return index, read_candidates(pages, index)


class ComicReaderWindow(qt.QMainWindow):
    metadata_saved = qt.Signal(object)

    def __init__(self, pages):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(950, 900)
        self.pages = pages
        self.page = 0
        self.shown_page = 0
        self.mode = 'auto'
        self.images = {}
        self.displayed_pages = (0,)
        self.busy = False
        self.file_loading = False
        self.closing = False
        self.pending_page = None
        self.pending_file = None
        self.previous_starts = []
        self.boundary = None
        self.metadata_windows = []
        self.siblings = []
        self._menus()
        container = qt.QWidget()
        layout = qt.QVBoxLayout(container)
        header = qt.QHBoxLayout()
        self.previous_file_button = self._button('Previous file', qt.QStyle.StandardPixmap.SP_MediaSkipBackward)
        self.next_file_button = self._button('Next file', qt.QStyle.StandardPixmap.SP_MediaSkipForward)
        self.previous_file_button.clicked.connect(lambda: self.open_adjacent(-1))
        self.next_file_button.clicked.connect(lambda: self.open_adjacent(1))
        self.file_controls = qt.QHBoxLayout()
        header.addLayout(self.file_controls)
        self.title = qt.QLabel()
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        header.addWidget(self.title, 1)
        self.direction = qt.QLabel()
        header.addWidget(self.direction)
        fullscreen = qt.QToolButton()
        fullscreen.setDefaultAction(self.fullscreen_action)
        header.addWidget(fullscreen)
        layout.addLayout(header)
        self.canvas = PageCanvas()
        self.canvas.setFocusPolicy(qt.Qt.FocusPolicy.StrongFocus)
        self.setFocusProxy(self.canvas)
        layout.addWidget(self.canvas, 1)
        self.canvas.resized.connect(self._resized)
        controls = qt.QHBoxLayout()
        self.previous_button = self._button('Previous page', qt.QStyle.StandardPixmap.SP_ArrowLeft)
        self.next_button = self._button('Next page', qt.QStyle.StandardPixmap.SP_ArrowRight)
        self.previous_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        self.page_controls = qt.QHBoxLayout()
        controls.addLayout(self.page_controls)
        self.progress = qt.QSlider(qt.Qt.Orientation.Horizontal)
        self.progress.setAccessibleName('Reading progress')
        self.progress.setLayoutDirection(qt.Qt.LayoutDirection.LeftToRight)
        self.progress.valueChanged.connect(self.go)
        controls.addWidget(self.progress, 1)
        self.progress_label = qt.QLabel()
        controls.addWidget(self.progress_label)
        layout.addLayout(controls)
        self.setCentralWidget(container)
        qt.QApplication.instance().installEventFilter(self)
        self._configure_file()
        self.go(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus(qt.Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, watched, event):
        if (not isinstance(watched, qt.QWidget) or watched.window() is not self
                or event.type() not in (qt.QEvent.Type.ShortcutOverride, qt.QEvent.Type.KeyPress)):
            return super().eventFilter(watched, event)
        modifiers = event.modifiers() & ~qt.Qt.KeyboardModifier.KeypadModifier
        keys = (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right, qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down,
                qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End, qt.Qt.Key.Key_Escape)
        if modifiers or event.key() not in keys:
            return super().eventFilter(watched, event)
        event.accept()
        if event.type() == qt.QEvent.Type.KeyPress and not event.isAutoRepeat():
            key = event.key()
            if key in (qt.Qt.Key.Key_Left, qt.Qt.Key.Key_Right):
                forward = (key == qt.Qt.Key.Key_Left) if self.pages.right_to_left else (key == qt.Qt.Key.Key_Right)
                self.step(1 if forward else -1)
            elif key in (qt.Qt.Key.Key_Up, qt.Qt.Key.Key_Down):
                self.step(1 if key == qt.Qt.Key.Key_Down else -1)
            elif key in (qt.Qt.Key.Key_Home, qt.Qt.Key.Key_End):
                self.go(0 if key == qt.Qt.Key.Key_Home else len(self.pages.pages) - 1)
            else:
                self.leave_fullscreen()
        return True

    def _button(self, name, icon):
        button = qt.QToolButton()
        button.setIcon(self.style().standardIcon(icon))
        button.setIconSize(qt.QSize(22, 22))
        button.setAutoRaise(True)
        button.setToolTip(name)
        button.setAccessibleName(name)
        return button

    def _menus(self):
        file_menu = self.menuBar().addMenu('File')
        open_action = file_menu.addAction('Open Comic…')
        open_action.setShortcut(qt.QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._choose_file)
        self.previous_file_action = file_menu.addAction('Previous File')
        self.previous_file_action.setShortcut('Ctrl+Shift+Left')
        self.previous_file_action.triggered.connect(lambda: self.open_adjacent(-1))
        self.next_file_action = file_menu.addAction('Next File')
        self.next_file_action.setShortcut('Ctrl+Shift+Right')
        self.next_file_action.triggered.connect(lambda: self.open_adjacent(1))
        self.previous_file_action.setAutoRepeat(False)
        self.next_file_action.setAutoRepeat(False)
        file_menu.addSeparator()
        close_action = file_menu.addAction('Close')
        close_action.setShortcut(qt.QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        edit_menu = self.menuBar().addMenu('Edit')
        self.edit_metadata_action = edit_menu.addAction('Edit Metadata…')
        self.edit_metadata_action.setShortcut('Ctrl+I')
        self.edit_metadata_action.triggered.connect(self.edit_metadata)
        view_menu = self.menuBar().addMenu('View')
        group = qt.QActionGroup(self)
        for mode, label in (('auto', 'Automatic Pages'), ('single', 'Single Page'), ('double', 'Two Pages')):
            action = view_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == 'auto')
            group.addAction(action)
            action.triggered.connect(lambda checked=False, selected=mode: self.set_mode(selected))
        self.fullscreen_action = view_menu.addAction('Full Screen')
        self.fullscreen_action.setShortcut('F11')
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)

    def _configure_file(self):
        self.setWindowTitle(self.pages.path.name)
        self.setWindowFilePath(str(self.pages.path))
        self.title.setText(self.pages.path.name)
        rtl = self.pages.right_to_left
        self.direction.setText('Right to left' if rtl else 'Left to right')
        blocker = qt.QSignalBlocker(self.progress)
        self.progress.setInvertedAppearance(rtl)
        self.progress.setRange(0, max(1, len(self.pages.pages) - 1))
        self.progress.setEnabled(len(self.pages.pages) > 1)
        blocker.unblock()
        for layout, previous, following in ((self.page_controls, self.previous_button, self.next_button),
                                            (self.file_controls, self.previous_file_button, self.next_file_button)):
            while layout.count():
                layout.takeAt(0)
            layout.addWidget(following if rtl else previous)
            layout.addWidget(previous if rtl else following)
        self.previous_button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_ArrowRight if rtl else qt.QStyle.StandardPixmap.SP_ArrowLeft))
        self.next_button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_ArrowLeft if rtl else qt.QStyle.StandardPixmap.SP_ArrowRight))
        self.previous_file_button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_MediaSkipForward if rtl else qt.QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.next_file_button.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_MediaSkipBackward if rtl else qt.QStyle.StandardPixmap.SP_MediaSkipForward))
        self._refresh_siblings()

    def _refresh_siblings(self):
        try:
            self.siblings = comic_siblings(self.pages.path)
        except OSError:
            self.siblings = [self.pages.path]
        self._update_controls()

    def adjacent_path(self, direction):
        if self.pages.path not in self.siblings:
            return None
        index = self.siblings.index(self.pages.path) + direction
        return self.siblings[index] if 0 <= index < len(self.siblings) else None

    def _update_controls(self):
        if not hasattr(self, 'progress'):
            return
        end = self.displayed_pages[-1]
        blocker = qt.QSignalBlocker(self.progress)
        self.progress.setValue(0 if self.shown_page == 0 else end)
        blocker.unblock()
        numbers = ' & '.join(str(index + 1) for index in self.displayed_pages)
        self.progress_label.setText(f'{numbers} / {len(self.pages.pages)} · {(end + 1) / len(self.pages.pages):.0%}')
        self.previous_button.setEnabled(not self.file_loading and (self.page > 0 or self.adjacent_path(-1) is not None))
        self.next_button.setEnabled(not self.file_loading and (end < len(self.pages.pages) - 1 or self.adjacent_path(1) is not None))
        for direction, button, action in ((-1, self.previous_file_button, self.previous_file_action),
                                           (1, self.next_file_button, self.next_file_action)):
            path = self.adjacent_path(direction)
            button.setEnabled(path is not None and not self.file_loading)
            action.setEnabled(button.isEnabled())
            button.setToolTip(('Previous file' if direction < 0 else 'Next file') + (f': {path.name}' if path else ''))
        self.edit_metadata_action.setEnabled(not self.file_loading)

    def set_mode(self, mode):
        self.mode = mode
        self.boundary = None
        self.previous_starts.clear()
        self._update_spread()

    def _resized(self):
        before = self.displayed_pages
        self._update_spread()
        if before != self.displayed_pages:
            self.boundary = None
            self.previous_starts.clear()

    def _update_spread(self):
        if not hasattr(self, 'canvas') or not hasattr(self, 'progress'):
            return
        sizes = {index: (image.width(), image.height()) for index, image in self.images.items()}
        self.displayed_pages = visible_pages(self.shown_page, sizes, (self.canvas.width(), self.canvas.height()),
                                            self.mode, self.pages.double_pages)
        pixmaps = [(index, qt.QPixmap.fromImage(self.images[index])) for index in self.displayed_pages if index in self.images]
        self.canvas.set_pages(pixmaps, self.pages.right_to_left)
        self._update_controls()

    def go(self, index, *, clear_history=True, previous=False):
        if self.closing or self.file_loading:
            return
        self.boundary = None
        if clear_history:
            self.previous_starts.clear()
        index = max(0, min(index, len(self.pages.pages) - 1))
        self.page = index
        self._update_controls()
        if self.busy:
            self.pending_page = (index, previous)
            return
        self.pending_page = None
        pages = self.pages
        if previous:
            viewport, mode = (self.canvas.width(), self.canvas.height()), self.mode
            self._start(lambda: read_previous(pages, index, viewport, mode),
                        lambda result, error: self._previous_loaded(pages, index, result, error))
        else:
            self._start(lambda: read_candidates(pages, index), lambda images, error: self._loaded(pages, index, images, error))

    def _previous_loaded(self, pages, expected, result, error):
        if self.closing or pages is not self.pages or self.page != expected:
            return
        if error:
            self._loaded(pages, expected, {}, error)
        else:
            self.page, images = result
            self._loaded(pages, self.page, images, '')

    def step(self, direction):
        if self.closing or self.file_loading:
            return
        end = self.displayed_pages[-1] if self.page == self.shown_page else self.page
        if direction > 0 and end < len(self.pages.pages) - 1:
            self.previous_starts.append(self.page)
            self.go(end + 1, clear_history=False)
        elif direction < 0 and self.page > 0:
            if self.previous_starts and self.previous_starts[-1] < self.page:
                previous = self.previous_starts.pop()
                self.go(previous, clear_history=False)
            else:
                self.go(self.page - 1, clear_history=False, previous=True)
        else:
            self._boundary_press(direction)

    def _boundary_press(self, direction):
        path = self.adjacent_path(direction)
        if path is None:
            return
        now = time.monotonic()
        if self.boundary is not None and self.boundary[0] == direction and now - self.boundary[1] <= .4:
            self.boundary = None
            self.open_adjacent(direction)
        else:
            self.boundary = (direction, now)
            self.statusBar().showMessage(f'Press again within 0.4 s to open {path.name}', 1800)

    def _start(self, callback, completed):
        self.busy = True
        self.operation = Operation(callback, self)
        self.operation.completed.connect(completed)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, pages, index, images, error):
        if self.closing or pages is not self.pages or index != self.page:
            return
        if error:
            self.canvas.message = f'Cannot read page: {error}'
            self.statusBar().showMessage(self.canvas.message, 8000)
            self.page = self.shown_page
            self.canvas.update()
            self._update_controls()
        else:
            self.shown_page = index
            self.images = images
            self._update_spread()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.closing:
            self.close()
        elif self.pending_file is not None:
            path, from_end, page = self.pending_file
            self.pending_file = None
            self._request_file(path, from_end, page)
        elif self.pending_page is not None:
            index, previous = self.pending_page
            self.pending_page = None
            self.go(index, clear_history=False, previous=previous)

    def open_adjacent(self, direction):
        self._refresh_siblings()
        path = self.adjacent_path(direction)
        if path is not None:
            self._request_file(path, direction < 0)

    def _request_file(self, path, from_end=False, page=0):
        if self.closing:
            return
        if any(window.busy for window in self.metadata_windows):
            self.statusBar().showMessage('Finishing metadata save…', 1800)
            return
        if self.busy:
            self.pending_file = (path, from_end, page)
            return
        self.file_loading = True
        self.pending_page = None
        self.boundary = None
        self._update_controls()
        def read():
            pages = ComicPages(path)
            start = len(pages.pages) - 1 if from_end else min(page, len(pages.pages) - 1)
            return pages, start, read_candidates(pages, start)
        self._start(read, self._file_loaded)

    def _file_loaded(self, result, error):
        self.file_loading = False
        if self.closing:
            return
        if error:
            self.statusBar().showMessage(f'Cannot open comic: {error}', 8000)
            self._refresh_siblings()
            return
        self.pages, self.page, self.images = result
        self.shown_page = self.page
        self.previous_starts.clear()
        self.displayed_pages = (self.page,)
        self._configure_file()
        self._update_spread()
        self.statusBar().clearMessage()

    def _choose_file(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open Comic', str(self.pages.path.parent), 'Comic archives (*.cbz)')
        if path:
            self._request_file(path)

    def edit_metadata(self):
        from .metadata_editor import MetadataEditor
        existing = next((window for window in self.metadata_windows
                         if window.targets == (self.pages.path,) and window.isVisible()), None)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return existing
        self._refresh_siblings()
        editor = MetadataEditor(self.pages.path, self.siblings, self)
        self.metadata_windows.append(editor)
        editor.saved.connect(self._metadata_saved)
        editor.show()
        return editor

    def _metadata_saved(self, path):
        self.metadata_saved.emit(path)
        if self.pages.path == path:
            self.reload_metadata_path = path
            qt.QTimer.singleShot(0, self._reload_metadata)

    def _reload_metadata(self):
        if self.closing or self.pages.path != self.reload_metadata_path:
            return
        if any(window.busy for window in self.metadata_windows):
            qt.QTimer.singleShot(25, self._reload_metadata)
            return
        self._request_file(self.reload_metadata_path, False, self.page)

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def shutdown(self):
        self.closing = True
        if self.busy:
            self.operation.wait()
        for window in self.metadata_windows:
            if window.busy:
                window.operation.wait()

    def closeEvent(self, event):
        if any(window.busy for window in self.metadata_windows):
            event.ignore()
            return
        for window in self.metadata_windows:
            if window.isVisible():
                window.reject()
        self.closing = True
        if self.busy:
            self.hide()
            event.ignore()
        else:
            event.accept()
