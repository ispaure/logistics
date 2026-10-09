"""Reader, metadata and compression services shared by Logistics browser hosts."""

from pathlib import Path

from commonUtils.ui import pyside as qt
from features.comics.pages import ComicPages
from features.comics.reader import open_reader
from features.comics.selection import normalize_targets
from .metadata_editor import MetadataEditor
from commonUtils.ui.operations import Operation
from services.zip_passwords import is_password_error
from ui_new.dialogs.archive_password import ask_password


class ComicBrowserServices:
    """Host supplies widgets, suggestions, metadata refresh and close state."""

    def _compress(self, targets):
        from .dialogs import CompressCbzDialog
        dialog = CompressCbzDialog(parent=self.browser_host, targets=targets)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()
            self.file_browser.refresh()

    def _read(self, path, *, password=None):
        if self.reader_busy or self.close_after_catalog:
            return
        self.reader_busy = True
        self._reading_path = Path(path)
        self._reader_password_retry = None
        self.reader_operation = Operation(lambda: ComicPages(path) if password is None else ComicPages(path, password=password), self)
        self.reader_operation.completed.connect(self._reader_opened)
        self.reader_operation.finished.connect(self._reader_finished)
        self.reader_operation.start()

    def _reader_opened(self, result, error):
        if error:
            if self.close_after_catalog:
                return
            if is_password_error(error) and not self.close_after_catalog:
                password = ask_password(self._reading_path, error, self.browser_host)
                if password is not None:
                    self._reader_password_retry = (self._reading_path, password)
            else:
                qt.QMessageBox.warning(self.browser_host, 'Cannot open reader', error)
        else:
            try:
                window = open_reader(result)
                if not self.close_after_catalog and getattr(getattr(result, 'document', None), 'password', None) is not None:
                    self.file_browser.refresh_item(result.path)
                if isinstance(window, qt.QMainWindow) and window not in self.reader_connections:
                    window.metadata_saved.connect(self._metadata_saved)
                    window.closed.connect(self._return_to_library)
                    self.reader_connections.append(window)
                    window.destroyed.connect(lambda: self._reader_closed(window))
            except Exception as issue:
                qt.QMessageBox.warning(self.browser_host, 'Cannot open reader', str(issue))

    def _return_to_library(self):
        # Restore focus after Qt has finished hiding the reader.
        qt.QTimer.singleShot(0, self._activate_library)

    def _activate_library(self):
        if self.browser_host.isVisible() and not self.close_after_catalog:
            self.browser_host.raise_()
            self.browser_host.activateWindow()

    def _reader_closed(self, window):
        if window in self.reader_connections:
            self.reader_connections.remove(window)

    def _reader_finished(self):
        self.reader_busy = False
        self.reader_operation.deleteLater()
        retry = getattr(self, '_reader_password_retry', None)
        self._reader_password_retry = None
        if retry is not None and not self.close_after_catalog:
            path, password = retry
            qt.QTimer.singleShot(0, lambda: self._read(path, password=password))

    def _open_editor(self, path, index=None):
        from ui_new.documents import show_document, document_is_open
        targets = normalize_targets(path)
        path = targets[0]
        existing = next((window for window in self.metadata_windows
                         if set(window.targets) == set(targets) and document_is_open(window)), None)
        if existing is not None:
            show_document(existing)
            return existing
        for window in list(self.metadata_windows):
            if not document_is_open(window) and not window.busy:
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
        window = MetadataEditor(targets, siblings, self.browser_host)
        window.tabs.set_suggestions(self.suggestions)
        self.suggestions_changed.connect(window.tabs.set_suggestions)
        self.metadata_windows.append(window)
        window.saved.connect(self._metadata_saved)
        show_document(window)
        return window
