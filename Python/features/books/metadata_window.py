"""Standalone metadata workflow; never constructs a reader or reading state."""
from commonUtils.ui import pyside as qt
from .epub import EPUBBook
from .metadata import save_metadata
from .metadata_editor import MetadataEditor
from .tasks import BookTask


class MetadataWindow(qt.QDialog):
    idle = qt.Signal()
    saved = qt.Signal(object)

    def __init__(self, path, parent=None):
        super().__init__(parent, qt.Qt.WindowType.Window)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Edit EPUB metadata')
        self.resize(650, 720)
        self.book = None
        self.editor = None
        self.worker = None
        self._close_pending = False
        self.layout = qt.QVBoxLayout(self)
        self.status = qt.QLabel('Loading EPUB metadata…')
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.layout.addWidget(self.status)
        self.close_buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Close)
        self.close_buttons.rejected.connect(self.close)
        self.layout.addWidget(self.close_buttons)
        self._run(lambda cancelled: EPUBBook(path), self._loaded)

    def _run(self, operation, done):
        task = BookTask(operation, self)
        self.worker = task
        if self.editor:
            self.editor.setEnabled(False)
        self.close_buttons.show()
        def finished():
            self.worker = None
            try:
                if self._close_pending:
                    self.close()
                    return
                if self.editor:
                    self.editor.setEnabled(True)
                    self.close_buttons.hide()
                if task.error:
                    self.status.setText(task.error)
                else:
                    done(task.result)
            except Exception as error:
                self.status.setText(str(error))
            finally:
                task.deleteLater()
                self.idle.emit()
        task.finished.connect(finished)
        task.start()

    def _loaded(self, book):
        self.book = book
        self.editor = MetadataEditor(book, self, save_handler=self._save)
        self.editor.setWindowFlags(qt.Qt.WindowType.Widget)
        self.editor.rejected.connect(self.close)
        self.layout.insertWidget(0, self.editor, 1)
        self.editor.show()
        self.status.clear()
        self.close_buttons.hide()

    def _save(self, changes):
        if self.worker:
            return
        if not changes:
            self.close()
            return
        self.status.setText('Saving metadata and backing up the original…')
        def saved(result):
            self.book, backup = result
            self.saved.emit(self.book.path)
            self.close()
        self._run(lambda cancelled: save_metadata(self.book, changes, cancelled=cancelled), saved)

    def prepare_close(self):
        if self.worker:
            self._close_pending = True
            self.worker.requestInterruption()
            return False
        return True

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()

    def reject(self):
        self.close()
