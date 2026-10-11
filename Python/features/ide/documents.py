"""Project-owned shared buffers with independently navigable editor views."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from commonUtils.ui.code_editor.syntax import SyntaxHighlighter, detect_language
from commonUtils.persistence.text import read_text_file, write_text_file, decode_bytes


class DocumentBuffer(qt.QObject):
    """Own the text and disk snapshot independently of any particular tab."""
    def __init__(self, snapshot, editor, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.text = editor.document()
        self.text.setParent(self)
        self.views = []
        self.highlighter = None

    def configure(self):
        editor = self.views[0]
        language = detect_language(self.snapshot.path, self.text.toPlainText())
        if self.highlighter is None:
            self.highlighter = SyntaxHighlighter(editor, language)
        else:
            self.highlighter.rebind_editor(editor)
            self.highlighter.configure(language)
        for view in self.views:
            view.comment_prefix = editor.comment_prefix


class EditorDocument(CodeEdit):
    """One view; snapshot, modified state, undo and file identity are shared."""
    def __init__(self, snapshot=None, parent=None, *, buffer=None):
        super().__init__(parent)
        if buffer is None:
            self.buffer = DocumentBuffer(snapshot, self, parent or self)
            self.setPlainText(snapshot.text)
            self.document().setModified(False)
        else:
            self.buffer = buffer
            self.share_document_from(buffer.views[0])
        self.buffer.views.append(self)
        if self.buffer.highlighter is None:
            self.buffer.configure()

    @property
    def snapshot(self):
        return self.buffer.snapshot

    @property
    def path(self):
        return self.snapshot.path

    @property
    def title(self):
        return self.path.name + (' *' if self.document().isModified() else '')

    def release(self):
        """Detach a closing view before its Qt widget is destroyed."""
        buffer = self.buffer
        primary = buffer.views[0] is self
        buffer.views.remove(self)
        if buffer.views and primary:
            buffer.configure()
        elif not buffer.views:
            buffer.deleteLater()
        self.detach_document()
        self.deleteLater()

    def save(self, path=None, *, expected=None):
        target = Path(path).resolve() if path else self.path
        content = self.snapshot.encode(self.toPlainText())
        write_text_file(target, content,
                        expected=self.snapshot.original if target == self.path else expected,
                        allow_overwrite=expected is not None)
        self.buffer.snapshot = decode_bytes(content, path=target, encoding=self.snapshot.encoding)
        self.document().setModified(False)
        self.buffer.configure()

    def reload(self):
        snapshot = read_text_file(self.path, encoding=self.snapshot.encoding)
        self.setPlainText(snapshot.text)
        self.buffer.snapshot = snapshot
        self.document().setModified(False)
        self.buffer.configure()
