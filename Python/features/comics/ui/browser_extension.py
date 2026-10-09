"""Per-window Comics controller; the feature declaration installs its capabilities."""

from commonUtils.ui import pyside as qt
from .browser_services import ComicBrowserServices


class ComicBrowserExtension(qt.QObject, ComicBrowserServices):
    suggestions_changed = qt.Signal(object)
    idle = qt.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.browser_host = host
        self.file_browser = host.file_browser
        self.model = self.file_browser.model
        self.metadata_windows = []
        self.reader_connections = []
        self.reader_busy = False
        self.close_after_catalog = False
        self.suggestions = {}

    def _metadata_saved(self, path):
        self.file_browser.refresh_item(path)

    def _reader_finished(self):
        ComicBrowserServices._reader_finished(self)
        self._notify_idle()

    def _notify_idle(self):
        if self.close_after_catalog:
            self.idle.emit()

    def prepare_close(self):
        from commonUtils.ui.document_host import host_keeps_document
        self.close_after_catalog = True
        books = getattr(self, '_books_metadata_controller', None)
        if books is not None and not books.prepare_close():
            return False
        if self.reader_busy:
            return False
        for window in self.metadata_windows:
            if host_keeps_document(window):
                continue
            if window.busy:
                # Saves may use a new Operation after initial metadata loading.
                window.operation.finished.connect(self._notify_idle)
                return False
            if window.isVisible():
                window.reject()
                if window.isVisible():
                    return False
        return True
