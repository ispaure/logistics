"""Project tree wrapper around the shared lazy filesystem model."""
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser.model import BrowserFileSystemModel
from commonUtils.filesystem.transfers import validate_name


class ProjectFilter(qt.QSortFilterProxyModel):
    def __init__(self, project, parent):
        super().__init__(parent)
        self.project = project
        self.query = ''

    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        path = Path(self.sourceModel().filePath(index))
        try:
            relative = path.relative_to(self.project.root)
        except ValueError:
            return True
        if any(part in self.project.excluded_paths for part in relative.parts) or relative.as_posix() in self.project.excluded_paths:
            return False
        return self.sourceModel().isDir(index) or self.query.casefold() in path.name.casefold()


class ProjectBrowser(qt.QWidget):
    opened = qt.Signal(object)
    changed = qt.Signal()

    def __init__(self, project, workspace):
        super().__init__(workspace)
        self.project, self.workspace = project, workspace
        layout = qt.QVBoxLayout(self)
        self.filter = qt.QLineEdit()
        self.filter.setPlaceholderText('Filter visible filenames…')
        layout.addWidget(self.filter)
        self.model = BrowserFileSystemModel(self)
        self.model.setReadOnly(True)
        self.proxy = ProjectFilter(project, self)
        self.proxy.setSourceModel(self.model)
        self.tree = qt.QTreeView()
        self.tree.setModel(self.proxy)
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.menu)
        self.tree.doubleClicked.connect(self.activate)
        self.expanded_paths = set()
        self.pending_expansion = set()
        self.tree.expanded.connect(self.expanded)
        self.tree.collapsed.connect(self.collapsed)
        self.model.directoryLoaded.connect(self.restore_expansion)
        layout.addWidget(self.tree)
        self.filter.textChanged.connect(self.filter_changed)
        self.reset_root()

    def reset_root(self):
        self.model.setRootPath(str(self.project.root))
        self.proxy.invalidateFilter()
        self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(str(self.project.root))))
        self.tree.setEnabled(self.project.root.is_dir())

    def filter_changed(self, value):
        self.proxy.query = value
        self.proxy.invalidateFilter()
        self.changed.emit()

    def path(self, index=None):
        index = index if index is not None else self.tree.currentIndex()
        return Path(self.model.filePath(self.proxy.mapToSource(index))) if index.isValid() else self.project.root

    def activate(self, index):
        path = self.path(index)
        if path.is_file():
            self.opened.emit(path)

    def locate(self, path):
        self.filter.clear()
        index = self.proxy.mapFromSource(self.model.index(str(path)))
        parent = index.parent()
        while parent.isValid():
            self.tree.expand(parent)
            parent = parent.parent()
        self.tree.setCurrentIndex(index)
        self.tree.scrollTo(index)

    def menu(self, position):
        path = self.path(self.tree.indexAt(position))
        menu = qt.QMenu(self)
        for label, action in [('New file…', lambda: self.create(path, False)), ('New folder…', lambda: self.create(path, True)),
                              ('Rename…', lambda: self.rename(path)), ('Delete…', lambda: self.delete(path)),
                              ('Reveal in file manager', lambda: qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))),
                              ('Refresh', self.reset_root)]:
            menu.addAction(label).triggered.connect(action)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def create(self, path, folder):
        name, ok = qt.QInputDialog.getText(self, 'Create folder' if folder else 'Create file', 'Name')
        if not ok:
            return
        try:
            validate_name(name)
            target = (path if path.is_dir() else path.parent) / name
            if folder:
                target.mkdir()
            else:
                with target.open('xb'):
                    pass
                self.opened.emit(target)
        except (OSError, ValueError) as error:
            self.workspace.error(error)

    def affected(self, path):
        return [doc for doc in self.workspace.documents.values() if doc.path == path.resolve() or path.resolve() in doc.path.parents]

    def rename(self, path):
        if path == self.project.root:
            return
        if self.affected(path):
            self.workspace.error('Close the affected files before renaming this file or folder.')
            return
        name, ok = qt.QInputDialog.getText(self, 'Rename', 'New name', text=path.name)
        if ok:
            self.model.setReadOnly(False)
            try:
                if not self.model.setData(self.model.index(str(path)), name):
                    self.workspace.error('Rename failed; check the name and destination.')
            finally:
                self.model.setReadOnly(True)

    def delete(self, path):
        if path == self.project.root:
            return
        if self.affected(path):
            self.workspace.error('Close the affected files before deleting this file or folder.')
            return
        if qt.QMessageBox.question(self, 'Delete permanently?', f'{path}\nOnly files and empty folders can be deleted here.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
            return
        try:
            if path.is_dir() and not path.is_symlink():
                path.rmdir()
            else:
                path.unlink()
        except OSError as error:
            self.workspace.error(error)

    def expanded(self, index):
        self.expanded_paths.add(str(self.path(index)))
        self.changed.emit()

    def collapsed(self, index):
        self.expanded_paths.discard(str(self.path(index)))
        self.changed.emit()

    def restore_expansion(self, *args):
        for path in list(self.pending_expansion):
            index = self.proxy.mapFromSource(self.model.index(path))
            if index.isValid():
                self.tree.expand(index)
                self.pending_expansion.discard(path)

    def state(self):
        return {'expanded': sorted(self.expanded_paths), 'filter': self.filter.text(),
                'selected': str(self.path())}

    def restore(self, state):
        if not isinstance(state, dict):
            return
        self.filter.setText(state.get('filter', '') if isinstance(state.get('filter', ''), str) else '')
        expanded = state.get('expanded', [])
        if isinstance(expanded, list):
            self.pending_expansion = {p for p in expanded[:1000] if isinstance(p, str)}
            self.restore_expansion()
        selected = state.get('selected')
        if isinstance(selected, str):
            self.tree.setCurrentIndex(self.proxy.mapFromSource(self.model.index(selected)))
