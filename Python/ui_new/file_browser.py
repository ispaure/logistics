"""General browser host enriched by available Logistics feature contributions."""

from pathlib import Path
import sys
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from features import registry
from commonUtils.ui.workspace import Workspace
from commonUtils.ui.file_browser.status import WorkspaceIndexStatus


class _BrowserHost:
    """Shared feature installation and worker-safe shutdown for embedded/standalone hosts."""
    def _initialize_browser(self, root_path, *, calculate_folder_sizes=True, filesystem_scope=False):
        self.closing = False
        self.filesystem_scope = filesystem_scope
        from ui_new.bulk_rename import bulk_rename_actions
        self.file_browser = FileBrowser(parent=self, action_providers=(bulk_rename_actions,),
                                       calculate_folder_sizes=calculate_folder_sizes)
        self.extensions = []
        self._extensions_by_feature = {}
        self._sync_extensions()
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.file_browser.idle.connect(self._retry_close)
        self._open_location(root_path)

    def _open_location(self, path):
        path = Path(path).absolute()
        root = Path(path.anchor) if self.filesystem_scope else None
        self.file_browser.set_directory(path, navigation_root=root)
        selector = getattr(self, 'drive_selector', None)
        if selector is not None:
            with qt.QSignalBlocker(selector):
                selector.setCurrentIndex(selector.findData(str(root)))

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
            self.window().close()

    def prepare_close(self):
        self.closing = True
        ready = True
        for extension in self.extensions:
            if not extension.prepare_close():
                ready = False
        browser_busy = self.file_browser.stop()
        return ready and not browser_busy

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()


class BrowserView(_BrowserHost, qt.QWidget):
    title_changed = qt.Signal(str)
    idle = qt.Signal()
    def __init__(self, parent=None, *, root_path=None, filesystem_scope=False):
        super().__init__(parent)
        initial = Path(root_path or Path.home())
        if filesystem_scope and sys.platform == 'win32':
            drive = Path('C:/')
            if drive.is_dir() and initial.anchor.casefold() != drive.anchor.casefold():
                initial = drive
        self._initialize_browser(initial, calculate_folder_sizes=True, filesystem_scope=filesystem_scope)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.drive_selector = None
        if filesystem_scope and sys.platform == 'win32':
            controls = qt.QHBoxLayout()
            self.drive_selector = qt.QComboBox()
            self.drive_selector.setAccessibleName('Browse drive')
            self.drive_selector.setToolTip('Choose the drive to browse')
            for info in qt.QDir.drives():
                path = info.absoluteFilePath()
                self.drive_selector.addItem(path, str(Path(path)))
            self.drive_selector.setCurrentIndex(self.drive_selector.findData(str(Path(initial.anchor))))
            self.drive_selector.currentIndexChanged.connect(lambda index: self._open_location(
                self.drive_selector.itemData(index)) if index >= 0 else None)
            controls.addWidget(self.drive_selector)
            controls.addStretch()
            layout.addLayout(controls)
        self.folder_sizes = qt.QCheckBox('Background indexing', self)
        self.folder_sizes.setToolTip('Pause or resume this tab’s indexing subscription. Cached search and sizes stay available; other tabs may continue indexing.')
        self.folder_sizes.setChecked(True)
        self.folder_sizes.toggled.connect(self.file_browser.set_folder_sizes_enabled)
        self.folder_sizes.hide()  # Legacy API; the browser toolbar now offers Pause/Resume.
        layout.addWidget(self.file_browser, 1)
        self.file_browser.views.directory_changed.connect(lambda path: self.title_changed.emit(self.view_title))
        self.file_browser.idle.connect(self.idle)

    @property
    def view_title(self):
        path = self.file_browser.navigation.directory
        return (path.name or str(path)) if path else 'Files'

    def _retry_close(self):
        if self.closing:
            self.idle.emit()


class _WorkspaceHost:
    @property
    def closing(self):
        return self.workspace._closing

    @property
    def file_browser(self):
        return self.workspace.active_view.file_browser

    @property
    def extensions(self):
        return self.workspace.active_view.extensions

    @property
    def _extensions_by_feature(self):
        return self.workspace.active_view._extensions_by_feature

    @property
    def folder_sizes(self):
        return self.workspace.active_view.folder_sizes

    def prepare_close(self):
        return self.workspace.prepare_close()

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()


class FileBrowserPage(_WorkspaceHost, qt.QWidget):
    def __init__(self, parent=None, *, root_path=None):
        super().__init__(parent)
        self.workspace = Workspace(lambda path: BrowserView(root_path=path or (
            self.file_browser.navigation.directory if self.workspace.active_view else root_path or Path.home()),
            filesystem_scope=root_path is None and not self.workspace.docks), self)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.workspace)
        self.index_status = WorkspaceIndexStatus(self.workspace)
        self.workspace.add_view(root_path or Path.home())


class FileBrowserWindow(_WorkspaceHost, qt.QMainWindow):
    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f'File Browser — {Path(root_path).name}')
        self.resize(1200, 800)
        self.workspace = Workspace(lambda path: BrowserView(root_path=path or (
            self.file_browser.navigation.directory if self.workspace.active_view else root_path)), self)
        self.workspace.active_changed.connect(lambda view: self.setWindowTitle(
            f'File Browser — {view.view_title}' if view else 'File Browser'))
        self.setCentralWidget(self.workspace)
        self.index_status = WorkspaceIndexStatus(self.workspace)
        view = self.workspace.add_view(root_path)
        view.folder_sizes.setChecked(True)


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
