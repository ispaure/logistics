"""Per-browser routing for archive feature actions and mutation refreshes."""
from pathlib import Path
from weakref import WeakSet
from commonUtils.ui import pyside as qt
from commonUtils.archives import is_supported_archive
from .page import ArchivePage
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
        """Use a live contributed page in this window, or a retained standalone host."""
        if self.closing:
            return None
        if not separate:
            for page in self.host.window().findChildren(ArchivePage):
                if page.closing:
                    continue
                parent = page.parentWidget()
                while parent is not None:
                    if isinstance(parent, qt.QTabWidget) and parent.indexOf(page) >= 0:
                        parent.setCurrentWidget(page)
                        self.host.window().show()
                        self.host.window().raise_()
                        return self._connect(page)
                    parent = parent.parentWidget()
            if self._window is not None and not self._window.page.closing:
                self._window.show()
                self._window.raise_()
                return self._connect(self._window.page)
        window = ArchiveWindow()
        if not separate:
            self._window = window
            window.destroyed.connect(lambda: self._window_closed(window))
        window.show()
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
        supported = [path for path in paths if is_supported_archive(path)]
        for index, path in enumerate(supported):
            page = self.workspace(separate=index > 0)
            if self._ready(page):
                if extract:
                    page.extract_path(path)
                else:
                    page.open_archive(path)

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
        # Independent hosts own and cancel their own workers. The contributed
        # main page participates directly in the main-window close protocol.
        self.closing = True
        return True
