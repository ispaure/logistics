"""General browser host enriched by available Logistics feature contributions."""

from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from features import registry


class FileBrowserWindow(qt.QMainWindow):
    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'File Browser — {Path(root_path).name}')
        self.resize(1200, 800)
        self.closing = False
        self.file_browser = FileBrowser(parent=self)
        self.setCentralWidget(self.file_browser)
        self.extensions = []
        self._extensions_by_feature = {}
        self._sync_extensions()
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.file_browser.idle.connect(self._retry_close)
        self.file_browser.set_directory(root_path)

    def _features_changed(self):
        self._sync_extensions()

    def _sync_extensions(self):
        if self.closing:
            return
        active = set()
        for registered in registry.get_browser_extensions():
            name = registered.feature_name
            active.add(name)
            if name not in self._extensions_by_feature:
                extension = registered.contribution.install(self)
                self.extensions.append(extension)
                self._extensions_by_feature[name] = extension
                extension.idle.connect(self._retry_close)
            binding = self._extensions_by_feature[name]
            if hasattr(binding, 'set_enabled'):
                binding.set_enabled(True)
            else:
                self.file_browser.set_extension_enabled(name, True)
        for name in self._extensions_by_feature.keys() - active:
            # Retain controllers so existing readers/editors/workers can finish.
            binding = self._extensions_by_feature[name]
            if hasattr(binding, 'set_enabled'):
                binding.set_enabled(False)
            else:
                self.file_browser.set_extension_enabled(name, False)
        if self.file_browser.navigation.library is not None:
            self.file_browser.refresh()

    def _retry_close(self):
        if self.closing:
            self.close()

    def closeEvent(self, event):
        self.closing = True
        ready = True
        for extension in self.extensions:
            if not extension.prepare_close():
                ready = False
        if not ready or self.file_browser.stop():
            event.ignore()
            return
        event.accept()


_windows = []


def open_file_browser(parent=None):
    root_path = qt.QFileDialog.getExistingDirectory(parent, 'Open File Browser', str(Path.home()))
    if not root_path:
        return None
    window = FileBrowserWindow(root_path, parent)
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    window.show()
    return window
