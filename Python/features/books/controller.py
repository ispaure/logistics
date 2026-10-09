"""Independent reading/editing windows share the browser's close lifecycle."""
from commonUtils.ui import pyside as qt
from .reader import BookWindow
from .metadata_window import MetadataWindow


class BooksController(qt.QObject):
    idle = qt.Signal()

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.browser = getattr(host, 'file_browser', host)
        self.windows = []

    def open(self, path, *, edit=False):
        window = MetadataWindow(path, parent=self.host) if edit else BookWindow(path, parent=self.host)
        self.windows.append(window)
        def removed():
            if window in self.windows:
                self.windows.remove(window)
            self.idle.emit()
        window.destroyed.connect(removed)
        if edit:
            window.idle.connect(self.idle)
            refresh = getattr(self.browser, 'refresh_item', None)
            if refresh:
                window.saved.connect(refresh)
        else:
            window.reader.idle.connect(self.idle)
        from ui_new.documents import show_document
        show_document(window)
        return window

    def prepare_close(self):
        ready = True
        for window in tuple(self.windows):
            if window.prepare_close():
                window.close()
            else:
                ready = False
        return ready
