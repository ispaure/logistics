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
        self.layout.setAlignment(qt.Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.body)
        self.cards = []
        self.editors = []
        self.height_timer = qt.QTimer(self)
        self.height_timer.setSingleShot(True)
        self.height_timer.timeout.connect(self._update_heights)

    def render(self, view, context):
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.cards = []; self.editors = []
        for index, (start, label) in enumerate(view.hunks):
            end = view.hunks[index + 1][0] if index + 1 < len(view.hunks) else len(view.lines)
            lines = view.lines[start + 1:end]
            if lines and not lines[-1].text and not lines[-1].kind: lines = lines[:-1]
            card = qt.QFrame()
            card.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Maximum)
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
            editor.diff_color_overrides = getattr(self.preview, 'diff_color_overrides', {})
            editor.setReadOnly(True); editor.indent_guides = False
            editor.setFont(self.preview.editor.font())
            from services.editors.ui.fonts import code_font
            code_font().bind(editor)
            editor.setAccessibleName(label)
            editor.highlighter = DiffHighlighter(editor)
            editor.set_diff(DiffView(lines=lines))
            editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth if self.preview.wrap.isChecked()
                                   else qt.QPlainTextEdit.LineWrapMode.NoWrap)
            box.addWidget(editor)
            self.layout.addWidget(card)
            self.cards.append(card); self.editors.append(editor)
            editor.installEventFilter(self)
            editor.document().documentLayout().documentSizeChanged.connect(self._schedule_heights)
            self._height(editor)
        self._schedule_heights()

    def _schedule_heights(self, *args):
        # Wait until the scroll area's layout has assigned the final card width.
        self.height_timer.start(0)

    def _update_heights(self):
        for card, editor in zip(self.cards, self.editors):
            self._height(editor)
            # Give the outer layout the same height as the actual card. Native
            # styles can otherwise reserve height-for-width space which a
            # Maximum-policy widget does not occupy, enlarging the visible gap.
            box = card.layout()
            height = max(box.totalMinimumSize().height(), box.totalHeightForWidth(card.width()))
            if card.height() != height:
                card.setFixedHeight(height)

    def eventFilter(self, watched, event):
        if event.type() in (qt.QEvent.Type.Resize, qt.QEvent.Type.FontChange):
            self._schedule_heights()
        return super().eventFilter(watched, event)

    def _height(self, editor):
        # Measuring blocks also lays out wrapped text at the current viewport width.
        height = 0
        for i in range(editor.blockCount()):
            block = editor.document().findBlockByNumber(i)
            editor.blockBoundingRect(block)
            height += block.layout().boundingRect().height()
        # A little breathing room also avoids a one-line scroll from Qt's rounding.
        height += 2 * editor.document().documentMargin() + 2 * editor.frameWidth() + 4
        if not self.preview.wrap.isChecked() and editor.horizontalScrollBar().maximum() > 0:
            height += editor.horizontalScrollBar().sizeHint().height()
        height = min(4096, max(48, int(height + .999)))
        if editor.height() != height:
            editor.setFixedHeight(height)

    def set_wrap(self, enabled):
        for editor in self.editors:
            editor.setLineWrapMode(qt.QPlainTextEdit.LineWrapMode.WidgetWidth if enabled
                                   else qt.QPlainTextEdit.LineWrapMode.NoWrap)
            self._height(editor)
        self._schedule_heights()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_heights()
