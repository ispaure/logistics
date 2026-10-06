"""Folder browser with read-only metadata and a separate context-menu editor."""

from pathlib import Path
from datetime import datetime
from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages, load_preview
from features.comics.folder_stats import scan_folders, format_size
from features.comics.reader import open_reader
from features.comics import desktop_actions
from features.comics.catalog import LibraryCatalog
from features.comics.selection import normalize_targets
from features.comics.library_config import configured_libraries
from .metadata_editor import MetadataEditor
from .operations import Operation
from .file_browser import FileBrowser
from .filesystem_model import ComicFileSystemModel
from .navigation import NavigationBar


class ComicLibraryWindow(qt.QMainWindow):
    suggestions_changed = qt.Signal(object)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'Comics — {Path(root_path).name}')
        self.resize(1200, 800)
        self.root_path = Path(root_path)
        self.libraries, self.library_config_error = configured_libraries(self.root_path)
        self.document = None
        self.busy = False
        self.metadata_windows = []
        self.reader_busy = False
        self.folder_busy = False
        self.folder_pending = False
        self.close_after_folders = False
        self.cover_pixmap = qt.QPixmap()
        self.catalog = LibraryCatalog(root_path)
        self.suggestions = {}
        self.catalog_busy = False
        self.catalog_pending = False
        self.close_after_catalog = False
        container = qt.QWidget()
        layout = qt.QVBoxLayout(container)
        library_row = qt.QHBoxLayout()
        library_row.addWidget(qt.QLabel('Library:'))
        self.library_selector = qt.QComboBox()
        self.library_selector.setAccessibleName('Select comics library')
        library_row.addWidget(self.library_selector, 1)
        self.view_selector = qt.QComboBox()
        self.view_selector.addItems(['List', 'Tiles', 'Columns'])
        self.view_selector.setAccessibleName('Browser view')
        library_row.addWidget(self.view_selector)
        layout.addLayout(library_row)
        self.navigation = NavigationBar(self)
        self.up_button = self.navigation.up
        self.navigation.requested.connect(self._navigate)
        layout.addWidget(self.navigation)
        self.refresh_button = qt.QPushButton('Refresh')
        self.refresh_button.clicked.connect(self._refresh_files)
        library_row.addWidget(self.refresh_button)
        self.library_status = qt.QLabel()
        self.library_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.library_status)
        self.catalog_status = qt.QLabel('Reading library suggestions…')
        self.catalog_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.catalog_status)
        splitter = qt.QSplitter()
        self.splitter = splitter
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(container)
        self.model = ComicFileSystemModel(self)
        self.model.setReadOnly(True)
        self.model.setFilter(qt.QDir.Filter.AllDirs | qt.QDir.Filter.Files | qt.QDir.Filter.NoDotAndDotDot)
        self.model.setRootPath(str(root_path))
        self.tree = qt.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(str(root_path)))
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, qt.Qt.SortOrder.AscendingOrder)
        self.tree.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setColumnWidth(0, 400)
        self.tree.setColumnWidth(3, 180)
        self.tree.setColumnWidth(1, 90)
        self.tree.hideColumn(2)
        self.tree.header().moveSection(3, 1)
        self.tree.collapseAll()
        self.browser = FileBrowser(self.model, self.tree, self)
        self.browser.context_requested.connect(self._context_menu)
        self.browser.activated.connect(self._activate)
        self.browser.selection_changed.connect(self._selection_changed)
        self.browser.idle.connect(self.close)
        self.browser.directory_changed.connect(self.navigation.set_directory)
        self.view_selector.currentIndexChanged.connect(self.browser.set_mode)
        splitter.addWidget(self.browser)
        panel = qt.QWidget()
        self.preview_panel = panel
        panel.setMinimumWidth(280)
        panel_layout = qt.QVBoxLayout(panel)
        self.heading = qt.QLabel('Comic')
        self.heading.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        panel_layout.addWidget(self.heading)
        self.message = qt.QLabel('Select a CBZ file. Right-click it and choose Edit Metadata to make changes.')
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        panel_layout.addWidget(self.message)
        self.cover = qt.QLabel()
        self.cover.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.cover.setMinimumSize(180, 200)
        self.cover.setMaximumHeight(500)
        panel_layout.addWidget(self.cover)
        self.preview = qt.QPlainTextEdit()
        self.preview.setReadOnly(True)
        panel_layout.addWidget(self.preview, 1)
        splitter.addWidget(panel)
        splitter.setSizes([700, 500])
        for name, path in self.libraries:
            self.library_selector.addItem(name, path)
            if not path.is_dir():
                item = self.library_selector.model().item(self.library_selector.count() - 1)
                item.setEnabled(False)
                item.setToolTip(f'Folder not found: {path}')
        initial = next((index for index, (_, path) in enumerate(self.libraries) if path.is_dir()), -1)
        self.library_selector.setCurrentIndex(initial)
        self.library_selector.currentIndexChanged.connect(self._library_changed)
        self._library_changed(initial)
        self._refresh_catalog()

    def _library_changed(self, index):
        if self.busy:
            self.refresh_pending = True
        path = self.library_selector.itemData(index) if index >= 0 else None
        available = path is not None and path.is_dir()
        self.browser.setVisible(available)
        self.library_status.setVisible(not available)
        self.navigation.set_library(path if available else None)
        if not available:
            self.library_status.setText(self.library_config_error or 'No configured library folders are available.')
        else:
            self.browser.set_root(path)
            self._refresh_folder_totals()
        self.cover.clear()
        self.cover_pixmap = qt.QPixmap()
        self.document = None
        self.preview.clear()
        self.preview_panel.show()
        self.heading.setText('Comic')
        self.message.setText('Select a CBZ file. Right-click it and choose Edit Metadata to make changes.')

    def _refresh_catalog(self):
        if self.catalog_busy:
            self.catalog_pending = True
            return
        self.catalog_busy = True
        self.catalog_pending = False
        self.catalog_status.setText('Updating library suggestions…')
        self.catalog_operation = Operation(
            lambda: self.catalog.refresh(self.catalog_operation.isInterruptionRequested), self)
        self.catalog_operation.completed.connect(self._catalog_loaded)
        self.catalog_operation.finished.connect(self._catalog_finished)
        self.catalog_operation.start()

    def _catalog_loaded(self, result, error):
        if error:
            self.catalog_status.setText('Library suggestions could not be updated; manual entry is available.')
            self.catalog_status.setToolTip(error)
        elif result is not None:
            self.suggestions = result['suggestions']
            self.suggestions_changed.emit(self.suggestions)
            status = f"Suggestions from {result['count']} comics"
            if result['errors']:
                status += f" · {len(result['errors'])} indexing issue(s)"
            self.catalog_status.setText(status)
            self.catalog_status.setToolTip('\n'.join(result['errors']))

    def _catalog_finished(self):
        self.catalog_busy = False
        self.catalog_operation.deleteLater()
        if self.close_after_catalog:
            self.close()
        elif self.catalog_pending:
            self._refresh_catalog()

    def _navigate(self, path):
        library = self.library_selector.currentData()
        path = Path(path)
        if library is not None and path.is_dir() and (path == library or library in path.parents):
            self.browser.set_root(path)
        else:
            self.navigation.set_directory(self.browser.browsing_directory())

    def _up(self):
        directory = self.browser.browsing_directory()
        library = self.library_selector.currentData()
        if directory is not None and directory != library:
            self._navigate(directory.parent)

    def _refresh_files(self):
        self._refresh_folder_totals()
        self._refresh_catalog()
        for path in list(self.browser.covers.icons):
            self.browser.covers.invalidate(path)
        self._selection_changed()

    def _refresh_folder_totals(self):
        if self.folder_busy:
            self.folder_pending = True
            self.folder_operation.requestInterruption()
            return
        root = self.library_selector.currentData()
        self.model.set_folder_totals({})
        if root is None:
            return
        self.folder_busy = True
        self.folder_pending = False
        self.folder_operation = Operation(
            lambda: scan_folders(root, self.folder_operation.isInterruptionRequested), self)
        self.folder_operation.completed.connect(lambda result, error: self._folders_loaded(root, result, error))
        self.folder_operation.finished.connect(self._folders_finished)
        self.folder_operation.start()

    def _folders_loaded(self, root, result, error):
        if root == self.library_selector.currentData() and result is not None and not self.folder_pending:
            self.model.set_folder_totals(result)
            selected = self.browser.selected_rows()
            if len(selected) == 1 and self.model.isDir(selected[0]):
                self._folder_details(Path(self.model.filePath(selected[0])))

    def _folders_finished(self):
        self.folder_busy = False
        self.folder_operation.deleteLater()
        if self.close_after_folders:
            self.close()
        elif self.folder_pending:
            self._refresh_folder_totals()

    def _folder_details(self, path):
        self.heading.setText(path.name)
        self.message.setText('Folder')
        self.cover.clear()
        self.cover_pixmap = qt.QPixmap()
        icon = self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon)
        self.cover.setPixmap(icon.pixmap(96, 96).scaled(96, 96, qt.Qt.AspectRatioMode.KeepAspectRatio,
                                                        qt.Qt.TransformationMode.SmoothTransformation))
        values = [f'Path: {path}']
        try:
            values.append(f'Modified: {datetime.fromtimestamp(path.stat().st_mtime):%Y-%m-%d %H:%M:%S}')
        except OSError:
            values.append('Folder is no longer available.')
        stats = self.model.folder_totals.get(path)
        if stats is None:
            values.append('Total size: Calculating…' if self.folder_busy else 'Total size: Unavailable')
        else:
            values.extend([f'Total size: {format_size(stats.size)}', f'Comics: {stats.comics:,}',
                           f'Files: {stats.files:,}', f'Subfolders: {stats.folders:,}'])
            if stats.skipped:
                values.append(f'{stats.skipped:,} unreadable items or symbolic links excluded.')
        self.preview.setPlainText('\n\n'.join(values))

    def _activate(self, index):
        path = Path(self.model.filePath(index))
        if path.is_dir():
            self._navigate(path)
        elif path.suffix.lower() == '.cbz' and not self.reader_busy:
            self.reader_busy = True
            self.reader_operation = Operation(lambda: ComicPages(path), self)
            self.reader_operation.completed.connect(self._reader_opened)
            self.reader_operation.finished.connect(self._reader_finished)
            self.reader_operation.start()

    def _reader_opened(self, result, error):
        if error:
            qt.QMessageBox.warning(self, 'Cannot open reader', error)
        else:
            try:
                open_reader(result)
            except Exception as issue:
                qt.QMessageBox.warning(self, 'Cannot open reader', str(issue))

    def _reader_finished(self):
        self.reader_busy = False
        self.reader_operation.deleteLater()

    def _desktop_action(self, action, path):
        try:
            action(path)
        except Exception as error:
            qt.QMessageBox.warning(self, 'Cannot open file', str(error))

    def _context_menu(self, index):
        menu = self._context_menu_for(index)
        if menu is not None:
            menu.exec(self.browser.context_position)
            menu.deleteLater()

    def _context_menu_for(self, index):
        path = Path(self.model.filePath(index)) if index.isValid() else None
        if path is None or not path.exists():
            return
        selected = self.browser.selected_rows()
        if not any(item == index.siblingAtColumn(0) for item in selected):
            selected = [index.siblingAtColumn(0)]
        targets = [Path(self.model.filePath(item)) for item in selected
                   if self.model.isDir(item) or self.model.filePath(item).lower().endswith('.cbz')]
        menu = qt.QMenu(self)
        action = menu.addAction('Open in Default App')
        action.triggered.connect(lambda: self._desktop_action(desktop_actions.open_default, path))
        action = menu.addAction(desktop_actions.reveal_label())
        action.triggered.connect(lambda: self._desktop_action(desktop_actions.reveal, path))
        if path.is_dir() or path.suffix.lower() == '.cbz':
            menu.addSeparator()
            action = menu.addAction('Edit Metadata')
            action.triggered.connect(lambda: self._open_editor(targets, index))
        return menu

    def _open_editor(self, path, index=None):
        targets = normalize_targets(path)
        path = targets[0]
        existing = next((window for window in self.metadata_windows
                         if set(window.targets) == set(targets) and window.isVisible()), None)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return existing
        for window in list(self.metadata_windows):
            if not window.isVisible() and not window.busy:
                self.metadata_windows.remove(window)
                window.deleteLater()
        index = index if index is not None else self.model.index(str(path))
        parent_index = index.parent()
        siblings = []
        for row in range(self.model.rowCount(parent_index)):
            child = self.model.index(row, 0, parent_index)
            candidate = Path(self.model.filePath(child))
            if candidate.suffix.lower() == '.cbz' and not self.model.isDir(child):
                siblings.append(candidate)
        window = MetadataEditor(targets, siblings, self)
        window.tabs.set_suggestions(self.suggestions)
        self.suggestions_changed.connect(window.tabs.set_suggestions)
        self.metadata_windows.append(window)
        window.saved.connect(self._metadata_saved)
        window.show()
        return window

    def _metadata_saved(self, path):
        self._refresh_catalog()
        self._refresh_folder_totals()
        self.browser.covers.invalidate(path)
        # Reload preview after the save. If a preview load is in progress, queue
        # a refresh rather than starting two threads on the same owner.
        if self.busy:
            self.refresh_pending = True
        elif self.model.filePath(self.browser.current_index()) == str(path):
            if len(self.browser.selected_rows()) > 1:
                self._selection_changed()
            else:
                self._load(path)

    def _selection_changed(self, selected=None, deselected=None):
        indexes = self.browser.selected_rows()
        if len(indexes) > 1:
            if self.busy:
                self.refresh_pending = True
                return
            self.document = None
            self.cover.clear()
            self.cover_pixmap = qt.QPixmap()
            self.preview.clear()
            self.preview_panel.show()
            self.heading.setText(f'{len(indexes)} items selected')
            self.message.setText('Right-click the selection to edit its CBZ metadata together. Folders include subfolders.')
        else:
            index = indexes[0] if indexes else qt.QModelIndex()
            self._selected(index, qt.QModelIndex())

    def _selected(self, current, previous):
        if self.busy:
            self.refresh_pending = True
            return
        path = Path(self.model.filePath(current)) if current.isValid() else None
        self.cover.clear()
        self.cover_pixmap = qt.QPixmap()
        self.cover.setToolTip('')
        self.document = None
        self.preview.clear()
        self.preview_panel.show()
        self.heading.setText(path.name if path else 'Library')
        self.message.setText('Select a CBZ file. Right-click it and choose Edit Metadata to make changes.')
        if path is not None and path.is_dir():
            self._folder_details(path)
        elif path is not None and path.is_file() and path.suffix.lower() == '.cbz':
            self._load(path)
        elif path is not None and path.is_file():
            self.preview.setPlainText(f'Path: {path}\n\nSize: {format_size(path.stat().st_size)}')

    def _load(self, path):
        self.busy = True
        self.refresh_pending = False
        self.message.setText('Reading ComicInfo.xml…')
        self.operation = Operation(lambda: load_preview(path), self)
        self.operation.completed.connect(self._loaded)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, result, error):
        if self.refresh_pending:
            return
        if error:
            self.message.setText(f'Cannot read comic: {error}')
            self.cover.clear()
            self.cover.setText('No cover available')
            self.preview_panel.show()
            return
        document, cover, cover_error = result
        values = []
        for field, label in (('Series', 'Series'), ('Writer', 'Author'), ('Volume', 'Volume'),
                             ('Number', 'Issue'), ('Count', 'Issues'), ('Title', 'Title'),
                             ('Publisher', 'Publisher'), ('Year', 'Year'), ('Summary', 'Description')):
            try:
                value = document.info.get_field(field)
            except ValueError:
                value = ''
            if value:
                values.append(f'{label}: {value}')
        self.preview.setPlainText('\n\n'.join(values))
        self.document = document
        self.cover_pixmap.loadFromData(cover)
        if self.cover_pixmap.isNull():
            self.cover.clear()
            self.cover.setText('No cover available')
        else:
            self.cover.setPixmap(self.cover_pixmap.scaled(320, 440, qt.Qt.AspectRatioMode.KeepAspectRatio,
                                                         qt.Qt.TransformationMode.SmoothTransformation))
        self.cover.setToolTip(cover_error)
        self.message.setText('')
        self.preview_panel.show()
        if self.preview_panel.width() < 280:
            self.splitter.setSizes([700, 380])

    def _finished(self):
        self.busy = False
        self.browser.setEnabled(True)
        self.view_selector.setEnabled(True)
        self.navigation.set_directory(self.browser.browsing_directory())
        self.library_selector.setEnabled(True)
        self.operation.deleteLater()
        if self.refresh_pending:
            self._selection_changed()

    def closeEvent(self, event):
        if self.busy or self.reader_busy or any(window.busy for window in self.metadata_windows):
            event.ignore()
            return
        for window in list(self.metadata_windows):
            if window.isVisible():
                window.reject()
                if window.isVisible():
                    event.ignore()
                    return
        if self.browser.stop():
            self.hide()
            event.ignore()
            return
        if self.folder_busy:
            self.close_after_folders = True
            self.folder_operation.requestInterruption()
            self.hide()
            event.ignore()
            return
        if self.catalog_busy:
            self.close_after_catalog = True
            self.catalog_operation.requestInterruption()
            self.hide()
            event.ignore()
            return
        event.accept()
