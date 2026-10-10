"""Index/worktree separation, selection-driven staging, and a commit draft."""
from commonUtils.ui import pyside as qt
from .chrome import status_icon


class FileList(qt.QTreeWidget):
    """Checkbox presses stage directly without starting a competing preview read."""
    def mousePressEvent(self, event):
        item=self.itemAt(event.position().toPoint())
        if item and event.button() == qt.Qt.MouseButton.LeftButton:
            indicator=self.style().pixelMetric(qt.QStyle.PixelMetric.PM_IndicatorWidth)
            if event.position().x() < self.visualItemRect(item).left()+indicator+10:
                with qt.QSignalBlocker(self): self.setCurrentItem(item)
                item.setCheckState(0,qt.Qt.CheckState.Unchecked if item.checkState(0) == qt.Qt.CheckState.Checked else qt.Qt.CheckState.Checked)
                event.accept()
                return
        super().mousePressEvent(event)


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
        layout.setSpacing(0)
        self.filter = qt.QLineEdit()
        self.filter.setPlaceholderText('Filter pending files by path')
        self.filter.textChanged.connect(self._filter)
        layout.addWidget(self.filter)
        self.file_split = qt.QSplitter(qt.Qt.Orientation.Vertical)
        self.staged_files = self._file_list('Staged files', True)
        self.unstaged_files = self._file_list('Unstaged files', False)
        self.files = self.unstaged_files
        self.file_split.setSizes([320, 320])
        layout.addWidget(self.file_split, 1)
        self.composer = qt.QWidget()
        composer_layout = qt.QVBoxLayout(self.composer)
        composer_layout.setContentsMargins(6, 4, 6, 4)
        composer_layout.setSpacing(4)
        self.message = qt.QPlainTextEdit()
        self.message.setPlaceholderText('Commit message\n\nOptional description')
        self.message.setAccessibleName('Commit message')
        self.message.setMaximumHeight(56)
        composer_layout.addWidget(self.message)
        row = qt.QHBoxLayout()
        self.amend = qt.QCheckBox('Amend last commit')
        self.commit_button = qt.QPushButton('Commit staged changes')
        self.commit_button.clicked.connect(lambda: self.commit_requested.emit(self.message.toPlainText(), self.amend.isChecked()))
        row.addWidget(self.amend)
        row.addStretch()
        row.addWidget(self.commit_button)
        composer_layout.addLayout(row)
        self.changes = []

    def _file_list(self, title, staged):
        host = qt.QWidget()
        layout = qt.QVBoxLayout(host)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        header = qt.QWidget()
        row = qt.QHBoxLayout(header)
        row.setContentsMargins(6,2,6,2)
        label = qt.QLabel(title); label.setObjectName('fileSection')
        row.addWidget(label,1)
        button = qt.QToolButton(); button.setText('Unstage all' if staged else 'Stage all')
        button.clicked.connect(self.unstage_all if staged else self.stage_all)
        row.addWidget(button); layout.addWidget(header)
        tree = FileList()
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(False)
        tree.setUniformRowHeights(True)
        tree.setIconSize(qt.QSize(16, 16))
        tree.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setAccessibleName(title)
        tree.currentItemChanged.connect(lambda item, previous: self._selected(tree,item))
        tree.itemChanged.connect(self._checked)
        tree.itemDoubleClicked.connect(self._edit)
        tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda point: self._menu(tree,point))
        layout.addWidget(tree,1)
        self.file_split.addWidget(host)
        return tree

    def set_changes(self, changes):
        key = None
        for tree in (self.staged_files,self.unstaged_files):
            current=tree.currentItem()
            if current:
                data=current.data(0,qt.Qt.ItemDataRole.UserRole)
                if data: key=(data[0].path,data[1])
        self.changes = changes
        for tree, staged in ((self.staged_files,True),(self.unstaged_files,False)):
            with qt.QSignalBlocker(tree):
                tree.clear()
                for change in sorted(changes,key=lambda c: c.path.casefold()):
                    if not (change.staged if staged else change.unstaged): continue
                    status='!' if change.conflict else '?' if change.index == '?' else (change.index if staged else change.worktree)
                    display=f'{change.original_path} → {change.path}' if change.original_path else change.path
                    item=qt.QTreeWidgetItem([display])
                    item.setIcon(0, status_icon(status))
                    item.setData(0,qt.Qt.ItemDataRole.UserRole,(change,staged))
                    item.setToolTip(0,display + f' · Status: {status}' + (' · submodule' if change.submodule != 'N...' else ''))
                    item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0,qt.Qt.CheckState.Checked if staged else qt.Qt.CheckState.Unchecked)
                    tree.addTopLevelItem(item)
                    if (change.path,staged) == key: tree.setCurrentItem(item)
        self._filter(self.filter.text())

    def _filter(self, text):
        for tree in (self.staged_files,self.unstaged_files):
            for i in range(tree.topLevelItemCount()):
                item=tree.topLevelItem(i)
                item.setHidden(text.casefold() not in item.text(0).casefold())

    def _selected(self, tree, item):
        data=item.data(0,qt.Qt.ItemDataRole.UserRole) if item else None
        if data:
            other=self.unstaged_files if tree is self.staged_files else self.staged_files
            with qt.QSignalBlocker(other): other.clearSelection(); other.setCurrentItem(None)
            self.change_selected.emit(*data)

    def _checked(self, item, column):
        data=item.data(0,qt.Qt.ItemDataRole.UserRole)
        if data:
            change,staged=data
            checked=item.checkState(0) == qt.Qt.CheckState.Checked
            if checked != staged:
                (self.unstage_requested if staged else self.stage_requested).emit(self.paths([change]))

    def _edit(self, item, column=0):
        data=item.data(0,qt.Qt.ItemDataRole.UserRole) if item else None
        if data: self.edit_requested.emit(data[0].path)

    def _menu(self, tree, point):
        item=tree.itemAt(point)
        if item:
            tree.setCurrentItem(item)
            staged=item.data(0,qt.Qt.ItemDataRole.UserRole)[1]
            menu=qt.QMenu(self)
            menu.addAction('Unstage file' if staged else 'Stage file',self.unstage_selected if staged else self.stage_selected)
            if not staged: menu.addAction('Discard file edits…',self.discard_selected)
            menu.addAction('Open working file in Text Editor',lambda: self._edit(item))
            menu.exec(tree.viewport().mapToGlobal(point))

    @staticmethod
    def paths(changes):
        return list(dict.fromkeys(path for change in changes for path in (change.path, change.original_path) if path is not None))

    def selected(self, staged=None):
        values = [item.data(0, qt.Qt.ItemDataRole.UserRole) for tree in (self.staged_files,self.unstaged_files) for item in tree.selectedItems()]
        return [change for change, side in filter(None, values) if staged is None or side == staged]

    def stage_selected(self): self.stage_requested.emit(self.paths(self.selected(False)))
    def unstage_selected(self): self.unstage_requested.emit(self.paths(self.selected(True)))
    def unstage_all(self): self.unstage_requested.emit(self.paths([c for c in self.changes if c.staged]))
    def stage_all(self): self.stage_requested.emit(self.paths([c for c in self.changes if c.unstaged]))
    def discard_selected(self): self.discard_requested.emit(self.selected(False))
