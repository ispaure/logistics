"""Reusable bulk rename widget/window. Requires an existing QApplication."""
from commonUtils.ui import pyside as qt
from .widget import BulkRenameWidget
import weakref

_host = None


def register_bulk_rename_host(callback):
    global _host
    _host = weakref.WeakMethod(callback)



class BulkRenameWindow(qt.QMainWindow):
    def __init__(self, directory=None, parent=None, *, paths=()):
        super().__init__(parent)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Bulk Rename')
        self.renamer = BulkRenameWidget(directory, self, paths=paths)
        self.setCentralWidget(self.renamer)
        self.resize(1380, 950)
        self._closing = False
        self._owner = parent.window() if parent is not None else None
        self._owner_closing = False
        if self._owner is not None:
            self._owner.installEventFilter(self)
        self.renamer.idle.connect(self._close_when_idle)
        from .menus import build_menus
        self.header_menus = build_menus(self, self.renamer, self.close)

    def eventFilter(self, watched, event):
        if (watched is self._owner and event.type() == qt.QEvent.Type.Close
                and self.renamer.progress.busy):
            self._owner_closing = True
            self.renamer.progress.request_cancel()
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def _close_when_idle(self):
        if self._owner_closing:
            self._owner_closing = False
            owner = self._owner
            self.close()
            owner.close()
            return
        if self._closing:
            self.close()

    def closeEvent(self, event):
        if self.renamer.can_close():
            self.renamer.preview_timer.stop()
            super().closeEvent(event)
        else:
            self._closing = True
            event.ignore()


_windows = set()


def open_bulk_rename(directory=None, *, paths=(), parent=None, standalone=False):
    """Open a retained window for a directory, or just the explicitly supplied paths."""
    if not standalone and _host is not None:
        callback = _host()
        if callback is not None:
            from shiboken6 import isValid
            if isValid(callback.__self__.dlg):
                return callback(directory, paths=paths)
    window = BulkRenameWindow(directory, parent, paths=paths)
    _windows.add(window)
    window.destroyed.connect(lambda: _windows.discard(window))
    window.show()
    return window


def bulk_rename_actions(selected, context):
    """Opt-in FileBrowser action provider; refreshes the browser after rename or undo."""
    from commonUtils.filesystem import BrowserAction
    if not context.selection:
        return ()
    def run(ctx):
        window = open_bulk_rename(paths=[item.path for item in ctx.selection], parent=ctx.widget.window())
        renamer = window if isinstance(window, BulkRenameWidget) else window.renamer
        browsers = getattr(renamer, "_refresh_browsers", None)
        if not isinstance(browsers, weakref.WeakSet):
            browsers = renamer._refresh_browsers = weakref.WeakSet()
            def refresh(receipt):
                from shiboken6 import isValid
                for browser in tuple(browsers):
                    if not isinstance(browser, qt.QObject) or isValid(browser):
                        browser.refresh()
            renamer.renamed.connect(refresh)
        browsers.add(ctx.browser)
        return window
    return (BrowserAction('bulk.rename', 'Bulk Rename…', run, source='Files', category='rename', order=10),)


__all__ = ['BulkRenameWidget', 'BulkRenameWindow', 'open_bulk_rename', 'bulk_rename_actions']
