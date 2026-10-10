"""Native adaptive-spread reader with deliberate adjacent-file navigation."""

import time
from pathlib import Path
from commonUtils.debugUtils import Severity, log
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reading import comic_siblings, visible_pages
from commonUtils.ui.operations import Operation
from services.zip_passwords import is_password_error
from ui_new.dialogs.archive_password import ask_password
from .reader_pages import PageCanvas, read_image, read_candidates, read_previous
from .reader_controls import ReaderControls, ReaderMenus
from .reader_keys import ReaderKeyHandler
from .reader_cache import ReaderPageCache

FILE_SWITCH_INTERVAL = .4


class ComicReaderWindow(qt.QMainWindow):
    document_editor_name = 'Comic Reader'
    document_editor_id = 'comic'
    """Coordinate asynchronous requests while retaining the last successful display.

    page is the latest requested index; shown_page and images describe what is
    actually on screen. Worker completions replace them only if still current.
    """
    metadata_saved = qt.Signal(object)
    closed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, pages):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(950, 900)
        self.setMinimumSize(640, 420)
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
        self.page_cache = ReaderPageCache(self)
        self.page_cache.idle.connect(self._cache_idle)
        self.page_cache.idle.connect(self.idle)
        self.menus = ReaderMenus(self)
        self.previous_file_action = self.menus.previous_file_action
        self.next_file_action = self.menus.next_file_action
        self.edit_metadata_action = self.menus.edit_metadata_action
        self.fullscreen_action = self.menus.fullscreen_action
        self.controls = ReaderControls(self.fullscreen_action, self, menus=self.menus)
        self.setCentralWidget(self.controls)
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        status.messageChanged.connect(lambda message: status.setVisible(bool(message)))
        status.hide()
        # Preserve the widget handles used by callers while keeping construction separate.
        for name in ('canvas', 'progress', 'progress_label', 'previous_button', 'next_button',
                     'previous_file_button', 'next_file_button', 'title', 'direction'):
            setattr(self, name, getattr(self.controls, name))
        self.setFocusProxy(self.canvas)
        self.canvas.resized.connect(self._resized)
        self.progress.valueChanged.connect(self.go)
        self.previous_file_button.clicked.connect(lambda: self.open_adjacent(-1))
        self.next_file_button.clicked.connect(lambda: self.open_adjacent(1))
        self.keys = ReaderKeyHandler(self)
        self.previous_button.pressed.connect(lambda: self.keys.start(-1))
        self.next_button.pressed.connect(lambda: self.keys.start(1))
        self.previous_button.released.connect(self.keys.stop)
        self.next_button.released.connect(self.keys.stop)
        self._configure_file()
        self.go(0)

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.setFocus(qt.Qt.FocusReason.OtherFocusReason)

    def _configure_file(self):
        self.page_cache.set_pages(self.pages)
        self.setWindowTitle(self.pages.path.name)
        self.setWindowFilePath(str(self.pages.path))
        self.menus.shared.remember(self.pages.path)
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
        self.menus.previous_page_action.setEnabled(self.previous_button.isEnabled())
        self.menus.next_page_action.setEnabled(self.next_button.isEnabled())
        self.menus.go_page_action.setEnabled(not self.file_loading)
        self.menus.shared.open_action.setEnabled(not self.file_loading)
        self.menus.shared.recent.setEnabled(not self.file_loading)

    def set_mode(self, mode):
        if mode not in self.menus.mode_actions:
            raise ValueError('Unknown reader page mode')
        self.menus.mode_actions[mode].setChecked(True)
        self.mode = mode
        self.controls.layout_button.setToolTip(f'Page layout: {self.menus.mode_actions[mode].text()}')
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
        cached = self.page_cache.lookup(index, previous, (self.canvas.width(), self.canvas.height()), self.mode)
        if cached is not None:
            self.page, images = cached
            self._loaded(pages, self.page, images, '')
            return
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
        self.operation.finished.connect(self.idle)
        self.operation.start()

    def _loaded(self, pages, index, images, error):
        if self.closing or pages is not self.pages or index != self.page:
            return
        if error:
            self.keys.stop()
            self.canvas.message = f'Cannot read page: {error}'
            self.statusBar().showMessage(self.canvas.message)
            self.canvas.setToolTip(self.canvas.message)
            log(Severity.ERROR, 'Comic Reader', self.canvas.message)
            self.page = self.shown_page
            self.canvas.update()
            self._update_controls()
        else:
            self.statusBar().clearMessage()
            self.canvas.setToolTip('')
            self.canvas.message = ''
            self.shown_page = index
            self.images = images
            self._update_spread()
            self.page_cache.update(images, self.shown_page, self.displayed_pages[-1])
            self.keys.page_shown()

    def _finished(self):
        self.busy = False
        self.operation.deleteLater()
        if self.closing:
            from commonUtils.ui.document_host import close_document
            close_document(self)
        elif self.pending_file is not None:
            path, from_end, page, password = self.pending_file
            self.pending_file = None
            self._request_file(path, from_end, page, password=password)
        elif self.pending_page is not None:
            index, previous = self.pending_page
            self.pending_page = None
            self.go(index, clear_history=False, previous=previous)

    def open_adjacent(self, direction):
        self._refresh_siblings()
        path = self.adjacent_path(direction)
        if path is not None:
            self._request_file(path, direction < 0)

    def _request_file(self, path, from_end=False, page=0, *, password=None):
        if self.closing:
            return
        if Path(path).suffix.lower() != '.cbz':
            self.statusBar().showMessage('This reader opens CBZ comics. Open EPUB books in the EPUB reader.')
            return
        if any(window.busy for window in self.metadata_windows):
            self.statusBar().showMessage('Finishing metadata save…', 1800)
            return
        if self.busy:
            self.pending_file = (path, from_end, page, password)
            return
        self.keys.stop()
        self.file_loading = True
        self.loading_request = (Path(path), from_end, page)
        self.pending_page = None
        self.boundary = None
        self._update_controls()
        def read():
            pages = ComicPages(path, password=password)
            start = len(pages.pages) - 1 if from_end else min(page, len(pages.pages) - 1)
            return pages, start, read_candidates(pages, start)
        self._start(read, self._file_loaded)

    def _file_loaded(self, result, error):
        self.file_loading = False
        if self.closing:
            return
        if error:
            self.statusBar().showMessage(f'Cannot open comic: {error}')
            if is_password_error(error):
                path, from_end, page = self.loading_request
                password = ask_password(path, error, self)
                if password is not None:
                    self.pending_file = (path, from_end, page, password)
            self._refresh_siblings()
            return
        self.pages, self.page, self.images = result
        self.shown_page = self.page
        self.previous_starts.clear()
        self.displayed_pages = (self.page,)
        self._configure_file()
        self._update_spread()
        self.page_cache.update(self.images, self.shown_page, self.displayed_pages[-1])
        self.statusBar().clearMessage()

    def _choose_file(self):
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open comic', str(self.pages.path.parent), 'Comic archives (*.cbz *.CBZ)')
        if path:
            self._request_file(path)

    def go_to_page(self):
        if self.closing or self.file_loading:
            return
        number, accepted = qt.QInputDialog.getInt(self, 'Go to page',
            f'Page (of {len(self.pages.pages)}):', self.shown_page + 1, 1, len(self.pages.pages))
        if accepted:
            self.go(number - 1)
            self.canvas.setFocus()

    def edit_metadata(self):
        from .metadata_editor import MetadataEditor
        from commonUtils.ui.document_host import show_document, document_is_open
        existing = next((window for window in self.metadata_windows
                         if window.targets == (self.pages.path,) and document_is_open(window)), None)
        if existing is not None:
            show_document(existing)
            return existing
        for window in list(self.metadata_windows):
            if not document_is_open(window) and not window.busy:
                self.metadata_windows.remove(window)
                window.deleteLater()
        self._refresh_siblings()
        editor = MetadataEditor(self.pages.path, self.siblings, self)
        self.metadata_windows.append(editor)
        editor.idle.connect(self.idle)
        editor.saved.connect(self._metadata_saved)
        show_document(editor)
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
        self.menus.fullscreen.toggle()

    def leave_fullscreen(self):
        self.menus.fullscreen.leave()

    def _cache_idle(self):
        if self.closing:
            from commonUtils.ui.document_host import close_document
            close_document(self)

    def shutdown(self):
        self.keys.stop()
        self.page_cache.stop()
        self.closing = True
        if self.page_cache.busy:
            self.page_cache.operation.wait()
        if self.busy:
            self.operation.wait()
        for window in self.metadata_windows:
            if window.busy:
                window.operation.wait()

    def request_close(self):
        from commonUtils.ui.document_host import CloseOutcome, close_document
        accepted = close_document(self)
        pending = self.busy or self.page_cache.busy or any(window.busy for window in self.metadata_windows)
        if pending:
            return CloseOutcome.PENDING
        return CloseOutcome.ACCEPTED if accepted else CloseOutcome.VETOED

    def closeEvent(self, event):
        from commonUtils.ui.document_host import host_keeps_document
        owned = [window for window in self.metadata_windows if not host_keeps_document(window)]
        if any(window.busy for window in owned):
            event.ignore()
            return
        for window in owned:
            if window.isVisible():
                window.reject()
        self.keys.stop()
        self.page_cache.stop()
        self.closing = True
        if self.busy or self.page_cache.busy:
            self.hide()
            event.ignore()
        else:
            event.accept()
            self.closed.emit()
