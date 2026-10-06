"""Comics library controls and domain services around the reusable file browser."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from features.comics import register_file_types
from features.comics.browser_support import directory_actions, folder_fields
from features.comics.pages import ComicPages
from features.comics.reader import open_reader
from features.comics.catalog import LibraryCatalog
from features.comics.selection import normalize_targets
from features.comics.library_config import configured_libraries
from .metadata_editor import MetadataEditor
from .operations import Operation


class ComicLibraryWindow(qt.QMainWindow):
    suggestions_changed = qt.Signal(object)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        register_file_types()
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'Comics — {Path(root_path).name}')
        self.resize(1200, 800)
        self.root_path = Path(root_path)
        self.libraries, self.library_config_error = configured_libraries(self.root_path)
        self.metadata_windows = []
        self.reader_busy = False
        self.reader_connections = []
        self.catalog = LibraryCatalog(root_path)
        self.suggestions = {}
        self.catalog_busy = False
        self.catalog_pending = False
        self.close_after_catalog = False
        container = qt.QWidget()
        layout = qt.QVBoxLayout(container)
        row = qt.QHBoxLayout()
        row.addWidget(qt.QLabel('Library:'))
        self.library_selector = qt.QComboBox()
        self.library_selector.setAccessibleName('Select comics library')
        row.addWidget(self.library_selector, 1)
        layout.addLayout(row)
        self.library_status = qt.QLabel()
        self.library_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.library_status)
        self.catalog_status = qt.QLabel('Reading library suggestions…')
        self.catalog_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.catalog_status)
        self.file_browser = FileBrowser(parent=self,
            services={'comics.edit_metadata': lambda targets: self._open_editor(targets),
                      'comics.read': lambda path: self._read(path)},
            action_providers=(directory_actions,), folder_fields=folder_fields)
        self.file_browser.idle.connect(self.close)
        self.file_browser.refreshed.connect(self._refresh_catalog)
        layout.addWidget(self.file_browser, 1)
        self.setCentralWidget(container)
        # Keep the existing public handles for callers embedding the library window.
        self.browser = self.file_browser.views
        for name in ('model', 'tree', 'view_selector', 'navigation', 'splitter', 'preview_panel',
                     'heading', 'message', 'cover', 'refresh_button'):
            setattr(self, name, getattr(self.file_browser, name))
        self.up_button = self.navigation.up
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

    @property
    def busy(self):
        return self.file_browser.busy

    @property
    def folder_busy(self):
        return self.file_browser.folder_busy

    @property
    def preview(self):
        return self.file_browser.preview

    @property
    def cover_pixmap(self):
        return self.file_browser.cover_pixmap

    @property
    def document(self):
        for panel, details, error in self.file_browser.last_details or ():
            if details.payload is not None:
                return details.payload
        return None

    def _library_changed(self, index):
        path = self.library_selector.itemData(index) if index >= 0 else None
        available = path is not None and path.is_dir()
        self.file_browser.setVisible(available)
        self.library_status.setVisible(not available)
        if available:
            self.file_browser.set_directory(path)
        else:
            self.library_status.setText(self.library_config_error or 'No configured library folders are available.')

    def _navigate(self, path):
        self.file_browser.navigate(path)

    def _up(self):
        directory = self.browser.browsing_directory()
        if directory is not None and directory != self.navigation.library:
            self.file_browser.navigate(directory.parent)

    def _activate(self, index):
        self.file_browser._activate(index)

    def _context_menu_for(self, index):
        return self.file_browser.context_menu_for(index)

    def _context_menu(self, index):
        self.file_browser._context_menu(index)

    def _selection_changed(self, *args):
        self.file_browser._selection_changed()

    def _load(self, path):
        self.file_browser.load(self.model.object_for_path(path))

    def _read(self, path):
        if self.reader_busy:
            return
        self.reader_busy = True
        self.reader_operation = Operation(lambda: ComicPages(path), self)
        self.reader_operation.completed.connect(self._reader_opened)
        self.reader_operation.finished.connect(self._reader_finished)
        self.reader_operation.start()

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

    def _reader_opened(self, result, error):
        if error:
            qt.QMessageBox.warning(self, 'Cannot open reader', error)
        else:
            try:
                window = open_reader(result)
                if isinstance(window, qt.QMainWindow) and window not in self.reader_connections:
                    window.metadata_saved.connect(self._metadata_saved)
                    self.reader_connections.append(window)
            except Exception as issue:
                qt.QMessageBox.warning(self, 'Cannot open reader', str(issue))

    def _reader_finished(self):
        self.reader_busy = False
        self.reader_operation.deleteLater()

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
        self.file_browser.refresh_item(path)

    def closeEvent(self, event):
        if self.reader_busy or any(window.busy for window in self.metadata_windows):
            event.ignore()
            return
        for window in list(self.metadata_windows):
            if window.isVisible():
                window.reject()
                if window.isVisible():
                    event.ignore()
                    return
        if self.file_browser.stop():
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
