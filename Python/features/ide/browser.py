"""Project tree wrapper around the shared lazy filesystem model."""
from pathlib import Path
import sys
from subprocess import SubprocessError
from commonUtils.ui import pyside as qt
from commonUtils.ui import desktop_actions
from commonUtils.ui.file_browser.model import BrowserFileSystemModel, ByteSortModel
from commonUtils.filesystem.transfers import validate_name


class ProjectFilter(ByteSortModel):
    def __init__(self, project, filesystem, parent):
        super().__init__(filesystem, parent)
        self.project = project
        self.browser = parent
        self.query = ''
        self.git_changes = {}
        self.unsaved_paths = set()

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == 0 and role in (
                qt.Qt.ItemDataRole.ForegroundRole, qt.Qt.ItemDataRole.ToolTipRole):
            path = Path(self.sourceModel().filePath(self.mapToSource(index)))
            status = self.git_changes.get(path)
            if path in self.unsaved_paths:
                status = (status[0], status[1] + '; unsaved changes') if status else ('modify', 'Unsaved changes')
            if status:
                if role == qt.Qt.ItemDataRole.ForegroundRole:
                    from .git_status import COLORS
                    return qt.QBrush(qt.QColor(COLORS[status[0]]))
                return str(path) + '\n' + ('Git: ' if path in self.git_changes else '') + status[1]
        return super().data(index, role)

    def flags(self, index):
        flags = super().flags(index)
        if index.isValid() and index.column() == 0:
            path = Path(self.sourceModel().filePath(self.mapToSource(index)))
            if path != self.project.root and path.is_relative_to(self.project.root) and not self.browser.rename_blocked(path):
                return flags | qt.Qt.ItemFlag.ItemIsEditable
        return flags & ~qt.Qt.ItemFlag.ItemIsEditable

    def setData(self, index, value, role=qt.Qt.ItemDataRole.EditRole):
        if role != qt.Qt.ItemDataRole.EditRole:
            return super().setData(index, value, role)
        browser = self.browser
        path = browser.path(index)
        if path == self.project.root or not path.is_relative_to(self.project.root) or browser.rename_blocked(path):
            browser.rename_error(path)
            return False
        source = self.mapToSource(index)
        try:
            target = path.with_name(value)
        except ValueError:
            target = None  # The shared filename validator supplies the error.
        occupied = set(getattr(browser.workspace, 'documents', {})) | set(getattr(browser.workspace, 'pending_opens', {}))
        if target is not None and target != path and any(p.is_relative_to(target) and not p.is_relative_to(path) for p in occupied):
            browser.workspace.error('The new name is already open in the IDE. Close that file first.')
            return False
        browser.model.setReadOnly(False)
        try:
            renamed = browser.model.setData(source, value, role)
        finally:
            browser.model.setReadOnly(True)
        return renamed

    def filterAcceptsRow(self, row, parent):
        index = self.sourceModel().index(row, 0, parent)
        path = Path(self.sourceModel().filePath(index))
        try:
            relative = path.relative_to(self.project.root)
        except ValueError:
            return True
        if path == self.project.root:
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
        layout.setContentsMargins(0, 0, 2, 0)
        layout.setSpacing(2)
        self.filter = qt.QLineEdit()
        self.filter.setPlaceholderText('Filter visible filenames…')
        layout.addWidget(self.filter)
        self.model = BrowserFileSystemModel(self)
        self.model.setReadOnly(True)
        self.proxy = ProjectFilter(project, self.model, self)
        self.proxy.sort(0, qt.Qt.SortOrder.AscendingOrder)
        self.tree = qt.QTreeView()
        from commonUtils.ui.appearance.styling import bind_font
        bind_font(self.tree, 'browser')
        self.tree.setModel(self.proxy)
        from commonUtils.ui.file_browser.editing import FilenameDelegate
        self.tree.setItemDelegate(FilenameDelegate(self.tree))
        self.tree.setEditTriggers(qt.QAbstractItemView.EditTrigger.SelectedClicked
                                  | qt.QAbstractItemView.EditTrigger.EditKeyPressed)
        self.rename_keys = []
        for key in (('F2', 'Return') if sys.platform == 'darwin' else ('F2',)):
            shortcut = qt.QShortcut(qt.QKeySequence(key), self.tree)
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda: self.rename(self.path()))
            self.rename_keys.append(shortcut)
        self.model.edit_failed.connect(getattr(workspace, 'error', lambda message: None))
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.menu)
        self.tree.doubleClicked.connect(self.activate)
        self.expanded_paths = set()
        self.pending_expansion = set()
        self.pending_selection = None
        self.model.fileRenamed.connect(self.renamed)
        self.tree.selectionModel().currentChanged.connect(self.selection_changed)
        self.tree.expanded.connect(self.expanded)
        self.tree.collapsed.connect(self.collapsed)
        self.model.directoryLoaded.connect(self.restore_expansion)
        layout.addWidget(self.tree)
        self.filter.textChanged.connect(self.filter_changed)
        self.reset_root()
        from .git_status import ProjectGitStatus
        self.git_status = ProjectGitStatus(self)

    def reset_root(self):
        self.model.setRootPath(str(self.project.root))
        self.proxy.invalidateFilter()
        self.tree.setRootIndex(self.proxy.mapFromSource(self.model.index(str(self.project.root))))
        self.tree.setEnabled(self.project.root.is_dir())
        if hasattr(self, 'git_status'):
            self.git_status.refresh()

    def refresh_unsaved(self):
        documents = getattr(self.workspace, 'documents', {})
        self.proxy.unsaved_paths = {path for path, doc in documents.items() if doc.document().isModified()}
        self.tree.viewport().update()

    def renamed(self, directory, old_name, new_name):
        old, new = Path(directory) / old_name, Path(directory) / new_name
        retarget = getattr(self.workspace, 'retarget_documents', None)
        if callable(retarget):
            retarget(old, new)
        def updated(value):
            path = Path(value)
            return str(new / path.relative_to(old)) if path.is_relative_to(old) else value
        self.expanded_paths = {updated(path) for path in self.expanded_paths}
        self.pending_expansion = {updated(path) for path in self.pending_expansion}
        if self.pending_selection:
            self.pending_selection = updated(self.pending_selection)
        self.git_status.refresh()
        self.changed.emit()

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
                              ('Rename', lambda: self.rename(path)), ('Delete…', lambda: self.delete(path)),
                              (desktop_actions.reveal_label(), lambda: self.reveal(path)),
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
        paths = set(getattr(self.workspace, 'documents', {})) | set(getattr(self.workspace, 'pending_opens', {}))
        resolved = path.resolve()
        return [p for p in paths if p == resolved or resolved in p.parents]

    def reveal(self, path):
        try:
            desktop_actions.reveal(path)
        except (OSError, RuntimeError, SubprocessError) as error:
            self.workspace.error(error)

    def rename(self, path):
        if path == self.project.root:
            return
        if self.rename_blocked(path):
            self.rename_error(path)
            return
        def edit():
            if self.rename_blocked(path):
                self.rename_error(path)
                return
            if not (path.exists() or path.is_symlink()):
                return
            self.locate(path)
            self.tree.setFocus()
            self.tree.edit(self.tree.currentIndex())
        qt.QTimer.singleShot(0, self, edit)

    def rename_error(self, path):
        self.workspace.error(self.rename_block_reason(path) or 'The project root cannot be renamed here.')

    def rename_blocked(self, path):
        return bool(self.rename_block_reason(path))

    def rename_block_reason(self, path):
        affected = self.affected(path)
        pending = getattr(self.workspace, 'pending_opens', {})
        documents = getattr(self.workspace, 'documents', {})
        if any(p in pending for p in affected):
            return 'Wait for affected files to finish opening, then retry rename.'
        if any(p in documents and getattr(getattr(documents[p].buffer, 'autosave', None), 'busy', False) for p in affected):
            return 'Wait for affected autosaves to finish, then retry rename.'
        page = getattr(self.workspace, 'host_page', None)
        for other in getattr(page, 'views', ()):
            if other is self.workspace:
                continue
            if other.project.root.is_relative_to(path) or any(p.is_relative_to(path) for p in set(other.documents) | set(other.pending_opens)):
                return 'Close the affected files or project in the other IDE project before renaming.'
        return ''

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
            # The confirmation dialog runs an event loop: a queued open may have
            # completed while it was displayed.
            if self.affected(path):
                self.workspace.error('Close the affected files before deleting this file or folder.')
                return
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
        self.pending_expansion.discard(str(self.path(index)))
        self.changed.emit()

    def selection_changed(self, current, previous):
        if current.isValid():
            self.pending_selection = None
        self.changed.emit()

    def restore_expansion(self, *args):
        for path in list(self.pending_expansion):
            index = self.proxy.mapFromSource(self.model.index(path))
            if index.isValid():
                self.tree.expand(index)
                self.pending_expansion.discard(path)
        if self.pending_selection:
            index = self.proxy.mapFromSource(self.model.index(self.pending_selection))
            if index.isValid():
                self.tree.setCurrentIndex(index)
                self.pending_selection = None

    def state(self):
        return {'expanded': sorted(self.expanded_paths | self.pending_expansion), 'filter': self.filter.text(),
                'selected': self.pending_selection or str(self.path())}

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
            self.pending_selection = selected
            self.restore_expansion()
