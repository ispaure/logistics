"""Edit a project's source folders and exclusions against its directory tree."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.colors import readable_accent
from features.ide.projects import ProjectFolderRoles, is_excluded


COLORS = {'Source': '#2878df', 'Excluded': '#cf681d', 'Missing': '#d82741'}
ITEM_ROLE = qt.Qt.ItemDataRole.UserRole


def path_color(status, palette):
    foreground = palette.color(qt.QPalette.ColorRole.Text).rgba()
    background = palette.color(qt.QPalette.ColorRole.Base).rgba()
    accent = qt.QColor(COLORS[status]).rgba()
    return qt.QBrush(qt.QColor.fromRgba(readable_accent(accent, foreground, background) & 0xffffffff))


class StructureModel(qt.QFileSystemModel):
    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self.setReadOnly(True)
        self.setResolveSymlinks(False)
        self.setFilter(qt.QDir.Filter.Dirs | qt.QDir.Filter.NoDotAndDotDot |
                       qt.QDir.Filter.Hidden | qt.QDir.Filter.NoSymLinks)

    def multiData(self, index, roles):
        for position in range(roles.size()):
            role = roles[position]
            role.setData(self.data(index, role.role()))

    def data(self, index, role=qt.Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (qt.Qt.ItemDataRole.ForegroundRole, qt.Qt.ItemDataRole.ToolTipRole):
            path = Path(self.filePath(index))
            status = self.panel.status_for(path)
            if status and role == qt.Qt.ItemDataRole.ForegroundRole:
                return path_color(status, self.panel.tree.palette())
            if role == qt.Qt.ItemDataRole.ToolTipRole:
                return f'{path}\n{status}' if status else str(path)
        return super().data(index, role)


class PathList(qt.QGroupBox):
    changed = qt.Signal()

    def __init__(self, title, status, values, panel):
        super().__init__(title, panel)
        self.panel = panel
        self.status = status
        self.values = list(values)
        layout = qt.QVBoxLayout(self)
        self.list = qt.QListWidget()
        self.list.setAccessibleName(title)
        self.list.setUniformItemSizes(True)
        layout.addWidget(self.list)
        controls = qt.QHBoxLayout()
        add = qt.QPushButton('Add Path…')
        add.setAutoDefault(False)
        add.clicked.connect(lambda: self.edit_path())
        controls.addWidget(add)
        self.remove = qt.QPushButton('Remove')
        self.remove.setAutoDefault(False)
        self.remove.setEnabled(False)
        self.remove.clicked.connect(self.remove_path)
        controls.addWidget(self.remove)
        controls.addStretch()
        layout.addLayout(controls)
        self.list.currentItemChanged.connect(lambda current, _: self.remove.setEnabled(current is not None))
        self.list.itemDoubleClicked.connect(lambda item: self.edit_path(item.data(ITEM_ROLE)))

    def refresh(self):
        row = self.list.currentRow()
        self.list.clear()
        for number, value in enumerate(self.values):
            status = self.status
            if not self.panel.root:
                description = 'Project root unavailable'
            elif self.status == 'Excluded' and '/' not in value:
                description = 'Name rule · matches anywhere in the project'
            elif self.path_exists(value):
                description = status
            else:
                status = 'Missing'
                description = 'Path unavailable'
            label = value or '(empty path)'
            if status == 'Missing':
                label += ' (unavailable)'
            item = qt.QListWidgetItem(label)
            item.setData(ITEM_ROLE, number)
            item.setToolTip(f'{value}\n{description}')
            item.setForeground(path_color(status, self.list.palette()))
            self.list.addItem(item)
        self.list.setCurrentRow(min(row, self.list.count() - 1))

    def path_exists(self, value):
        try:
            path = self.panel.root / Path(value).expanduser()
            return path.is_dir() if self.status == 'Source' else path.exists()
        except (OSError, RuntimeError, ValueError):
            return False

    def edit_path(self, row=None):
        if self.status == 'Source':
            prompt = 'Project-relative or absolute folder path'
        else:
            prompt = 'Name anywhere in the project, or a project-relative path using /'
        value, accepted = qt.QInputDialog.getText(self, self.title(), prompt,
                                                   text=self.values[row] if row is not None else '')
        if not accepted or not value.strip():
            return
        value = value.strip()
        if self.status == 'Excluded':
            value = Path(value).as_posix()
            if value == '.' or Path(value).is_absolute() or '..' in Path(value).parts:
                qt.QMessageBox.warning(self, self.title(), 'Enter a name or a path inside the project root.')
                return
        if value in self.values:
            return
        if row is None:
            self.values.append(value)
        else:
            self.values[row] = value
        self.changed.emit()

    def remove_path(self):
        item = self.list.currentItem()
        if item is not None:
            self.values.pop(item.data(ITEM_ROLE))
            self.changed.emit()


class ProjectStructure(qt.QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.root = None
        self.folder_roles = ProjectFolderRoles(None, (), (), ())
        layout = qt.QVBoxLayout(self)
        root_row = qt.QHBoxLayout()
        root_label = qt.QLabel('Project root')
        self.root_path = qt.QLineEdit(str(project.root))
        root_label.setBuddy(self.root_path)
        self.root_path.setAccessibleName('Project root')
        root_row.addWidget(root_label)
        root_row.addWidget(self.root_path, 1)
        browse = qt.QPushButton('Browse…')
        browse.setAutoDefault(False)
        browse.clicked.connect(self.choose_root)
        root_row.addWidget(browse)
        layout.addLayout(root_row)

        splitter = qt.QSplitter(qt.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)

        folders = qt.QWidget()
        folder_layout = qt.QVBoxLayout(folders)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        actions = qt.QHBoxLayout()
        self.mark_source = qt.QPushButton('Mark as Source')
        self.mark_excluded = qt.QPushButton('Mark as Excluded')
        self.mark_source.clicked.connect(lambda: self.mark('Source'))
        self.mark_excluded.clicked.connect(lambda: self.mark('Excluded'))
        for button in (self.mark_source, self.mark_excluded):
            button.setAutoDefault(False)
            actions.addWidget(button)
        actions.addStretch()
        folder_layout.addLayout(actions)
        self.tree = qt.QTreeView()
        self.tree.setAccessibleName('Project folders')
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.model = StructureModel(self)
        self.tree.setModel(self.model)
        for column in (1, 2, 3):
            self.tree.hideColumn(column)
        folder_layout.addWidget(self.tree, 1)
        self.root_status = qt.QLabel()
        folder_layout.addWidget(self.root_status)
        pattern_row = qt.QHBoxLayout()
        pattern_label = qt.QLabel('Exclude files')
        self.pattern_field = qt.QLineEdit('; '.join(project.excluded_patterns))
        self.pattern_field.setAccessibleName('Exclude files')
        self.pattern_field.setPlaceholderText('*.xcarchive; *.dSYM')
        pattern_label.setBuddy(self.pattern_field)
        pattern_row.addWidget(pattern_label)
        pattern_row.addWidget(self.pattern_field, 1)
        folder_layout.addLayout(pattern_row)
        pattern_help = qt.QLabel('Separate patterns with semicolons. * matches any number of characters and ? matches one.')
        pattern_help.setWordWrap(True)
        folder_layout.addWidget(pattern_help)
        splitter.addWidget(folders)

        lists = qt.QWidget()
        lists_layout = qt.QVBoxLayout(lists)
        lists_layout.setContentsMargins(0, 0, 0, 0)
        self.sources = PathList('Source Folders', 'Source', project.source_paths, self)
        self.exclusions = PathList('Excluded Paths', 'Excluded', project.excluded_paths, self)
        for path_list in (self.sources, self.exclusions):
            lists_layout.addWidget(path_list, 1)
            path_list.changed.connect(self.refresh)
        splitter.addWidget(lists)
        splitter.setSizes([510, 330])
        self.tree.selectionModel().currentChanged.connect(self.update_buttons)
        self.root_path.editingFinished.connect(self.update_root)
        self.pattern_field.textChanged.connect(self.update_patterns)
        self.update_patterns(self.pattern_field.text())
        self.update_root()

    def update_patterns(self, text):
        self.patterns = list(dict.fromkeys(part.strip() for part in text.split(';') if part.strip()))
        self.refresh_roles()

    def resolved_root(self):
        value = self.root_path.text().strip()
        if not value:
            return None
        try:
            return Path(value).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            return None

    def choose_root(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Choose Project Root', self.root_path.text())
        if path:
            self.root_path.setText(path)
            self.update_root()

    def update_root(self):
        self.root = self.resolved_root()
        available = self.root is not None and self.root.is_dir()
        if available:
            index = self.model.setRootPath(str(self.root))
            self.tree.setRootIndex(index)
            if self.relative_selection() is None:
                self.tree.clearSelection()
                self.tree.setCurrentIndex(qt.QModelIndex())
        self.tree.setVisible(available)
        self.root_status.setText('Project root is unavailable.' if not available else '')
        self.root_status.setVisible(not available)
        self.refresh()

    def status_for(self, path):
        return self.folder_roles.status(path)

    def relative_selection(self):
        index = self.tree.currentIndex()
        if self.root and index.isValid():
            path = Path(self.model.filePath(index))
            if path != self.root and path.is_relative_to(self.root):
                return path.relative_to(self.root)
        return None

    def update_buttons(self, *args):
        relative = self.relative_selection()
        if relative is None:
            self.mark_source.setEnabled(False)
            self.mark_excluded.setEnabled(False)
            return
        direct = relative.as_posix()
        remaining = [rule for rule in self.exclusions.values if rule != direct]
        self.mark_source.setEnabled(not is_excluded(relative, remaining, self.patterns)
                                    and (direct in self.exclusions.values
                                         or self.root / relative not in self.folder_roles.sources))
        self.mark_excluded.setEnabled(not is_excluded(relative, self.exclusions.values, self.patterns))

    def mark(self, status):
        relative = self.relative_selection()
        if relative is None:
            return
        value = relative.as_posix()
        path = self.root / relative
        if status == 'Source' and self.mark_source.isEnabled():
            self.exclusions.values = [rule for rule in self.exclusions.values if rule != value]
            if path not in self.folder_roles.sources:
                self.sources.values.append(value)
        elif status == 'Excluded' and self.mark_excluded.isEnabled():
            self.sources.values = [entry for entry in self.sources.values if self.folder_roles.source_folder(entry) != path]
            self.exclusions.values.append(value)
        self.refresh()

    def refresh(self):
        self.sources.refresh()
        self.exclusions.refresh()
        self.refresh_roles()

    def refresh_roles(self):
        self.folder_roles = ProjectFolderRoles(self.root, self.sources.values, self.exclusions.values, self.patterns)
        self.tree.viewport().update()
        self.update_buttons()
