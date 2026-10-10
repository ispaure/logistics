"""Standalone host used by browser windows outside the main application."""
from commonUtils.ui import pyside as qt
from .page import ArchivePage

_windows = set()


class ArchiveWindow(qt.QMainWindow):
    def __init__(self):
        super().__init__(None, qt.Qt.WindowType.Window)
        self.setWindowTitle('Logistics · Archives')
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(1100, 700)
        self.page = ArchivePage(self)
        self.setCentralWidget(self.page)
        self.page.idle.connect(self._idle)
        _windows.add(self)
        self.destroyed.connect(lambda: _windows.discard(self))

    def _idle(self):
        if self.page.closing:
            qt.QTimer.singleShot(0, self, self.close)

    def closeEvent(self, event):
        if not self.page.prepare_close():
            event.ignore()
        else:
            super().closeEvent(event)
