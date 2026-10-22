"""General browser host enriched by available Logistics feature contributions."""

from commonUtils.ui.appearance.typography import point_size, setting_size
from dataclasses import dataclass, replace
from pathlib import Path
from functools import lru_cache
import time
import sys
from commonUtils.ui import pyside as qt
from commonUtils.ui.file_browser import FileBrowser
from features import registry
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy
from commonUtils.ui.file_browser.status import WorkspaceIndexStatus


class BrowserIndexStatus(WorkspaceIndexStatus):
    """Logistics' compact footer, retaining the shared indexing controller."""
    def __init__(self, workspace):
        super().__init__(workspace)
        content = self.label.parentWidget()
        content.layout().setContentsMargins(0, 0, 0, 0)
        content.layout().setSpacing(6)
        font = self.label.font()
        font.setItalic(False)
        font.setPointSizeF(point_size(max(7.0, setting_size(font) - .75)))
        self.label.setFont(font)
        self.activity.setFixedSize(100, 6)
        for button in (self.refresh_button, self.details_button):
            button.setFont(font)
            button.setStyleSheet('QPushButton { min-height: 0px; padding: 2px 6px; }')

BROWSER_POLICY = WorkspacePolicy(allow_last_tab_detach=False,
                                 show_single_tab_in_main=True,
                                 show_single_tab_in_detached=False,
                                 detached_title='{title} — File Browser')


@lru_cache(maxsize=8)
def _crypt_copies(root, record_revision, interval):
    # Model callbacks are frequent. Refresh on publication and at least once a
    # second for external record edits; cache identities, never decoded names.
    from features.rclone.localcrypt.backend import connections
    return tuple(connections(root))


def _crypt_location(path, *, root=None):
    """Resolve raw paths/aliases only at the host's provider boundary."""
    from features.rclone.localcrypt.backend import storage_root
    path = Path(path).absolute()
    configured_root = Path(root if root is not None else storage_root()).absolute()
    root = configured_root.resolve()
    resolved = path.resolve()
    if resolved == root:
        return None, False
    try:
        revision = (configured_root / '.connections').stat().st_mtime_ns
    except FileNotFoundError:
        revision = None
    copies = _crypt_copies(configured_root, revision, int(time.monotonic()))
    for item in copies:
        target = item.data.resolve()
        if resolved == target or target in resolved.parents:
            return item, True
    if root not in resolved.parents and configured_root not in path.parents:
        return None, False
    # Schema-1 package containers are navigable to their mapped copy roots.
    if any(resolved in item.data.resolve().parents for item in copies):
        return None, False
    return None, True


@dataclass(frozen=True)
class _PrivateBrowserLocation:
    item: object
    directory: Path


def _browser_view(path=None, *, root_path=None, filesystem_scope=False):
    from services.local_storage import install_local_storage_policy
    install_local_storage_policy()
    initial = path or root_path or Path.home()
    from features.rclone.ui.remote_browser import RemoteLocation, RemoteBrowserView
    if isinstance(initial, RemoteLocation):
        return RemoteBrowserView(initial)
    if isinstance(initial, _PrivateBrowserLocation):
        from features.rclone.localcrypt.ui.views import CryptBrowserView, ensure_session
        if not ensure_session(initial.item.context, package=initial.item.package, parent=qt.QApplication.activeWindow()):
            return None
        return CryptBrowserView(initial.item, directory=initial.directory)
    item, _managed = _crypt_location(initial)
    if item is not None:
        from features.rclone.localcrypt.ui.views import CryptBrowserView, ensure_session
        if not ensure_session(item.context, package=item.package, parent=qt.QApplication.activeWindow()):
            return None
        return CryptBrowserView(item, directory=item.data)
    return BrowserView(root_path=initial, filesystem_scope=filesystem_scope)


def _new_browser_tab(workspace):
    active = workspace.active_view
    browser = getattr(active, 'file_browser', None)
    from features.rclone.ui.remote_browser import RemoteLocation
    if isinstance(getattr(active, 'location', None), RemoteLocation):
        return workspace.add_view(replace(active.location,
            directory=active.provider.relative(browser.navigation.directory)))
    if getattr(active, 'item', None) is not None:
        return workspace.add_view(_PrivateBrowserLocation(active.item,
            browser.navigation.directory if browser else active.item.data))
    return workspace.add_view(browser.navigation.directory if browser else Path.home())


def _browser_container(workspace):
    workspace.index_status = BrowserIndexStatus(workspace)


class _BrowserHost:
    """Shared feature installation and worker-safe shutdown for embedded/standalone hosts."""
    def _initialize_browser(self, root_path, *, calculate_folder_sizes=True, filesystem_scope=False):
        self.closing = False
        self.filesystem_scope = filesystem_scope
        from desktop.bulk_rename import bulk_rename_actions
        self.file_browser = FileBrowser(parent=self, action_providers=(bulk_rename_actions,),
                                       directory_handler=self._route_directory,
                                       directory_boundary=self._directory_boundary,
                                       calculate_folder_sizes=calculate_folder_sizes,
                                       index_settings_path=Path(__file__).resolve().parents[1]/'configFile.ini')
        self.extensions = []
        self._extensions_by_feature = {}
        self._sync_extensions()
        self._unsubscribe = registry.subscribe(self._features_changed)
        self.destroyed.connect(self._unsubscribe)
        self.file_browser.idle.connect(self._retry_close)
        self._open_location(root_path)

    def _directory_boundary(self, path):
        # Qt asks rowCount repeatedly while painting. Do not reread application
        # settings or resolve the same path for every query. Actual navigation
        # always uses the fresh resolver below.
        interval = int(time.monotonic())
        if getattr(self, '_boundary_interval', None) != interval:
            from features.rclone.localcrypt.backend import storage_root
            self._boundary_interval = interval
            self._boundary_root = storage_root()
            self._boundary_paths = {}
        if path not in self._boundary_paths:
            if len(self._boundary_paths) >= 1024:
                self._boundary_paths.clear()
            self._boundary_paths[path] = _crypt_location(path, root=self._boundary_root)[1]
        return self._boundary_paths[path]

    def _route_directory(self, path):
        item, managed = _crypt_location(path)
        if not managed:
            return False
        if self.closing or getattr(self, '_crypt_route_pending', False):
            return True
        self._crypt_route_pending = True
        def open_copy():
            try:
                if self.closing:
                    return
                if item is None:
                    raise ValueError('This LocalCrypt folder has no valid credential mapping. Open a mapped copy or pull it again.')
                from features.rclone.localcrypt.ui.views import ensure_session
                if not ensure_session(item.context, package=item.package, parent=self):
                    return
                from commonUtils.ui.workspaces.workspace import WorkspaceDock
                parent = self.parentWidget()
                while parent is not None and not isinstance(parent, WorkspaceDock):
                    parent = parent.parentWidget()
                if parent is not None:
                    workspace = parent.workspace
                    for dock in workspace.docks:
                        if getattr(dock.widget(), 'item', None) == item:
                            dock.show()
                            dock.raise_()
                            workspace._activate(dock)
                            return
                    if workspace.add_view(item.data) is not None:
                        return
                host = self.parentWidget()
                while host is not None:
                    opener = getattr(host, 'open_browser_location', None)
                    if callable(opener):
                        opener(_PrivateBrowserLocation(item, item.data))
                        return
                    host = host.parentWidget()
                from features.rclone.localcrypt.ui.views import open_browser
                open_browser(item, self)
            except Exception as error:
                qt.QMessageBox.warning(self, 'Cannot open LocalCrypt', str(error))
            finally:
                self._crypt_route_pending = False
        qt.QTimer.singleShot(0, self, open_copy)
        return True

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
        self.can_retire = ready
        browser_busy = self.file_browser.stop()
        return ready and not browser_busy

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()


class BrowserView(_BrowserHost, qt.QMainWindow):
    close_in_background = True
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
        self.file_browser.setObjectName('logisticsBrowser')
        self.file_browser.setStyleSheet('''
            QWidget#logisticsBrowser QTreeView::item,
            QWidget#logisticsBrowser QTreeView::item:hover,
            QWidget#logisticsBrowser QTreeView::item:selected { padding: 2px 4px; }
            QWidget#logisticsBrowser QHeaderView::section { padding: 2px 4px; }
            QWidget#logisticsBrowser QTabBar::tab { padding: 4px 16px; }
        ''')
        content = qt.QWidget(self)
        self.setCentralWidget(content)
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.drive_selector = None
        if filesystem_scope and sys.platform == 'win32':
            self.file_browser.navigation.breadcrumbs.enable_drive_menu(self._open_location)
        self.folder_sizes = qt.QCheckBox('Background indexing', self)
        self.folder_sizes.setToolTip('Pause or resume this tab’s indexing subscription. Cached search and sizes stay available; other tabs may continue indexing.')
        self.folder_sizes.setChecked(True)
        self.folder_sizes.toggled.connect(self.file_browser.set_folder_sizes_enabled)
        self.folder_sizes.hide()  # Legacy API; the browser toolbar now offers Pause/Resume.
        layout.addWidget(self.file_browser, 1)
        self.workspace_controls = self.file_browser.workspace_controls
        self.file_browser.views.directory_changed.connect(lambda path: self.title_changed.emit(self.view_title))
        self.file_browser.idle.connect(self.idle)
        from .browser_menus import BrowserMenus
        self.header_menus = BrowserMenus(self)
        from desktop.location_context import install_browser_location
        install_browser_location(self.file_browser)

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
        self.workspace = Workspace(lambda path: _browser_view(
            root_path=path or root_path or Path.home(),
            filesystem_scope=root_path is None and (path is None or not self.workspace.all_docks)), self,
            keep_one_tab=True, policy=BROWSER_POLICY, new_view=_new_browser_tab,
            setup_container=_browser_container)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.workspace)
        self.index_status = BrowserIndexStatus(self.workspace)
        self.workspace.add_view(root_path or Path.home())


class FileBrowserWindow(_WorkspaceHost, qt.QMainWindow):
    def __init__(self, root_path, parent=None, *, allow_new_tabs=True):
        super().__init__(parent)
        self.setWindowFlag(qt.Qt.WindowType.Window, True)
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('File Browser')
        self.resize(1200, 800)
        self.workspace_publish_menus = True
        self.workspace = Workspace(lambda path: _browser_view(root_path=path or root_path), self,
                                   keep_one_tab=True, allow_new_tabs=allow_new_tabs,
                                   policy=replace(BROWSER_POLICY, max_tabs=None if allow_new_tabs else 1),
                                   new_view=_new_browser_tab, setup_container=_browser_container)
        self.workspace.active_changed.connect(self._update_title)
        self.workspace_menu_document = lambda: self.workspace.active_view
        self.workspace.tabs_changed.connect(self._update_title)
        self.setCentralWidget(self.workspace)
        self.index_status = BrowserIndexStatus(self.workspace)
        view = self.workspace.add_view(root_path)
        if view.file_browser is not None and getattr(view.file_browser, 'persistent_index', True):
            view.folder_sizes.setChecked(True)

    def _update_title(self, *args):
        view = self.workspace.active_view
        title = view.view_title if view else ''
        private = title.startswith('🕵️ Private - ')
        self.setWindowTitle(('🕵️ Private - ' if private else '') + 'File Browser' +
                            (f': {title.removeprefix("🕵️ Private - ")}' if title else ''))


_windows = []


def open_file_browser(parent=None, *, allow_new_tabs=True):
    root_path = qt.QFileDialog.getExistingDirectory(parent, 'Open File Browser', str(Path.home()))
    if not root_path:
        return None
    window = FileBrowserWindow(root_path, parent, allow_new_tabs=allow_new_tabs)
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    window.show()
    return window
