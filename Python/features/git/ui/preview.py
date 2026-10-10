"""Reuse the commonUtils code editor for selectable, searchable Git previews."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
from ..diff_view import present_diff


from commonUtils.ui.code_editor.diff_bands import diff_colors, DiffEdit, DiffHighlighter


class Preview(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.title = qt.QLabel('Select a changed file or commit')
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        row = qt.QHBoxLayout()
        row.setContentsMargins(4,2,4,2)
        row.setSpacing(4)
        row.addWidget(self.title,1)
        self.file_buttons=[]
        for label,name in (('Stage file','stage_button'),('Unstage file','unstage_button'),('Discard file…','discard_button')):
            button=qt.QToolButton(); button.setText(label); setattr(self,name,button)
            self.file_buttons.append(button); row.addWidget(button); button.hide()
        self.compare_button = qt.QToolButton(); self.compare_button.setText("Compare sides…")
        self.compare_button.setToolTip("Review full file versions side by side")
        self.compare_button.hide(); row.addWidget(self.compare_button)
        layout.addLayout(row)
        self.summary = qt.QLabel()
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setContentsMargins(4, 0, 4, 0)
        self.summary.hide()
        layout.addWidget(self.summary)
        self.raw_patch = None
        self.diff_view = None
        controls = qt.QHBoxLayout()
        controls.setContentsMargins(2, 0, 2, 0)
        controls.setSpacing(4)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Find in preview (Enter for next)')
        self.search.setAccessibleName('Find in Git preview')
        self.search.returnPressed.connect(self.find_next)
        self.search.setClearButtonEnabled(True)
        controls.addWidget(self.search, 1)
        for label, name, step in (('↑', 'previous_hunk', -1), ('↓', 'next_hunk', 1)):
            button = qt.QToolButton(); button.setText(label)
            button.setToolTip('Previous hunk' if step < 0 else 'Next hunk')
            button.setAccessibleName(button.toolTip())
            button.clicked.connect(lambda checked=False, step=step: self.move_hunk(step))
            setattr(self, name, button); controls.addWidget(button)
        self.wrap = qt.QCheckBox('Wrap')
        self.wrap.setToolTip('Wrap long lines without horizontal scrolling')
        self.wrap.toggled.connect(lambda enabled: self.editor.setLineWrapMode(
            qt.QPlainTextEdit.LineWrapMode.WidgetWidth if enabled else qt.QPlainTextEdit.LineWrapMode.NoWrap))
        controls.addWidget(self.wrap)
        self.raw = qt.QCheckBox('Raw')
        self.raw.setToolTip('Show the original Git patch, including headers')
        self.raw.toggled.connect(self._render_diff)
        controls.addWidget(self.raw)
        self.ignore_whitespace = qt.QCheckBox('Ignore whitespace')
        self.ignore_whitespace.setToolTip('Hide whitespace-only differences while reviewing; file staging still includes all changes')
        controls.addWidget(self.ignore_whitespace)
        layout.addLayout(controls)
        self.editor = DiffEdit()
        self.editor.setReadOnly(True)
        self.editor.indent_guides = False
        self.editor.setAccessibleName('Git diff or historical file preview')
        self.highlighter = DiffHighlighter(self.editor)
        layout.addWidget(self.editor, 1)
        self._set_diff_controls(False)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, 'highlighter'):
            self.highlighter.rehighlight()

    def hide_file_actions(self):
        self.compare_button.hide()
        for button in self.file_buttons: button.hide()

    def set_file_actions(self, staged, discardable):
        self.stage_button.setVisible(not staged)
        self.unstage_button.setVisible(staged)
        self.discard_button.setVisible(not staged and discardable)

    def show_text(self, title, text):
        self.title.setText(title)
        self.raw_patch = self.diff_view = None
        self.summary.hide()
        self._set_diff_controls(False)
        self.editor.setPlainText(text)
        self.highlighter.rehighlight()

    def show_diff(self, title, patch):
        self.title.setText(title)
        self.raw_patch = patch
        self.diff_view = present_diff(patch)
        self.summary.setText(self.diff_view.summary)
        self.summary.show()
        self._set_diff_controls(True)
        self._render_diff()

    def _set_diff_controls(self, enabled):
        self.raw.setVisible(enabled)
        self.ignore_whitespace.setVisible(enabled)
        for button in (self.previous_hunk, self.next_hunk):
            button.setVisible(enabled)
            button.setEnabled(enabled and bool(self.diff_view and self.diff_view.hunks))

    def _render_diff(self, *args):
        if self.raw_patch is None: return
        self.editor.set_diff(self.diff_view, raw=self.raw.isChecked())
        self.highlighter.rehighlight()

    def move_hunk(self, step):
        if self.raw_patch is None: return
        if self.raw.isChecked():
            positions = [i for i, line in enumerate(self.diff_view.raw_lines) if line.kind == 'hunk']
        else: positions = [index for index, label in self.diff_view.hunks]
        if not positions: return
        current = self.editor.textCursor().blockNumber()
        choices = [index for index in positions if index > current] if step > 0 else [index for index in positions if index < current]
        target = (choices[0] if step > 0 else choices[-1]) if choices else (positions[0] if step > 0 else positions[-1])
        self.editor.setTextCursor(qt.QTextCursor(self.editor.document().findBlockByNumber(target)))
        self.editor.centerCursor()

    def find_next(self):
        if not self.editor.find(self.search.text()):
            cursor = self.editor.textCursor()
            cursor.movePosition(qt.QTextCursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(self.search.text())
