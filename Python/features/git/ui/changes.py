"""Index/worktree separation, selection-driven staging, and a commit draft."""
from commonUtils.ui import pyside as qt


class ChangesPanel(qt.QWidget):
    change_selected = qt.Signal(object, bool)
    stage_requested = qt.Signal(object)
    unstage_requested = qt.Signal(object)
    discard_requested = qt.Signal(object)
    commit_requested = qt.Signal(str, bool)
    edit_requested = qt.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = qt.QHBoxLayout()
        for text, callback in (('Stage', self.stage_selected), ('Unstage', self.unstage_selected),
                               ('Stage all', self.stage_all), ('Discard…', self.discard_selected)):
            button = qt.QPushButton(text)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.files = qt.QTreeWidget()
        self.files.setHeaderLabels(['Changed files', 'Status'])
        self.files.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setAccessibleName('Working tree and staged changes')
        self.files.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.files.header().setStretchLastSection(False)
        self.files.header().setSectionResizeMode(1, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.files.currentItemChanged.connect(self._selected)
        self.files.itemDoubleClicked.connect(self._edit)
        self.files.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.files, 1)
        self.message = qt.QPlainTextEdit()
        self.message.setPlaceholderText('Commit subject\n\nOptional description')
        self.message.setAccessibleName('Commit message')
        self.message.setMaximumHeight(150)
        layout.addWidget(self.message)
        row = qt.QHBoxLayout()
        self.amend = qt.QCheckBox('Amend last commit')
        self.commit_button = qt.QPushButton('Commit staged changes')
        self.commit_button.clicked.connect(lambda: self.commit_requested.emit(self.message.toPlainText(), self.amend.isChecked()))
        row.addWidget(self.amend)
        row.addStretch()
        row.addWidget(self.commit_button)
        layout.addLayout(row)
        self.changes = []

    def set_changes(self, changes):
        current = self.files.currentItem()
        selected = current.data(0, qt.Qt.ItemDataRole.UserRole) if current else None
        key = (selected[0].path, selected[1]) if selected else None
        self.changes = changes
        with qt.QSignalBlocker(self.files):
            self.files.clear()
            for title, predicate, staged in (
                    ('Conflicts', lambda c: c.conflict, False),
                    ('Unstaged', lambda c: c.unstaged and not c.conflict, False),
                    ('Staged', lambda c: c.staged, True)):
                entries = [c for c in changes if predicate(c)]
                section = qt.QTreeWidgetItem([f'{title} ({len(entries)})', ''])
                section.setFlags(section.flags() & ~qt.Qt.ItemFlag.ItemIsSelectable)
                self.files.addTopLevelItem(section)
                for change in entries:
                    display = f'{change.original_path} → {change.path}' if change.original_path else change.path
                    status = 'conflict' if change.conflict else 'untracked' if change.index == '?' else (
                        change.index if staged else change.worktree)
                    if change.submodule != 'N...': status += ' · submodule'
                    item = qt.QTreeWidgetItem([display, status])
                    item.setData(0, qt.Qt.ItemDataRole.UserRole, (change, staged))
                    item.setToolTip(0, display)
                    section.addChild(item)
                    if (change.path, staged) == key: self.files.setCurrentItem(item)
                section.setExpanded(True)

    def _selected(self, item, previous):
        data = item.data(0, qt.Qt.ItemDataRole.UserRole) if item else None
        if data: self.change_selected.emit(*data)

    def _edit(self, item, column=0):
        data = item.data(0, qt.Qt.ItemDataRole.UserRole) if item else None
        if data: self.edit_requested.emit(data[0].path)

    def _menu(self, point):
        item = self.files.itemAt(point)
        if item and item.data(0, qt.Qt.ItemDataRole.UserRole):
            menu = qt.QMenu(self)
            menu.addAction('Open working file in Text Editor', lambda: self._edit(item))
            menu.exec(self.files.viewport().mapToGlobal(point))

    @staticmethod
    def paths(changes):
        return list(dict.fromkeys(path for change in changes for path in (change.path, change.original_path) if path is not None))

    def selected(self, staged=None):
        values = [item.data(0, qt.Qt.ItemDataRole.UserRole) for item in self.files.selectedItems()]
        return [change for change, side in filter(None, values) if staged is None or side == staged]

    def stage_selected(self): self.stage_requested.emit(self.paths(self.selected(False)))
    def unstage_selected(self): self.unstage_requested.emit(self.paths(self.selected(True)))
    def stage_all(self): self.stage_requested.emit(self.paths([c for c in self.changes if c.unstaged]))
    def discard_selected(self): self.discard_requested.emit(self.selected(False))
