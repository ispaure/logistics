"""Project-owned shared buffers with independently navigable editor views."""
from pathlib import Path
import re
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
    link_requested = qt.Signal(object)

    def __init__(self, snapshot=None, parent=None, *, buffer=None):
        self.link_token = None
        self.link_selection = None
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.link_timer = qt.QTimer(self)
        self.link_timer.setInterval(80)
        self.link_timer.timeout.connect(self.poll_link)
        self.textChanged.connect(self.clear_link)
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

    def setExtraSelections(self, selections):
        # Keep the shared editor's line, search and bracket overlays intact.
        link = getattr(self, 'link_selection', None)
        super().setExtraSelections(list(selections) + ([link] if link else []))

    def clear_link(self):
        had_selection = self.link_selection is not None
        self.link_token = None
        self.link_selection = None
        self.viewport().setCursor(qt.Qt.CursorShape.IBeamCursor)
        if had_selection:
            self.highlight_cursor()

    def viewportEvent(self, event):
        if event.type() == qt.QEvent.Type.Enter:
            self.link_timer.start()
        elif event.type() in (qt.QEvent.Type.Leave, qt.QEvent.Type.Hide):
            self.link_timer.stop()
            self.clear_link()
        result = super().viewportEvent(event)
        if event.type() == qt.QEvent.Type.MouseMove:
            self.poll_link()
        return result

    def poll_link(self):
        point = self.viewport().mapFromGlobal(qt.QCursor.pos())
        enabled = (self.isVisible() and self.window().isActiveWindow()
                   and self.viewport().rect().contains(point)
                   and qt.QApplication.keyboardModifiers() & qt.Qt.KeyboardModifier.ControlModifier)
        self.update_link(point, bool(enabled))

    def update_link(self, point, enabled):
        if not enabled or self.path.suffix.lower() not in ('.py', '.pyi'):
            self.clear_link()
            return
        self.viewport().setCursor(qt.Qt.CursorShape.PointingHandCursor)
        cursor = self.cursorForPosition(point)
        text = cursor.block().text()
        column = len(text.encode('utf-16-le')[:cursor.positionInBlock() * 2].decode('utf-16-le'))
        match = next((m for m in re.finditer(r'[^\W\d]\w*', text)
                      if m.start() <= column <= m.end()), None)
        if match:
            start = cursor.block().position() + len(text[:match.start()].encode('utf-16-le')) // 2
            end = cursor.block().position() + len(text[:match.end()].encode('utf-16-le')) // 2
            cursor.setPosition(start)
            left = self.cursorRect(cursor)
            cursor.setPosition(end)
            right = self.cursorRect(cursor)
            if not (left.top() <= point.y() <= left.bottom() and left.x() <= point.x() < right.x()):
                match = None
        if not match:
            self.link_token = None
            self.link_selection = None
            self.highlight_cursor()
            return
        token = (self.path, self.document().revision(), start, end)
        if token == self.link_token:
            return
        self.link_token = token
        self.link_selection = None
        self.highlight_cursor()
        self.link_requested.emit((token, cursor.blockNumber() + 1, match.start() + 1))

    def show_link(self, token, reachable):
        if token != self.link_token:
            return
        self.link_selection = None
        if reachable:
            selection = qt.QTextEdit.ExtraSelection()
            selection.cursor = qt.QTextCursor(self.document())
            selection.cursor.setPosition(token[2])
            selection.cursor.setPosition(token[3], qt.QTextCursor.MoveMode.KeepAnchor)
            selection.format.setForeground(qt.QColor('#268bd2'))
            selection.format.setFontUnderline(True)
            self.link_selection = selection
        self.highlight_cursor()

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
        self.link_timer.stop()
        self.clear_link()
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
