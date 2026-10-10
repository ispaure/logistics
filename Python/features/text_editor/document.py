"""Application document metadata around the shared editing widget."""

from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.views import EditorViews
from commonUtils.text_files import TextSnapshot


class Document(qt.QWidget):
    changed = qt.Signal()

    def __init__(self, snapshot=None, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot or TextSnapshot(None, b"", "")
        self.encoding = self.snapshot.encoding
        self.newline_override = None
        self.bom_override = None
        self.simple = len(self.snapshot.original) > 1024 * 1024
        self.external_changed = False
        self.external_acknowledged = False
        self.language = "text"
        self.views = EditorViews(self)
        self.views.active_changed.connect(self.changed)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.views)
        self.editor.setPlainText(self.snapshot.text)
        self.editor.document().setModified(False)
        self.editor.document().modificationChanged.connect(self.changed)
        self.editor.cursorPositionChanged.connect(self.changed)
        self.editor.focused.connect(self.changed)

    @property
    def editor(self):
        return self.views.active

    @property
    def path(self):
        return self.snapshot.path

    @property
    def modified(self):
        return self.editor.document().isModified()

    @property
    def title(self):
        return (self.path.name if self.path else "Untitled") + (
            " *" if self.modified else ""
        )

    def contents(self):
        return self.snapshot.encode(
            self.editor.toPlainText(),
            encoding=self.encoding,
            newline=self.newline_override,
            bom=self.bom_override,
        )

    def replace(self, snapshot):
        self.snapshot = snapshot
        self.encoding = snapshot.encoding
        self.newline_override = None
        self.bom_override = None
        self.external_changed = False
        self.external_acknowledged = False
        self.simple = len(snapshot.original) > 1024 * 1024
        self.editor.setPlainText(snapshot.text)
        self.editor.document().setModified(False)
        self.changed.emit()
