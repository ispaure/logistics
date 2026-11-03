"""Embedded regular code-editor components with provider-owned persistence."""
from commonUtils.ui import pyside as qt
from commonUtils.persistence.text import decode_bytes
from commonUtils.ui.code_editor.search import SearchPanel
from commonUtils.ui.code_editor.syntax import SyntaxHighlighter
from commonUtils.ui.code_editor.widget import CodeEdit
from commonUtils.formats.code_language import LanguageSelection
from commonUtils.ui.tasks.operation_progress import OperationProgress


class LibraryTextEditor(qt.QWidget):
    saved = qt.Signal(str)
    idle = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.resource = None
        self.snapshot = decode_bytes(b'')
        self.editor = CodeEdit(self)
        self.language = LanguageSelection()
        self.highlighter = SyntaxHighlighter(self.editor)
        self.search = SearchPanel(self)
        self.search.set_editor(self.editor)
        self.search.idle.connect(self.idle)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self.completed)
        layout = qt.QVBoxLayout(self)
        row = qt.QHBoxLayout()
        self.title = qt.QLabel()
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.save_button = qt.QPushButton('Save')
        self.save_button.clicked.connect(self.save)
        find = qt.QPushButton('Find / replace…')
        find.clicked.connect(lambda: self.search.open(True))
        row.addWidget(self.title, 1)
        row.addWidget(find)
        row.addWidget(self.save_button)
        layout.addLayout(row)
        layout.addWidget(self.search)
        layout.addWidget(self.editor, 1)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addWidget(self.operation)
        self.operation.hide()
        self.find_shortcut = qt.QShortcut(qt.QKeySequence.StandardKey.Find, self)
        self.find_shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.find_shortcut.activated.connect(self.search.open)
        self.editor.document().modificationChanged.connect(self.update_title)

    @property
    def busy(self):
        return self.operation.busy

    @property
    def dirty(self):
        return self.editor.document().isModified()

    def load(self, resource, snapshot, *, writable):
        self.clear()
        self.resource, self.writable = resource, writable
        self.snapshot = snapshot
        self.editor.setPlainText(snapshot.text)
        self.editor.document().setModified(False)
        self.language.update(snapshot.path, snapshot.text)
        self.highlighter.configure(self.language.language_id)
        self.editor.folding.configure(self.language.language_id)
        self.editor.setReadOnly(not writable)
        self.save_button.setEnabled(writable)
        self.status.setText('' if writable else 'Read-only storage')
        self.update_title()

    def update_title(self):
        self.title.setText((self.snapshot.path.name if self.snapshot.path else '') + (' *' if self.dirty else ''))

    def save(self):
        if self.resource is None or self.busy or not self.writable:
            return False
        data = self.snapshot.encode(self.editor.toPlainText())
        resource, path = self.resource, self.snapshot.path
        self.editor.setReadOnly(True)
        self.save_button.setEnabled(False)
        def write(report, cancelled):
            resource.save(data, cancelled=cancelled)
            return decode_bytes(data, path=path)
        self.operation.start(write, message='Saving text…')
        return True

    def completed(self, snapshot, error):
        self.operation.hide()
        if self.resource is not None:
            self.editor.setReadOnly(not self.writable)
            self.save_button.setEnabled(self.writable)
            if not error:
                self.snapshot = snapshot
                self.editor.document().setModified(False)
                self.update_title()
            self.status.setText(error or 'Saved.')
        self.saved.emit(error)
        self.idle.emit()

    def can_leave(self):
        if self.busy:
            return False
        if not self.dirty:
            return True
        answer = qt.QMessageBox.question(self, 'Unsaved text changes', 'Save changes before leaving?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Cancel)
        if answer == qt.QMessageBox.StandardButton.Save:
            self.save()
            return False
        return answer == qt.QMessageBox.StandardButton.Discard

    def clear(self):
        self.search.close_panel()
        self.search.query.clear()
        self.search.replacement.clear()
        self.operation.request_cancel()
        if self.resource is not None:
            self.resource.close()
            self.resource = None
        self.snapshot = decode_bytes(b'')
        self.editor.clear()
        self.editor.document().setModified(False)
        self.highlighter.configure('text')
        self.update_title()
        self.status.clear()
