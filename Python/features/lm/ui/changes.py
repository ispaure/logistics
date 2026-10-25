"""Clickable turn summaries and a read-only pane reusing Git's diff preview."""
from copy import deepcopy

from commonUtils.ui import pyside as qt


def counts(changes):
    return (f'<span style="color:#00a65a">+{sum(item["added"] for item in changes)}</span> '
            f'<span style="color:#e34b4b">-{sum(item["removed"] for item in changes)}</span>')


class FileDelegate(qt.QStyledItemDelegate):
    def sizeHint(self, option, index):
        return qt.QSize(120, max(34, option.fontMetrics.height() + 14))

    def paint(self, painter, option, index):
        change = index.data(qt.Qt.ItemDataRole.UserRole + 1)
        painter.save()
        painter.setFont(option.font)
        rect = option.rect.adjusted(10, 0, -10, 0)
        metrics = option.fontMetrics
        removed = f'-{change["removed"]}'
        added = f'+{change["added"]}'
        width = metrics.horizontalAdvance(removed)
        painter.setPen(qt.QColor('#e34b4b'))
        painter.drawText(rect, qt.Qt.AlignmentFlag.AlignRight | qt.Qt.AlignmentFlag.AlignVCenter, removed)
        rect.setRight(rect.right() - width - 6)
        painter.setPen(qt.QColor('#00a65a'))
        painter.drawText(rect, qt.Qt.AlignmentFlag.AlignRight | qt.Qt.AlignmentFlag.AlignVCenter, added)
        rect.setRight(rect.right() - metrics.horizontalAdvance(added) - 16)
        painter.setPen(option.palette.color(qt.QPalette.ColorRole.Text))
        path = change['path'] + (' · Undone' if change.get('undone') else '')
        painter.drawText(rect, qt.Qt.AlignmentFlag.AlignLeft | qt.Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(path, qt.Qt.TextElideMode.ElideMiddle, rect.width()))
        painter.restore()


def summary(changes):
    count = len(changes)
    return (f'Edited {count} file{"s" if count != 1 else ""} · '
            f'+{sum(item["added"] for item in changes)} −{sum(item["removed"] for item in changes)}')


class EditedFilesCard(qt.QFrame):
    file_requested = qt.Signal(str)
    undo_requested = qt.Signal()
    edit_requested = qt.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('editedFilesCard')
        self.setStyleSheet('QFrame#editedFilesCard { background: palette(base); border: 1px solid palette(mid); border-radius: 12px; }')
        self.setFrameShape(qt.QFrame.Shape.StyledPanel)
        self.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Maximum)
        self.box = qt.QVBoxLayout(self)
        self.box.setContentsMargins(12, 10, 12, 8)
        self.box.setAlignment(qt.Qt.AlignmentFlag.AlignTop)
        self.header = qt.QLabel()
        self.header.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.header.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        row = qt.QHBoxLayout()
        icon = qt.QLabel()
        icon.setPixmap(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon).pixmap(24, 24))
        row.addWidget(icon)
        titles = qt.QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(self.header)
        self.totals = qt.QLabel()
        self.totals.setTextFormat(qt.Qt.TextFormat.RichText)
        titles.addWidget(self.totals)
        row.addLayout(titles, 1)
        self.undo_button = qt.QToolButton()
        self.undo_button.setText('Undo')
        self.undo_button.setAccessibleName("Undo this response's AI changes")
        self.undo_button.setToolTip('Revert this response only where the saved patch still matches. Later conflicts are refused.')
        self.undo_button.clicked.connect(self.undo_requested)
        row.addWidget(self.undo_button)
        self.view_button = qt.QPushButton('View changes')
        self.view_button.clicked.connect(lambda: self.file_requested.emit(self.records[0]['path']) if self.records else None)
        row.addWidget(self.view_button)
        self.box.addLayout(row)
        separator = qt.QFrame()
        separator.setFrameShape(qt.QFrame.Shape.HLine)
        separator.setStyleSheet('background: palette(mid); border: none;')
        separator.setFixedHeight(1)
        self.box.addWidget(separator)
        self.actions_enabled = False
        self.files = qt.QListWidget()
        self.files.setAccessibleName('Files edited in this response')
        self.files.setHorizontalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.setTextElideMode(qt.Qt.TextElideMode.ElideMiddle)
        self.files.setSelectionMode(qt.QAbstractItemView.SelectionMode.NoSelection)
        self.files.setItemDelegate(FileDelegate(self.files))
        self.files.setFrameShape(qt.QFrame.Shape.NoFrame)
        self.files.setStyleSheet('QListWidget { background: transparent; border: none; }')
        self.files.setVerticalScrollBarPolicy(qt.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.files.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self.file_menu)
        self.files.itemClicked.connect(lambda item: self.file_requested.emit(item.data(qt.Qt.ItemDataRole.UserRole)))
        self.files.itemActivated.connect(lambda item: self.file_requested.emit(item.data(qt.Qt.ItemDataRole.UserRole)))
        self.box.addWidget(self.files)
        self.more_button = qt.QToolButton()
        self.more_button.setAutoRaise(True)
        self.more_button.clicked.connect(self.toggle_files)
        self.box.addWidget(self.more_button, 0, qt.Qt.AlignmentFlag.AlignLeft)
        self.expanded = False
        self.records = None
        self.hide()

    def update_changes(self, changes):
        if changes == self.records:
            return
        self.records = deepcopy(changes)
        self.header.setText(f'Edited {len(changes)} file{"s" if len(changes) != 1 else ""}')
        self.totals.setText(counts(changes))
        self.set_actions_enabled(self.actions_enabled)
        self.files.clear()
        for change in changes:
            state = ' · Undone' if change.get('undone') else ''
            item = qt.QListWidgetItem(f'{change["path"]}   +{change["added"]} −{change["removed"]}{state}')
            item.setData(qt.Qt.ItemDataRole.UserRole, change['path'])
            item.setData(qt.Qt.ItemDataRole.UserRole + 1, change)
            item.setToolTip(change['path'])
            self.files.addItem(item)
        self.fit_files()
        self.setVisible(bool(changes))

    def toggle_files(self):
        self.expanded = not self.expanded
        self.fit_files()

    def fit_files(self):
        count = len(self.records or [])
        for index in range(count):
            self.files.item(index).setHidden(not self.expanded and index >= 3)
        height = self.files.sizeHintForRow(0) if count else 34
        self.files.setFixedHeight(max(1, (count if self.expanded else min(3, count)) * height + 2))
        self.more_button.setVisible(count > 3)
        self.more_button.setText('Show fewer files ⌃' if self.expanded else f'Show {max(0, count - 3)} more files ⌄')

    def file_menu(self, position):
        item = self.files.itemAt(position)
        if item is None:
            return
        path = item.data(qt.Qt.ItemDataRole.UserRole)
        menu = qt.QMenu(self.files)
        menu.addAction('Edit in IDE', lambda: self.edit_requested.emit(path))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.files.viewport().mapToGlobal(position))

    def set_actions_enabled(self, enabled):
        self.actions_enabled = enabled
        pending = any(not item.get('undone', False) for item in self.records or [])
        self.undo_button.setText('Undo' if pending else 'Undone')
        self.undo_button.setEnabled(enabled and pending)


class ChangesPane(qt.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.box = qt.QVBoxLayout(self)
        self.box.setContentsMargins(8, 4, 4, 4)
        header = qt.QHBoxLayout()
        self.title = qt.QLabel('Changes for this response')
        self.title.setTextFormat(qt.Qt.TextFormat.PlainText)
        header.addWidget(self.title, 1)
        close = qt.QToolButton()
        close.setText('×')
        close.setToolTip('Close changes')
        close.setAccessibleName('Close changes')
        close.clicked.connect(self.hide)
        header.addWidget(close)
        self.box.addLayout(header)
        self.files = qt.QComboBox()
        self.files.setAccessibleName('Changed file for this response')
        self.files.currentIndexChanged.connect(self.show_file)
        self.box.addWidget(self.files)
        self.preview = None
        self.key = None
        self.records = []
        self.hide()

    def clear(self):
        self.key = None
        self.records = []
        self.files.clear()
        if self.preview is not None:
            self.preview.show_text('', '')
        self.hide()

    def show_changes(self, key, changes, path):
        if self.preview is None:
            from features.git.ui.preview import Preview
            self.preview = Preview(self)
            self.preview.search.setAccessibleName('Find in AI changes')
            self.preview.editor.setAccessibleName('AI changes for this response')
            self.preview.raw.setToolTip('Show the saved unified patch, including headers')
            self.box.addWidget(self.preview, 1)
        self.key, self.records = key, deepcopy(changes)
        self.title.setText('Changes · ' + summary(changes))
        self.files.blockSignals(True)
        self.files.clear()
        for item in changes:
            self.files.addItem(item['path'], item['path'])
        index = self.files.findData(path)
        self.files.setCurrentIndex(max(0, index))
        self.files.blockSignals(False)
        self.show_file(self.files.currentIndex())
        self.show()

    def show_file(self, index):
        if self.preview is None or not 0 <= index < len(self.records):
            return
        change = self.records[index]
        self.preview.show_diff(change['path'], change['patch'])
        self.preview.hide_file_actions()
        # These are saved snapshots, so toggling repository whitespace options
        # or staging/discarding hunks would be misleading.
        self.preview.ignore_whitespace.hide()
