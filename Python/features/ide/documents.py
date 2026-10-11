"""Project-owned buffers using the same editor and text IO as TextEditor."""
from pathlib import Path
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import SyntaxHighlighter, detect_language
from commonUtils.persistence.text import read_text_file, write_text_file, decode_bytes


class EditorDocument(CodeEdit):
    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.setPlainText(snapshot.text)
        self.document().setModified(False)
        self.highlighter = SyntaxHighlighter(self, detect_language(snapshot.path, snapshot.text))

    @property
    def path(self):
        return self.snapshot.path

    @property
    def title(self):
        return self.path.name + (' *' if self.document().isModified() else '')

    def save(self, path=None):
        target = Path(path).resolve() if path else self.path
        content = self.snapshot.encode(self.toPlainText())
        write_text_file(target, content,
                        expected=self.snapshot.original if target == self.path else None)
        self.snapshot = decode_bytes(content, path=target, encoding=self.snapshot.encoding)
        self.document().setModified(False)
        self.highlighter.configure(detect_language(target, self.toPlainText()))

    def reload(self):
        snapshot = read_text_file(self.path, encoding=self.snapshot.encoding)
        self.setPlainText(snapshot.text)
        self.snapshot = snapshot
        self.document().setModified(False)
