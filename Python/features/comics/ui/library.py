"""Folder browser with read-only metadata and a separate context-menu editor."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from features.comics.comicinfo import ComicInfoXML
from features.comics.library import ComicDocument
from features.comics.catalog import LibraryCatalog
from features.comics.selection import normalize_targets
from .metadata_editor import MetadataEditor
from .operations import Operation


class ComicLibraryWindow(qt.QMainWindow):
    suggestions_changed = qt.Signal(object)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'Comics — {Path(root_path).name}')
        self.resize(1200, 800)
        self.document = None
        self.busy = False
        self.metadata_windows = []
        self.catalog = LibraryCatalog(root_path)
        self.suggestions = {}
        self.catalog_busy = False
        self.catalog_pending = False
        self.close_after_catalog = False
        container = qt.QWidget()
        layout = qt.QVBoxLayout(container)
        location = qt.QLabel(str(root_path))
        location.setTextFormat(qt.Qt.TextFormat.PlainText)
        location.setTextInteractionFlags(qt.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(location)
        self.catalog_status = qt.QLabel('Reading library suggestions…')
        self.catalog_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.catalog_status)
        splitter = qt.QSplitter()
        layout.addWidget(splitter, 1)
        self.setCentralWidget(container)
        self.model = qt.QFileSystemModel(self)
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
        self.tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        splitter.addWidget(self.tree)
        panel = qt.QWidget()
        panel_layout = qt.QVBoxLayout(panel)
        self.heading = qt.QLabel('ComicInfo metadata')
        self.heading.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        panel_layout.addWidget(self.heading)
        self.message = qt.QLabel('Select a CBZ file. Right-click it and choose Edit Metadata to make changes.')
        self.message.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.message.setWordWrap(True)
        panel_layout.addWidget(self.message)
        self.preview = qt.QPlainTextEdit()
        self.preview.setReadOnly(True)
        panel_layout.addWidget(self.preview, 1)
        splitter.addWidget(panel)
        splitter.setSizes([700, 500])
        self.tree.selectionModel().selectionChanged.connect(self._selection_changed)
        self._refresh_catalog()

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

    def _context_menu(self, point):
        menu = self._context_menu_for(self.tree.indexAt(point))
        if menu is not None:
            menu.exec(self.tree.viewport().mapToGlobal(point))
            menu.deleteLater()

    def _context_menu_for(self, index):
        path = Path(self.model.filePath(index)) if index.isValid() else None
        if path is None or not (path.is_dir() or (path.is_file() and path.suffix.lower() == '.cbz')):
            return
        selected = self.tree.selectionModel().selectedRows(0)
        if not any(item == index.siblingAtColumn(0) for item in selected):
            selected = [index.siblingAtColumn(0)]
        targets = [Path(self.model.filePath(item)) for item in selected
                   if self.model.isDir(item) or self.model.filePath(item).lower().endswith('.cbz')]
        menu = qt.QMenu(self)
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
        # Reload preview after the save. If a preview load is in progress, queue
        # a refresh rather than starting two threads on the same owner.
        if self.busy:
            self.refresh_pending = True
        elif self.model.filePath(self.tree.currentIndex()) == str(path):
            if len(self.tree.selectionModel().selectedRows(0)) > 1:
                self._selection_changed()
            else:
                self._load(path)

    def _selection_changed(self, selected=None, deselected=None):
        indexes = self.tree.selectionModel().selectedRows(0)
        if len(indexes) > 1:
            if self.busy:
                self.refresh_pending = True
                return
            self.document = None
            self.preview.clear()
            self.heading.setText(f'{len(indexes)} items selected')
            self.message.setText('Right-click the selection to edit its CBZ metadata together. Folders include subfolders.')
        else:
            index = indexes[0] if indexes else qt.QModelIndex()
            self._selected(index, qt.QModelIndex())

    def _selected(self, current, previous):
        if self.busy:
            self.refresh_pending = True
            return
        path = Path(self.model.filePath(current))
        self.document = None
        self.preview.clear()
        self.heading.setText(path.name)
        self.message.setText('Select a CBZ file. Right-click it and choose Edit Metadata to make changes.')
        if path.is_file() and path.suffix.lower() == '.cbz':
            self._load(path)

    def _load(self, path):
        self.busy = True
        self.refresh_pending = False
        self.tree.setEnabled(False)
        self.message.setText('Reading ComicInfo.xml…')
        self.operation = Operation(lambda: ComicDocument(path), self)
        self.operation.completed.connect(self._loaded)
        self.operation.finished.connect(self._finished)
        self.operation.start()

    def _loaded(self, document, error):
        if error:
            self.message.setText(f'Cannot read metadata: {error}')
            return
        values = []
        for field in ComicInfoXML.FIELDS:
            try:
                value = document.info.get_field(field)
            except ValueError:
                value = '(complex or duplicate field; preserved in XML)'
            if value:
                values.append(f'{field}: {value}')
        self.preview.setPlainText('\n\n'.join(values))
        self.document = document
        self.message.setText('Right-click the file and choose Edit Metadata.' if document.exists else
                             'No ComicInfo.xml yet. Use Edit Metadata to create it.')

    def _finished(self):
        self.busy = False
        self.tree.setEnabled(True)
        self.operation.deleteLater()
        if self.refresh_pending:
            self._selection_changed()

    def closeEvent(self, event):
        if self.busy or any(window.busy for window in self.metadata_windows):
            event.ignore()
            return
        for window in list(self.metadata_windows):
            if window.isVisible():
                window.reject()
                if window.isVisible():
                    event.ignore()
                    return
        if self.catalog_busy:
            self.close_after_catalog = True
            self.catalog_operation.requestInterruption()
            self.hide()
            event.ignore()
            return
        event.accept()
