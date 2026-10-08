"""Browsable rename previews; all scanning/planning/disk work uses a shared worker."""
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import json
import re
import stat
from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.ui.file_browser.controls import navigation_button
from commonUtils.filesystem import format_size
from commonUtils.renameUtils import RenameRules, plan_renames, apply_renames, undo_renames
from commonUtils.traversal import natural_path_key, scan_directory
from .rules import RenameRuleControls


class _FolderIconProvider(qt.QFileIconProvider):
    """Avoid MIME/content inspection of unrelated files in ancestor folders."""

    def type(self, info):
        return 'Folder' if info.isDir() else 'File'

    def icon(self, value):
        if isinstance(value, qt.QFileInfo):
            value = self.IconType.Folder if value.isDir() else self.IconType.File
        return super().icon(value)


class BulkRenameWidget(qt.QWidget):
    """Embed a folder browser or supply explicit paths. Only selected rows are renamed."""
    renamed = qt.Signal(object)
    preview_ready = qt.Signal(object)
    idle = qt.Signal()

    def __init__(self, directory=None, parent=None, *, paths=()):
        super().__init__(parent)
        paths = tuple(Path(path).absolute() for path in paths)
        self.directory = Path(directory or (paths[0].parent if paths else Path.home())).absolute()
        self.plan = None
        self.receipt = None
        self._state = ''
        self._generation = 0
        self._plan_generation = -1
        self._pending_preview = False
        self._items = {}
        self._closing = False
        self._folder_reveal_pending = None
        self._loaded_tree_directories = set()
        self._tree_anchor = self.directory.anchor
        layout = qt.QVBoxLayout(self)
        self.path_edit = qt.QLineEdit(str(self.directory))
        self.path_edit.setAccessibleName('Bulk rename folder')
        self.path_edit.returnPressed.connect(lambda: self.load_directory(self.path_edit.text()))
        self.browse_button = qt.QPushButton('Browse…')
        self.browse_button.clicked.connect(self._browse)
        self.refresh_button = qt.QPushButton('Refresh')
        self.refresh_button.clicked.connect(lambda: self.load_directory(self.directory))
        address = qt.QHBoxLayout()
        self.up_button = navigation_button(self, 'Parent folder', qt.QStyle.StandardPixmap.SP_ArrowUp)
        self.up_button.clicked.connect(lambda: self.load_directory(self.directory.parent))
        address.addWidget(self.up_button)
        address.addWidget(qt.QLabel('Folder'))
        address.addWidget(self.path_edit, 1)
        address.addWidget(self.browse_button)
        address.addWidget(self.refresh_button)
        layout.addLayout(address)
        filters = qt.QHBoxLayout()
        self.mask = qt.QLineEdit('*')
        self.mask.setMaximumWidth(200)
        self.mask.setAccessibleName('Filename filter')
        filters.addWidget(qt.QLabel('Filter'))
        filters.addWidget(self.mask)
        self.filter_regex = qt.QCheckBox('Regex')
        self.filter_case = qt.QCheckBox('Match case')
        self.include_files = qt.QCheckBox('Files')
        self.include_files.setChecked(True)
        self.include_folders = qt.QCheckBox('Folders')
        self.include_hidden = qt.QCheckBox('Hidden')
        self.recursive = qt.QCheckBox('Subfolders')
        self.depth = qt.QSpinBox()
        self.depth.setRange(0, 1000)
        self.depth.setSpecialValueText('All levels')
        self.depth.setToolTip('Zero scans all levels; one includes immediate subfolders')
        for control in (self.filter_regex, self.filter_case, self.include_files, self.include_folders,
                        self.include_hidden, self.recursive, self.depth):
            filters.addWidget(control)
        self.filter_button = qt.QPushButton('Apply filter')
        self.filter_button.clicked.connect(lambda: self.load_directory(self.directory))
        filters.addWidget(self.filter_button)
        filters.addStretch()
        layout.addLayout(filters)
        splitter = qt.QSplitter()
        self.folder_model = qt.QFileSystemModel(self)
        self._folder_icon_provider = _FolderIconProvider()
        self.folder_model.setIconProvider(self._folder_icon_provider)
        # Navigation must include hidden ancestors (e.g. macOS /private or
        # dot-directories) so a directly opened folder can always be revealed.
        # Candidate visibility is still controlled separately by the file filter.
        self.folder_model.setFilter(qt.QDir.Filter.AllDirs | qt.QDir.Filter.NoDotAndDotDot | qt.QDir.Filter.Hidden)
        # Keep a stable filesystem/drive tree. The file list's working directory
        # must never become the tree's view root, hiding that folder and its peers.
        self.folder_model.setRootPath(self._tree_anchor)
        self.folder_model.directoryLoaded.connect(self._folder_directory_loaded)
        self.folder_tree = qt.QTreeView()
        self.folder_tree.setModel(self.folder_model)
        self.folder_tree.setUniformRowHeights(True)
        self.folder_tree.setAccessibleName('Folders')
        self.folder_tree.header().setStretchLastSection(False)
        self.folder_tree.setColumnWidth(0, 240)
        self.folder_tree.setHorizontalScrollMode(qt.QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._folder_reveal_timer = qt.QTimer(self)
        self._folder_reveal_timer.setSingleShot(True)
        self._folder_reveal_timer.timeout.connect(self._reveal_current_folder)
        for column in range(1, self.folder_model.columnCount()):
            self.folder_tree.hideColumn(column)
        self.folder_tree.clicked.connect(lambda index: self.load_directory(self.folder_model.filePath(index)))
        self.table = qt.QTreeWidget()
        self.table.setHeaderLabels(['Name', 'New name', 'Folder', 'Size', 'Modified', 'Status'])
        self.table.setRootIsDecorated(False)
        self.table.setUniformRowHeights(True)
        self.table.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAccessibleName('Original and preview filenames; selected rows will be renamed')
        self.table.itemSelectionChanged.connect(self.request_preview)
        self.table.itemDoubleClicked.connect(self._enter_folder)
        self.table.setColumnWidth(0, 240)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 150)
        splitter.addWidget(self.folder_tree)
        splitter.addWidget(self.table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 1000])
        layout.addWidget(splitter, 1)
        selection = qt.QHBoxLayout()
        self.select_all_button = qt.QPushButton('Select all')
        self.select_all_button.clicked.connect(self.table.selectAll)
        self.select_none_button = qt.QPushButton('Select none')
        self.select_none_button.clicked.connect(self.table.clearSelection)
        selection.addWidget(self.select_all_button)
        selection.addWidget(self.select_none_button)
        self.selection_label = qt.QLabel()
        selection.addWidget(self.selection_label)
        selection.addStretch()
        selection.addWidget(qt.QLabel('Rules combine in numbered order · positions start at 0'))
        layout.addLayout(selection)
        self.controls = RenameRuleControls()
        self.controls.changed.connect(self.request_preview)
        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.controls)
        scroll.setMinimumHeight(250)
        scroll.setMaximumHeight(480)
        layout.addWidget(scroll)
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self._finished)
        layout.addWidget(self.progress)
        self.status = qt.QLabel('Choose files and configure rules to see the live preview.')
        self.status.setWordWrap(True)
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)
        actions = qt.QHBoxLayout()
        self.load_preset_button = qt.QPushButton('Load rules…')
        self.load_preset_button.clicked.connect(self.load_preset)
        self.save_preset_button = qt.QPushButton('Save rules…')
        self.save_preset_button.clicked.connect(self.save_preset)
        self.reset_button = qt.QPushButton('Reset rules')
        self.reset_button.clicked.connect(lambda: self.controls.set_rules(RenameRules()))
        self.preview_button = qt.QPushButton('Preview')
        # Reserve the wider label so offering cancellation cannot move nearby buttons.
        preview_width = self.preview_button.sizeHint().width()
        self.preview_button.setText('Cancel preview')
        self.preview_button.setFixedWidth(max(preview_width, self.preview_button.sizeHint().width()))
        self.preview_button.setText('Preview')
        self.preview_button.clicked.connect(self._preview_clicked)
        self.undo_button = qt.QPushButton('Undo last rename')
        self.undo_button.clicked.connect(self.undo)
        self.rename_button = qt.QPushButton('Rename selected')
        self.rename_button.clicked.connect(self.apply)
        for button in (self.load_preset_button, self.save_preset_button, self.reset_button):
            actions.addWidget(button)
        actions.addStretch()
        for button in (self.preview_button, self.undo_button, self.rename_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.preview_timer = qt.QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self._preview)
        self._update_actions()
        if paths:
            qt.QTimer.singleShot(0, lambda: self._load_paths(paths))
        else:
            qt.QTimer.singleShot(0, lambda: self.load_directory(self.directory))

    def selected_paths(self):
        return tuple(item.data(0, qt.Qt.ItemDataRole.UserRole) for item in self.table.selectedItems())

    def _browse(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Choose folder', str(self.directory))
        if path:
            self.load_directory(path)

    def _enter_folder(self, item, column):
        path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if self._items[path][2]:
            self.load_directory(path)

    def _folder_directory_loaded(self, path):
        self._loaded_tree_directories.add(Path(path))
        pending = self._folder_reveal_pending
        # Qt populates directories asynchronously. Retry only loads on the
        # requested branch, and leave user-expanded/collapsed branches alone.
        if pending is not None and Path(path) in (pending, *pending.parents):
            # Let Qt apply its queued directory sorting/layout before scrolling.
            self._folder_reveal_timer.start(0)

    def _reveal_current_folder(self):
        path = self._folder_reveal_pending
        if path is None:
            return
        index = self.folder_model.index(str(path))
        if not index.isValid():
            return
        depth = 1
        ancestor = index.parent()
        while ancestor.isValid():
            depth += 1
            self.folder_tree.expand(ancestor)
            ancestor = ancestor.parent()
        self.folder_tree.expand(index)
        # A deep branch can indent beyond a narrow sidebar column, giving its
        # row a zero-width visual rect and preventing scrollTo from revealing it.
        width = depth * self.folder_tree.indentation() + self.folder_tree.fontMetrics().horizontalAdvance(path.name) + 48
        if self.folder_tree.columnWidth(0) < width:
            self.folder_tree.setColumnWidth(0, width)
        self.folder_tree.setCurrentIndex(index)
        self.folder_tree.doItemsLayout()
        self.folder_tree.scrollTo(index, qt.QAbstractItemView.ScrollHint.PositionAtCenter)
        self.folder_tree.horizontalScrollBar().setValue(max(0, depth * self.folder_tree.indentation() - 20))
        # An index can exist before its parents' rows have arrived. Keep the
        # pending reveal until the selected folder is actually in the view.
        rectangle = self.folder_tree.visualRect(index)
        # Later sibling inserts/sorting in an unloaded ancestor can move this
        # row out of view again. Finish the reveal only after the entire branch
        # has loaded, then stop following it so manual tree scrolling is respected.
        branch_loaded = all(parent in self._loaded_tree_directories for parent in (path, *path.parents))
        if branch_loaded and not rectangle.isEmpty() and self.folder_tree.viewport().rect().intersects(rectangle):
            self._folder_reveal_pending = None

    def _scan_options(self):
        return dict(mask=self.mask.text(), files=self.include_files.isChecked(),
                    folders=self.include_folders.isChecked(), hidden=self.include_hidden.isChecked(),
                    recursive=self.recursive.isChecked(), max_depth=self.depth.value(),
                    regex=self.filter_regex.isChecked(), match_case=self.filter_case.isChecked())

    def load_directory(self, path):
        if self.progress.busy:
            return False
        directory = Path(path).absolute()
        options = self._scan_options()
        def work(report, cancelled):
            paths = scan_directory(directory, cancelled=cancelled, **options)
            return directory.resolve(), self._scan_items(paths, cancelled)
        self._start('scan', work, 'Scanning folder…')
        return True

    @staticmethod
    def _scan_items(paths, cancelled):
        items = []
        for path in paths:
            if cancelled():
                from commonUtils.renameUtils import RenameCancelled
                raise RenameCancelled('Folder scan cancelled')
            path = path.parent.resolve() / path.name
            info = path.lstat()
            items.append((path, info.st_size, info.st_mtime, stat.S_ISDIR(info.st_mode)))
        return items

    def _load_paths(self, paths):
        self._start('scan', lambda report, cancelled: (self.directory.resolve(), self._scan_items(paths, cancelled)),
                    'Loading selected paths…')

    def _fill(self, items):
        blocker = qt.QSignalBlocker(self.table)
        self.table.setUpdatesEnabled(False)
        self.table.clear()
        self._items = {}
        for path, size, modified, folder in sorted(items, key=lambda item: natural_path_key(item[0])):
            self._items[path] = (size, modified, folder)
            item = qt.QTreeWidgetItem([path.name, path.name, str(path.parent),
                                      '' if folder else format_size(size),
                                      datetime.fromtimestamp(modified).strftime('%Y-%m-%d %H:%M'), ''])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, path)
            item.setToolTip(0, str(path))
            item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if folder
                                                    else qt.QStyle.StandardPixmap.SP_FileIcon))
            self.table.addTopLevelItem(item)
            item.setSelected(True)
        self.table.setUpdatesEnabled(True)
        del blocker
        self.plan = None
        self._generation += 1
        self.selection_label.setText(f'{len(items)} items selected')

    def request_preview(self):
        self._generation += 1
        self.rename_button.setEnabled(False)
        self.preview_timer.start()

    def _preview_clicked(self):
        if self.progress.busy and self._state == 'preview':
            self.preview_timer.stop()
            self._pending_preview = False
            self.progress.request_cancel()
        else:
            self.request_preview()

    def _preview(self):
        if self.progress.busy:
            self._pending_preview = True
            return
        generation, paths, rules = self._generation, self.selected_paths(), self.controls.rules()
        self.selection_label.setText(f'{len(paths)} of {self.table.topLevelItemCount()} selected')
        self._start('preview', lambda report, cancelled: (generation, plan_renames(paths, rules, cancelled=cancelled)),
                    'Updating rename preview…')

    def _show_plan(self, generation, plan):
        if generation != self._generation:
            return
        self.plan, self._plan_generation = plan, generation
        entries = {entry.source: entry for entry in plan.entries}
        vertical = self.table.verticalScrollBar().value()
        horizontal = self.table.horizontalScrollBar().value()
        self.table.setUpdatesEnabled(False)
        blocker = qt.QSignalBlocker(self.table)
        try:
            for index in range(self.table.topLevelItemCount()):
                item = self.table.topLevelItem(index)
                entry = entries.get(item.data(0, qt.Qt.ItemDataRole.UserRole))
                item.setText(1, entry.target.name if entry else item.text(0))
                status = entry.error if entry and entry.error else 'Ready' if entry and entry.changed else 'Unchanged' if entry else 'Not selected'
                item.setText(5, status)
                color = qt.QColor('#bb2525') if entry and entry.error else self.palette().color(
                    qt.QPalette.ColorRole.Link if entry and entry.changed else qt.QPalette.ColorRole.Text)
                item.setForeground(1, color)
                item.setForeground(5, color)
                item.setToolTip(5, status)
        finally:
            del blocker
            self.table.setUpdatesEnabled(True)
            self.table.verticalScrollBar().setValue(vertical)
            self.table.horizontalScrollBar().setValue(horizontal)
        errors = sum(bool(entry.error) for entry in plan.entries)
        self.status.setText(f'{len(plan.entries)} selected · {len(plan.changes)} changes · {errors} errors. '
                            + ('Fix all errors before renaming.' if errors else 'No disk changes until Rename selected.'))
        self.preview_ready.emit(plan)

    def _start(self, state, work, message):
        self.preview_timer.stop()
        self._state = state
        if state == 'scan':
            self.plan = None
        self.progress.start(work, message=message, cancel_message='Cancelling; restoring original names if needed…',
                            show_progress=state != 'preview')
        self._update_actions()

    def _update_actions(self):
        busy = self.progress.busy
        editing = not busy or self._state == 'preview'
        self.controls.setEnabled(editing)
        self.table.setEnabled(editing)
        self.select_all_button.setEnabled(editing)
        self.select_none_button.setEnabled(editing)
        for widget in (self.folder_tree, self.path_edit, self.browse_button, self.refresh_button,
                       self.filter_button, self.load_preset_button, self.save_preset_button,
                       self.reset_button):
            widget.setEnabled(not busy)
        previewing = busy and self._state == 'preview'
        self.preview_button.setText('Cancel preview' if previewing else 'Preview')
        self.preview_button.setEnabled(not busy or (previewing and not self.progress.cancelled.is_set()))
        self.up_button.setEnabled(not busy and self.directory.parent != self.directory)
        self.rename_button.setEnabled(bool(not busy and self.plan and self.plan.valid and self.plan.changes
                                           and self._plan_generation == self._generation))
        self.undo_button.setEnabled(bool(not busy and self.receipt and self.receipt.entries))

    def _finished(self, result, error):
        state, self._state = self._state, ''
        self.progress.hide()
        if state in ('scan', 'preview') and self.progress.cancelled.is_set():
            error = 'Folder scan cancelled' if state == 'scan' else 'Preview cancelled'
        if error:
            self.status.setText(error)
            if state in ('preview', 'rename'):
                self.plan = None
        elif state == 'scan':
            self.directory, items = result
            self.path_edit.setText(str(self.directory))
            self._fill(items)
            if self.directory.anchor != self._tree_anchor:
                self._tree_anchor = self.directory.anchor
                self.folder_model.setRootPath(self._tree_anchor)
            self._folder_reveal_pending = self.directory
            self._folder_reveal_timer.start(0)
            self.request_preview()
        elif state == 'preview':
            self._show_plan(*result)
        else:
            if result.success:
                previous = self._items
                mapping = {entry.source: entry.target for entry in result.entries}
                items = [(mapping.get(path, path), *details) for path, details in previous.items()]
                self._fill(items)
                if state == 'rename':
                    self.receipt = result
                else:
                    self.receipt = None
                self.renamed.emit(result)
                self.status.setText(f'{len(result.entries)} items {"renamed" if state == "rename" else "restored"}. '
                                    'Rules retained; change a rule or click Preview to prepare another batch.')
            else:
                self.plan = None
                message = result.error + (' Batch rolled back.' if not result.recovery else '')
                if result.recovery:
                    message += '\nManual recovery required:\n' + '\n'.join(f'{current} → {original}: {problem}'
                                                                          for current, original, problem in result.recovery)
                    self.receipt = None
                self.renamed.emit(result)
                self.status.setText(message)
        if self._pending_preview:
            self._pending_preview = False
            self.preview_timer.start()
        self._update_actions()
        self.idle.emit()
        if self._closing:
            self.close()

    def apply(self):
        if (self.progress.busy or not self.plan or not self.plan.valid or not self.plan.changes
                or self._plan_generation != self._generation):
            return False
        plan = self.plan
        self._start('rename', lambda report, cancelled: apply_renames(plan, report=report, cancelled=cancelled),
                    'Renaming selected items…')
        return True

    def undo(self):
        if self.progress.busy or not self.receipt:
            return False
        receipt = self.receipt
        self._start('undo', lambda report, cancelled: undo_renames(receipt, report=report, cancelled=cancelled),
                    'Restoring original names…')
        return True

    def save_preset(self):
        path, _ = qt.QFileDialog.getSaveFileName(self, 'Save rename rules', '', 'JSON rules (*.json)')
        if not path:
            return False
        try:
            data = json.dumps(asdict(self.controls.rules()), ensure_ascii=False, indent=2).encode('utf-8')
            file = qt.QSaveFile(path)
            if not file.open(qt.QIODevice.OpenModeFlag.WriteOnly):
                raise OSError(file.errorString())
            if file.write(data) != len(data) or not file.commit():
                raise OSError(file.errorString())
            return True
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return False

    def load_preset(self):
        if self.progress.busy:
            return False
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Load rename rules', '', 'JSON rules (*.json)')
        if not path:
            return False
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            self.controls.set_rules(RenameRules(**data))
            return True
        except (OSError, ValueError, TypeError, re.error, OverflowError) as error:
            self.status.setText(f'Could not load rules: {error}')
            return False

    def can_close(self):
        if self.progress.busy:
            self.progress.request_cancel()
            return False
        return True

    def closeEvent(self, event):
        if self.can_close():
            self.preview_timer.stop()
            self._folder_reveal_timer.stop()
            self._folder_reveal_pending = None
            super().closeEvent(event)
        else:
            self._closing = True
            event.ignore()
