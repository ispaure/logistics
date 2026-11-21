"""Prepare durable local copies before offering provider files to a file manager."""
from pathlib import Path

from commonUtils.filesystem.local_access import check_local_path
from commonUtils.runtime.resources.local import LocalFiles
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress

from .browser_moves import MoveSource, copy_selection
from .browser_transfer_view import present_browser_transfer
from .native_file_drag import handoff_message, start_file_drag


class PreparedFiles(qt.QListWidget):
    def __init__(self, paths, status):
        super().__init__()
        self.paths = paths
        self.status = status
        self.setDragEnabled(True)
        self.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setAccessibleName('Prepared files. Drag the selected items to your file manager.')
        self.addItems([path.name for path in paths])
        self.selectAll()

    def startDrag(self, _actions):
        paths = tuple(self.paths[self.row(item)] for item in self.selectedItems())
        if not paths:
            return
        try:
            self.status.setText(handoff_message(start_file_drag(self, paths)))
        except (OSError, ValueError) as error:
            self.status.setText(str(error))


class BrowserExport(qt.QObject):
    def __init__(self, host, layout, menu):
        super().__init__(host)
        self.host = host
        self.operation = OperationProgress(host)
        self.operation.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.operation.completed.connect(self._finish)
        self.release = None
        layout.addWidget(self.operation)
        self.action = menu.addAction('Prepare Selected Items to Drag…', self.prepare)
        menu.aboutToShow.connect(self.update_action)
        host._private_view_guard.revoked.connect(self.operation.request_cancel)

    def available(self):
        browser = self.host.file_browser
        moves = getattr(self.host, 'move_actions', None)
        opening = getattr(self.host, 'open_operation', None) or getattr(self.host, 'operation', None)
        return (not self.host.closing and self.host.isEnabled() and browser.isEnabled() and not browser.busy
                and not self.operation.busy and not (moves and moves.busy) and not (opening and opening.busy))

    def update_action(self):
        self.action.setEnabled(self.available() and bool(self.host.file_browser.selected_rows()))

    def prepare(self):
        if not self.available():
            return
        provider = self.host.provider
        sources = tuple(MoveSource(provider, row['path'], row.get('revision'))
                        for row in self.host.file_browser.selected_rows())
        if not sources:
            return
        folder = qt.QFileDialog.getExistingDirectory(self.host, 'Save local copies for dragging')
        if not folder or not self.available():
            return
        title = 'Prepare local copies'
        confirm = qt.QMessageBox.question(self.host, title,
            'Save readable copies in the chosen folder? The published copies will remain accessible after you lock the source.',
            qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        if confirm != qt.QMessageBox.StandardButton.Yes or not self.available():
            return
        try:
            directory = Path(folder)
            check_local_path(directory)
            destination = LocalFiles(directory)
            self.release = provider.acquire()
        except (OSError, ValueError) as error:
            qt.QMessageBox.warning(self.host, title, str(error))
            return
        self.operation.start(lambda report, cancelled: copy_selection(
            sources, destination, '', report=report, cancelled=cancelled), message='Preparing local copies…')
        window = present_browser_transfer(self.operation, title, provider=provider)
        window.runner.completed.connect(lambda _result: self._offer_drag(window),
                                        qt.Qt.ConnectionType.SingleShotConnection)

    def _finish(self, result, error):
        if self.release is not None:
            self.release()
            self.release = None
        self.prepared = tuple(path for _, path in result.completed) if result is not None else ()
        if not self.host.closing:
            if error or result is not None and result.issues:
                self.operation.message.setText(error or '\n'.join(result.issues))
        self.host.idle.emit()

    def _offer_drag(self, window):
        if not self.prepared or window.closing or window._private_view_guard.locked:
            return
        status = qt.QLabel('Drag the selected local copies to your file manager.')
        status.setWordWrap(True)
        status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout = window.layout()
        layout.insertWidget(layout.count() - 1, status)
        layout.insertWidget(layout.count() - 1, PreparedFiles(self.prepared, status))

    def stop(self):
        self.operation.request_cancel()
        return self.operation.busy
