"""Per-browser routing for archive feature actions and mutation refreshes."""
from pathlib import Path
from weakref import WeakSet
from commonUtils.ui import pyside as qt
from commonUtils.archives import is_supported_archive
from .window import ArchiveWindow


class ArchiveBrowserController(qt.QObject):
    idle = qt.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.closing = False
        self._window = None
        self._pages = WeakSet()

    def _connect(self, page):
        if page not in self._pages:
            page.archive_changed.connect(self._changed)
            self._pages.add(page)
        return page

    def workspace(self, *, separate=False):
        """Create or reveal a retained archive document host."""
        if self.closing:
            return None
        from commonUtils.ui.document_host import show_document, document_is_open
        if not separate and self._window is not None and not self._window.page.closing and document_is_open(self._window):
            show_document(self._window)
            return self._connect(self._window.page)
        window = ArchiveWindow()
        if not separate:
            self._window = window
            window.destroyed.connect(lambda: self._window_closed(window))
        show_document(window)
        return self._connect(window.page)

    def _window_closed(self, window):
        if self._window is window:
            self._window = None

    def _ready(self, page):
        if page is None:
            return False
        if page.busy:
            page.status.setText('Finish or cancel the current archive operation before starting another.')
            return False
        return True

    def open(self, paths, *, extract=False):
        if self.closing:
            return
        supported = [path for path in paths if is_supported_archive(path)]
        for path in supported:
            from .window import open_archive_window
            if extract:
                page = self.workspace(separate=True)
            else:
                page = self._connect(open_archive_window(path).page)
                continue
            if self._ready(page):
                page.extract_path(path)

    def create(self, paths):
        page = self.workspace()
        if self._ready(page):
            page.new_archive(sources=paths)

    @qt.Slot(object)
    def _changed(self, path):
        if self.closing:
            return
        browser = getattr(self.host, 'file_browser', None)
        if browser is None or browser.navigation.library is None:
            return
        path = Path(path)
        if path.is_relative_to(browser.navigation.library):
            browser.refresh_item(path)
            browser.refresh_changed((path.parent,))

    def prepare_close(self):
        # Retained document hosts own and cancel their own workers; closing a
        # browser does not discard documents kept by the main document host.
        self.closing = True
        return True
