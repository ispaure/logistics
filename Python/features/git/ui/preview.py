"""Reuse the commonUtils code editor for selectable, searchable Git previews."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit


class DiffHighlighter(qt.QSyntaxHighlighter):
    def highlightBlock(self, text):
        color = ('#538bde' if text.startswith(('@@', 'diff ', 'commit ')) else
                 '#38965b' if text.startswith('+') else '#c55b62' if text.startswith('-') else None)
        if color:
            form = qt.QTextCharFormat()
            form.setForeground(qt.QColor(color))
            if text.startswith(('+','-')) and not text.startswith(('+++','---')):
                form.setBackground(qt.QColor('#193d32' if text.startswith('+') else '#4f2930'))
            self.setFormat(0, len(text), form)


class Preview(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = qt.QLabel('Select a changed file or commit')
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        row = qt.QHBoxLayout()
        row.addWidget(self.title,1)
        self.file_buttons=[]
        for label,name in (('Stage file','stage_button'),('Unstage file','unstage_button'),('Discard file…','discard_button')):
            button=qt.QToolButton(); button.setText(label); setattr(self,name,button)
            self.file_buttons.append(button); row.addWidget(button); button.hide()
        layout.addLayout(row)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Find in preview (Enter for next)')
        self.search.setAccessibleName('Find in Git preview')
        self.search.returnPressed.connect(self.find_next)
        layout.addWidget(self.search)
        self.editor = CodeEdit()
        self.editor.setReadOnly(True)
        self.editor.setAccessibleName('Git diff or historical file preview')
        self.highlighter = DiffHighlighter(self.editor.document())
        layout.addWidget(self.editor, 1)

    def hide_file_actions(self):
        for button in self.file_buttons: button.hide()

    def set_file_actions(self, staged, discardable):
        self.stage_button.setVisible(not staged)
        self.unstage_button.setVisible(staged)
        self.discard_button.setVisible(not staged and discardable)

    def show_text(self, title, text):
        self.title.setText(title)
        self.editor.setPlainText(text)

    def find_next(self):
        if not self.editor.find(self.search.text()):
            cursor = self.editor.textCursor()
            cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(self.search.text())
