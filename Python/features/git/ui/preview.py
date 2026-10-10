"""Reuse the commonUtils code editor for selectable, searchable Git previews."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.code_editor import CodeEdit
import re


def diff_colors(palette, kind):
    dark = palette.base().color().lightness() < 128
    return ({'add': ('#76dfae', '#204c3d'), 'remove': ('#ff9caa', '#582d39'),
             'hunk': ('#a6cfff', '#2d3d56')} if dark else
            {'add': ('#17643d', '#d8f2e1'), 'remove': ('#a32238', '#fce0e4'),
             'hunk': ('#235a91', '#e0ebf8')})[kind]


class DiffEdit(CodeEdit):
    """Keep the shared editor, with old/new line numbers and visible diff bands."""
    def __init__(self):
        super().__init__()
        self.diff_rows = []
        self._bands_key = None
        self.textChanged.connect(self._read_diff)
        self.updateRequest.connect(self._refresh_bands)

    def _refresh_bands(self, *args):
        if self.diff_rows: self.highlight_cursor()

    def setPlainText(self, text):
        # The shared cursor handler runs before our textChanged handler.
        self.diff_rows = []
        self._bands_key = None
        super().setPlainText(text)

    def _read_diff(self):
        rows = []
        old = new = None
        for line in self.toPlainText().split('\n'):
            hunk = re.match(r'^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if hunk:
                old, new = map(int, hunk.groups())
                rows.append(('', '', 'hunk'))
            elif line.startswith('diff --git '):
                old = new = None
                rows.append(('', '', ''))
            elif old is not None and line.startswith(('+', '-', ' ')):
                kind = 'add' if line.startswith('+') else 'remove' if line.startswith('-') else ''
                rows.append(('' if kind == 'add' else str(old), '' if kind == 'remove' else str(new), kind))
                old += kind != 'add'
                new += kind != 'remove'
            else:
                rows.append(('', '', ''))
        self.diff_rows = rows if any(row[2] == 'hunk' for row in rows) else []
        self._bands_key = None
        self.update_gutter()
        self.gutter.setFixedWidth(self.gutter_width())
        self.highlight_cursor()

    def gutter_width(self):
        if not getattr(self, 'diff_rows', None): return super().gutter_width()
        digits = max(len(row[0]) for row in self.diff_rows) + max(len(row[1]) for row in self.diff_rows)
        return self.fontMetrics().horizontalAdvance('9') * digits + 24

    def paint_gutter(self, event):
        if not self.diff_rows: return super().paint_gutter(event)
        painter = qt.QPainter(self.gutter)
        painter.fillRect(event.rect(), self.palette().alternateBase())
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        half = self.gutter.width() // 2
        while block.isValid() and top <= event.rect().bottom():
            height = round(self.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                old, new, kind = self.diff_rows[block.blockNumber()]
                if kind:
                    painter.fillRect(0, top, self.gutter.width(), height,
                                     qt.QColor(diff_colors(self.palette(), kind)[1]))
                painter.setPen(self.palette().color(qt.QPalette.ColorRole.PlaceholderText))
                for x, number in ((0, old), (half, new)):
                    painter.drawText(x, top, half - 5, height, qt.Qt.AlignmentFlag.AlignRight, number)
            top += height
            block = block.next()

    def highlight_cursor(self, *args):
        if not getattr(self, 'diff_rows', None): return super().highlight_cursor()
        block = self.firstVisibleBlock()
        key = (block.blockNumber(), self.viewport().height(), self.font().key(),
               self.palette().cacheKey(), id(self.search_selections))
        if key == self._bands_key: return
        self._bands_key = key
        selections = []
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        while block.isValid() and top <= self.viewport().height():
            kind = self.diff_rows[block.blockNumber()][2]
            if kind:
                selection = qt.QTextEdit.ExtraSelection()
                selection.format.setBackground(qt.QColor(diff_colors(self.palette(), kind)[1]))
                selection.format.setProperty(qt.QTextFormat.Property.FullWidthSelection, True)
                selection.cursor = qt.QTextCursor(block)
                selections.append(selection)
            top += self.blockBoundingRect(block).height()
            block = block.next()
        self.setExtraSelections(selections + self.search_selections)
        self.gutter.update()


class DiffHighlighter(qt.QSyntaxHighlighter):
    def __init__(self, editor):
        super().__init__(editor.document())
        self.editor = editor

    def highlightBlock(self, text):
        kind = ('hunk' if text.startswith(('@@', 'diff ', 'commit ')) else
                'add' if text.startswith('+') else 'remove' if text.startswith('-') else None)
        if kind:
            form = qt.QTextCharFormat()
            form.setForeground(qt.QColor(diff_colors(self.editor.palette(), kind)[0]))
            if text.startswith('@@'): form.setFontWeight(qt.QFont.Weight.Bold)
            self.setFormat(0, len(text), form)


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
        layout.addLayout(row)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Find in preview (Enter for next)')
        self.search.setAccessibleName('Find in Git preview')
        self.search.returnPressed.connect(self.find_next)
        layout.addWidget(self.search)
        self.editor = DiffEdit()
        self.editor.setReadOnly(True)
        self.editor.setAccessibleName('Git diff or historical file preview')
        self.highlighter = DiffHighlighter(self.editor)
        layout.addWidget(self.editor, 1)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == qt.QEvent.Type.PaletteChange and hasattr(self, 'highlighter'):
            self.highlighter.rehighlight()

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
