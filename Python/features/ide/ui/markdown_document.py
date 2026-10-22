"""Embed the shared Markdown editor in project-owned file tabs."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.markdown import MarkdownViewer
from features.ide.ui.documents import DocumentBuffer, EditorDocument


class MarkdownBuffer(DocumentBuffer):
    def configure(self):
        for view in self.views:
            view._loaded_path = self.snapshot.path
            view.history = [{'url': qt.QUrl.fromLocalFile(str(self.snapshot.path)), 'scroll': 0}]
            view.history_index = 0
            view._source_bytes = self.snapshot.original
            view._update_buttons()
            view._source_changed()


class MarkdownDocument(MarkdownViewer):
    focused = qt.Signal()
    cursorPositionChanged = qt.Signal()

    def __init__(self, snapshot=None, parent=None, *, buffer=None):
        self._syncing = False
        self.workspace = parent
        super().__init__(parent=parent, allow_edit=True)
        if buffer is None:
            self.buffer = MarkdownBuffer(snapshot, self.editor, parent or self)
            self.editor.setPlainText(snapshot.text)
            self.editor.document().setModified(False)
        else:
            self.buffer = buffer
            self.editor.setDocument(buffer.text)
            buffer.text.modificationChanged.connect(self._modified_changed)
        self.buffer.views.append(self)
        self.editor.textChanged.connect(self._source_changed)
        self.buffer.configure()
        self.set_editing(True)
        # The project owns file operations and standard edit shortcuts. Keep
        # Markdown-specific formatting actions local to this tab.
        for action in (self.new_action, self.open_action, self.save_action,
                       self.save_as_action, self.undo_action, self.redo_action,
                       self.cut_action, self.copy_action, self.paste_action,
                       self.select_all_action, self.find_action):
            action.setShortcuts([])
        self.new_action.setEnabled(False)
        self.open_action.setEnabled(False)
        for shortcut in (self.back_shortcut, self.forward_shortcut):
            shortcut.setEnabled(False)
        for widget in (self.editor, self.formatted_editor, self.browser):
            widget.installEventFilter(self)
            widget.cursorPositionChanged.connect(self.cursorPositionChanged)

    def eventFilter(self, watched, event):
        if event.type() == qt.QEvent.Type.FocusIn:
            self.focused.emit()
        return super().eventFilter(watched, event)

    def _formatted_changed(self):
        super()._formatted_changed()
        if hasattr(self, 'buffer') and not self._syncing and self._rich_pending():
            self._syncing = True
            try:
                self.markdown_text()
            finally:
                self._syncing = False

    def _source_changed(self):
        if self._syncing:
            return
        self._syncing = True
        try:
            if self.edit_button.isChecked() and self.edit_mode.currentData() == 'formatted':
                self._load_formatted()
            elif not self.edit_button.isChecked():
                self._render_source(self.editor.toPlainText())
        finally:
            self._syncing = False

    @property
    def snapshot(self):
        return self.buffer.snapshot

    @property
    def path(self):
        return self.snapshot.path

    @property
    def title(self):
        return self.path.name + (' *' if self.document().isModified() else '')

    def document(self):
        return self.editor.document()

    def toPlainText(self):
        return self.markdown_text()

    def textCursor(self):
        return self.editor.textCursor()

    def setTextCursor(self, cursor):
        self.set_edit_mode('source')
        self.set_editing(True)
        self.editor.setTextCursor(cursor)

    def centerCursor(self):
        self.editor.centerCursor()

    def blockCount(self):
        return self.editor.blockCount()

    def verticalScrollBar(self):
        return self.editor.verticalScrollBar()

    def setPlainText(self, text):
        self.editor.setPlainText(text)

    def setFocus(self, *args):
        target = self.active_editor() if self.edit_button.isChecked() else self.browser
        target.setFocus(*args)

    def edit_command(self, method):
        target = self.active_editor() if self.edit_button.isChecked() else self.browser
        if self.edit_button.isChecked() or method in ('copy', 'selectAll'):
            getattr(target, method)()

    def toggle_comment(self):
        self.set_edit_mode('source')
        cursor = self.editor.textCursor()
        cursor.insertText('<!-- ' + (cursor.selectedText() or 'comment') + ' -->')

    def save(self, path=None, *, expected=None):
        if path and Path(path).suffix.lower() not in ('.md', '.markdown'):
            raise ValueError('Choose a .md or .markdown filename for Markdown Save As.')
        EditorDocument.save(self, path, expected=expected)

    def save_document(self, path=None):
        return self.workspace.save_document(self)

    def save_as_dialog(self):
        return self.workspace.save_document(self, True)

    def reload(self):
        EditorDocument.reload(self)

    def follow_link(self, link):
        url = qt.QUrl(link)
        resolved = qt.QUrl.fromLocalFile(str(self.path)).resolved(url)
        if resolved.isLocalFile() and Path(resolved.toLocalFile()) != self.path:
            target = Path(resolved.toLocalFile())
            if target.suffix.lower() in ('.md', '.markdown'):
                editing = self.edit_button.isChecked()
                mode = self.edit_mode.currentData()
                def opened(view):
                    view.set_edit_mode(mode)
                    view.set_editing(editing)
                    view.browser.scrollToAnchor(resolved.fragment())
                    if editing and view.active_editor() is view.formatted_editor and resolved.fragment():
                        view._scroll_formatted_heading(resolved.fragment())
                self.workspace.open_path(target, on_open=opened)
                return
        super().follow_link(link)

    def release(self):
        self.speech.stop()
        if self._diagram_renderer:
            self._diagram_renderer.cancel()
        buffer = self.buffer
        self.editor.textChanged.disconnect(self._source_changed)
        buffer.text.modificationChanged.disconnect(self._modified_changed)
        buffer.views.remove(self)
        from commonUtils.ui.markdown.live_edit import SourceMarkdownEdit
        detached = SourceMarkdownEdit()
        document = detached.document()
        document.setParent(self.editor)
        self.editor.setDocument(document)
        detached.deleteLater()
        if not buffer.views:
            buffer.deleteLater()
        self.deleteLater()
