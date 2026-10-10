"""Separate selectable diff cards with feature-owned hunk controls."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor.diff_bands import DiffEdit, DiffHighlighter
from ..diff_view import DiffView


class HunkCards(qt.QScrollArea):
    def __init__(self, preview):
        super().__init__(preview)
        self.preview = preview
        self.setWidgetResizable(True)
        self.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.body = qt.QWidget()
        self.layout = qt.QVBoxLayout(self.body)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.setWidget(self.body)
        self.cards = []
        self.editors = []

    def render(self, view, context):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.cards = []; self.editors = []
        for index, (start, label) in enumerate(view.hunks):
            end = view.hunks[index + 1][0] if index + 1 < len(view.hunks) else len(view.lines)
            lines = view.lines[start + 1:end]
            if lines and not lines[-1].text and not lines[-1].kind: lines = lines[:-1]
            card = qt.QFrame()
            card.setFrameShape(qt.QFrame.Shape.StyledPanel)
            box = qt.QVBoxLayout(card)
            box.setContentsMargins(0, 0, 0, 0); box.setSpacing(0)
            header = qt.QWidget(card)
            header.setAutoFillBackground(True)
            header.setBackgroundRole(qt.QPalette.ColorRole.AlternateBase)
            row = qt.QHBoxLayout(header)
            row.setContentsMargins(8, 5, 8, 5)
            title = qt.QLabel(label)
            title.setTextFormat(qt.Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            row.addWidget(title, 1)
            if context is not None:
                actions = [('Unstage Hunk' if context['staged'] else 'Stage Hunk', 'unstage' if context['staged'] else 'stage')]
                if not context['staged']: actions.append(('Discard Hunk…', 'discard'))
                for text, action in actions:
                    button = qt.QToolButton(header); button.setText(text)
                    button.setEnabled(context['allowed'])
                    button.setToolTip(context.get('reason', '') or text)
                    button.clicked.connect(lambda checked=False, index=index, action=action, context=context:
                                           self.preview.hunk_requested.emit(context, index, action))
                    row.addWidget(button)
            box.addWidget(header)
            editor = DiffEdit()
            editor.setReadOnly(True); editor.indent_guides = False
            editor.setFont(self.preview.editor.font())
            editor.setAccessibleName(label)
            editor.highlighter = DiffHighlighter(editor)
            editor.set_diff(DiffView(lines=lines))
            editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth if self.preview.wrap.isChecked()
                                   else qt.QPlainTextEdit.LineWrapMode.NoWrap)
            box.addWidget(editor)
            self.layout.addWidget(card)
            self.cards.append(card); self.editors.append(editor)
            editor.textChanged.connect(lambda editor=editor: self._height(editor))
            self._height(editor)
        self.layout.addStretch()

    def _height(self, editor):
        lines = (sum(max(1, editor.document().findBlockByNumber(i).layout().lineCount())
                     for i in range(editor.blockCount())) if self.preview.wrap.isChecked() else editor.blockCount())
        height = max(1, lines) * editor.fontMetrics().lineSpacing() + 12
        if not self.preview.wrap.isChecked(): height += editor.horizontalScrollBar().sizeHint().height()
        editor.setFixedHeight(min(4096, max(48, height)))

    def set_wrap(self, enabled):
        for editor in self.editors:
            editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth if enabled
                                   else qt.QPlainTextEdit.LineWrapMode.NoWrap)
            self._height(editor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for editor in self.editors: self._height(editor)
