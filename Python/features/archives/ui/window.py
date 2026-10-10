"""Standalone host used by browser windows outside the main application."""
from commonUtils.ui import pyside as qt
from .page import ArchivePage

_windows = set()


class ArchiveWindow(qt.QMainWindow):
    document_editor_name = 'Archives'
    document_editor_id = 'archive'
    idle = qt.Signal()
    def __init__(self):
        super().__init__(None, qt.Qt.WindowType.Window)
        self.setWindowTitle('Logistics · Archives')
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1100, 700)
        self.page = ArchivePage(self)
        self.setCentralWidget(self.page)
        self.page.idle.connect(self._idle)
        self.page.idle.connect(self.idle)
        self.page.session.completed.connect(self._title_changed)
        _windows.add(self)
        self.destroyed.connect(lambda: _windows.discard(self))

    def _title_changed(self, *args):
        if self.page.path:
            self.setWindowTitle(self.page.path.name + ' — Archives')
            self.setWindowFilePath(str(self.page.path))

    def _idle(self):
        if self.page.closing:
            qt.QTimer.singleShot(0, self, self.close)

    def closeEvent(self, event):
        if not self.page.prepare_close():
            event.ignore()
        else:
            super().closeEvent(event)


def open_archive_window(path=None):
    from pathlib import Path
    from commonUtils.ui.document_host import show_document, document_is_open
    candidate = Path(path).absolute() if path else None
    existing = next((window for window in _windows if candidate is not None
                     and (window.page.path == candidate or getattr(window, '_requested_path', None) == candidate) and not window.page.closing
                     and document_is_open(window)), None)
    if existing is not None:
        show_document(existing)
        if existing.page.path is None and not existing.page.busy:
            existing.page.open_archive(candidate)
        return existing
    window = ArchiveWindow()
    window._requested_path = candidate
    if candidate:
        window.setWindowTitle(candidate.name + ' — Archives')
        window.setWindowFilePath(str(candidate))
    show_document(window)
    if candidate is not None:
        window.page.open_archive(candidate)
    return window
