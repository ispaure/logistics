"""Native adaptive-spread reader with deliberate adjacent-file navigation."""

import time
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reading import comic_siblings, visible_pages
from .operations import Operation
from .reader_pages import PageCanvas, read_image, read_candidates, read_previous
from .reader_controls import ReaderControls, ReaderMenus
from .reader_keys import ReaderKeyHandler

FILE_SWITCH_INTERVAL = .4


class ComicReaderWindow(qt.QMainWindow):
    """Coordinate asynchronous requests while retaining the last successful display.

    page is the latest requested index; shown_page and images describe what is
    actually on screen. Worker completions replace them only if still current.
    """
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
        self.reload_metadata_path = None
        self.siblings = []
        self.menus = ReaderMenus(self)
        self.previous_file_action = self.menus.previous_file_action
        self.next_file_action = self.menus.next_file_action
        self.edit_metadata_action = self.menus.edit_metadata_action
        self.fullscreen_action = self.menus.fullscreen_action
        self.controls = ReaderControls(self.fullscreen_action, self)
        self.setCentralWidget(self.controls)
        # Preserve the widget handles used by callers while keeping construction separate.
        for name in ('canvas', 'progress', 'progress_label', 'previous_button', 'next_button',
                     'previous_file_button', 'next_file_button', 'title', 'direction'):
            setattr(self, name, getattr(self.controls, name))
        self.setFocusProxy(self.canvas)
        self.canvas.resized.connect(self._resized)
        self.progress.valueChanged.connect(self.go)
        self.previous_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))
        self.previous_file_button.clicked.connect(lambda: self.open_adjacent(-1))
        self.next_file_button.clicked.connect(lambda: self.open_adjacent(1))
        self.keys = ReaderKeyHandler(self)
        self._configure_file()
        self.go(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus(qt.Qt.FocusReason.OtherFocusReason)

    def _configure_file(self):
        self.setWindowTitle(self.pages.path.name)
        self.setWindowFilePath(str(self.pages.path))
        self.controls.set_file(self.pages)
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
        self.controls.show_progress(self.shown_page, self.displayed_pages, len(self.pages.pages))
        can_go_back = self.page > 0 or self.adjacent_path(-1) is not None
        can_go_forward = self.displayed_pages[-1] < len(self.pages.pages) - 1 or self.adjacent_path(1) is not None
        self.previous_button.setEnabled(not self.file_loading and can_go_back)
        self.next_button.setEnabled(not self.file_loading and can_go_forward)
        for direction, button, action in ((-1, self.previous_file_button, self.previous_file_action),
                                           (1, self.next_file_button, self.next_file_action)):
            path = self.adjacent_path(direction)
            button.setEnabled(path is not None and not self.file_loading)
            action.setEnabled(button.isEnabled())
            label = 'Previous file' if direction < 0 else 'Next file'
            button.setToolTip(f'{label}: {path.name}' if path else label)
        self.edit_metadata_action.setEnabled(not self.file_loading)

    def set_mode(self, mode):
        if mode not in self.menus.mode_actions:
            raise ValueError('Unknown reader page mode')
        self.menus.mode_actions[mode].setChecked(True)
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
        if self.boundary is not None and self.boundary[0] == direction and now - self.boundary[1] <= FILE_SWITCH_INTERVAL:
            self.boundary = None
            self.open_adjacent(direction)
        else:
            self.boundary = (direction, now)
            self.statusBar().showMessage(f'Press again within {FILE_SWITCH_INTERVAL:g} s to open {path.name}', 1800)

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
        for window in list(self.metadata_windows):
            if not window.isVisible() and not window.busy:
                self.metadata_windows.remove(window)
                window.deleteLater()
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
