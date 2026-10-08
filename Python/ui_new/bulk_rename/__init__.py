"""Reusable bulk rename widget/window. Requires an existing QApplication."""
from commonUtils.ui import pyside as qt
from .widget import BulkRenameWidget


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
        file_menu = self.menuBar().addMenu('File')
        file_menu.addAction('Open folder…', self.renamer._browse, qt.QKeySequence(qt.QKeySequence.StandardKey.Open))
        file_menu.addAction('Load rules…', self.renamer.load_preset)
        file_menu.addAction('Save rules…', self.renamer.save_preset)
        file_menu.addSeparator()
        file_menu.addAction('Close', self.close, qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        edit_menu = self.menuBar().addMenu('Edit')
        edit_menu.addAction('Select all', self.renamer.table.selectAll,
                            qt.QKeySequence(qt.QKeySequence.StandardKey.SelectAll))
        edit_menu.addAction('Undo last rename', self.renamer.undo,
                            qt.QKeySequence(qt.QKeySequence.StandardKey.Undo))
        edit_menu.addAction('Reset rules', lambda: self.renamer.reset_button.click())
        self._help_menu = self.menuBar().addMenu('Help')
        self._help_menu.addAction('Bulk rename guide', self._show_help)

    def _show_help(self):
        from pathlib import Path
        from commonUtils.ui.markdown import open_markdown
        open_markdown(Path(__file__).with_name('README.md'), parent=self)

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


def open_bulk_rename(directory=None, *, paths=(), parent=None):
    """Open a retained window for a directory, or just the explicitly supplied paths."""
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
        window.renamer.renamed.connect(lambda receipt: ctx.browser.refresh())
        return window
    return (BrowserAction('bulk.rename', 'Bulk rename…', run, source='Files'),)


__all__ = ['BulkRenameWidget', 'BulkRenameWindow', 'open_bulk_rename', 'bulk_rename_actions']
