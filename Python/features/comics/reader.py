"""Open and retain independent native comic reader windows."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from .pages import ComicPages
from .archive_io import archive_unchanged
from .ui.reader import ComicReaderWindow

_windows = []


def open_reader(comic):
    """Called on the GUI thread, optionally with pages prepared in a worker."""
    pages = comic if isinstance(comic, ComicPages) else ComicPages(Path(comic).absolute())
    existing = next((window for window in _windows if window.pages.path == pages.path
                     and not window.closing
                     and archive_unchanged(pages.path, window.pages.document.snapshot)), None)
    if existing is not None:
        existing.showNormal()
        existing.raise_()
        existing.activateWindow()
        return existing
    window = ComicReaderWindow(pages)
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    qt.QApplication.instance().aboutToQuit.connect(window.shutdown)
    window.show()
    return window
