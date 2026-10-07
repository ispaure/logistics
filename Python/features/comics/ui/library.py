"""Comics library controls and domain services around the reusable file browser."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from features import registry
from features.comics.catalog import LibraryCatalog
from features.comics.library_config import configured_libraries
from .operations import Operation
from .browser_services import ComicBrowserServices


class ComicLibraryWindow(qt.QMainWindow, ComicBrowserServices):
    suggestions_changed = qt.Signal(object)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.browser_host = self
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
        self.library_tabs = qt.QTabBar()
        self.library_tabs.setAccessibleName('Comics libraries')
        self.library_tabs.setExpanding(False)
        self.library_tabs.setUsesScrollButtons(True)
        layout.addWidget(self.library_tabs)
        self.library_status = qt.QLabel()
        self.library_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.library_status)
        self.catalog_status = qt.QLabel()
        self.catalog_status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.catalog_status.hide()
        layout.addWidget(self.catalog_status)
        self.file_browser = FileBrowser(parent=self)
        definition = registry.get_feature_definition('comics')
        self.feature_binding = definition.install_browser(self.file_browser, host=self, controller=self)
        self.feature_binding.set_enabled(registry.is_feature_enabled('comics'))
        self.archive_binding = registry.get_feature_definition('archives').install_browser(self.file_browser, host=self)
        self.archive_binding.set_enabled(registry.is_feature_enabled('archives'))
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
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
        self.library_tabs.addTab('All')
        self.library_tabs.setTabData(0, self.root_path)
        self.library_tabs.setTabToolTip(0, str(self.root_path))
        self.library_tabs.setTabEnabled(0, bool(self.libraries) and self.root_path.is_dir())
        for name, path in self.libraries:
            if path == self.root_path:
                continue
            index = self.library_tabs.addTab(name)
            self.library_tabs.setTabData(index, path)
            self.library_tabs.setTabEnabled(index, path.is_dir())
            self.library_tabs.setTabToolTip(index, str(path) if path.is_dir() else f'Folder not found: {path}')
        initial = 0 if self.library_tabs.isTabEnabled(0) else -1
        self.library_tabs.setCurrentIndex(initial)
        self.library_tabs.currentChanged.connect(self._library_changed)
        self._library_changed(initial)
        self._refresh_catalog()

    def _features_changed(self):
        self._sync_feature()

    def _sync_feature(self):
        if self.close_after_catalog or self.file_browser.stopping:
            return
        enabled = registry.is_feature_enabled('comics')
        self.feature_binding.set_enabled(enabled)
        self.archive_binding.set_enabled(registry.is_feature_enabled('archives'))
        self.file_browser.refresh()
        self.setWindowTitle(f'Comics — {self.root_path.name}' + ('' if enabled else ' (disabled)'))

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
        path = self.library_tabs.tabData(index) if index >= 0 else None
        available = index >= 0 and self.library_tabs.isTabEnabled(index) and path is not None and path.is_dir()
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

    def _refresh_catalog(self):
        if not registry.is_feature_enabled('comics'):
            return
        if self.catalog_busy:
            self.catalog_pending = True
            return
        self.catalog_busy = True
        self.catalog_pending = False
        self.catalog_status.hide()
        self.catalog_operation = Operation(
            lambda: self.catalog.refresh(self.catalog_operation.isInterruptionRequested), self)
        self.catalog_operation.completed.connect(self._catalog_loaded)
        self.catalog_operation.finished.connect(self._catalog_finished)
        self.catalog_operation.start()

    def _catalog_loaded(self, result, error):
        if error:
            self.catalog_status.show()
            self.catalog_status.setText('Library suggestions could not be updated; manual entry is available.')
            self.catalog_status.setToolTip(error)
        elif result is not None:
            self.suggestions = result['suggestions']
            self.suggestions_changed.emit(self.suggestions)
            self.catalog_status.setVisible(bool(result['errors']))
            self.catalog_status.setText(f"{len(result['errors'])} indexing issue(s)")
            self.catalog_status.setToolTip('\n'.join(result['errors']))

    def _catalog_finished(self):
        self.catalog_busy = False
        self.catalog_operation.deleteLater()
        if self.close_after_catalog:
            self.close()
        elif self.catalog_pending:
            self._refresh_catalog()

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
