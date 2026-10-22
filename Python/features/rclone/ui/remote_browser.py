"""Read-only remote tabs hosted alongside Local and LocalCrypt browser tabs."""
from dataclasses import dataclass
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.resource_browser import ResourceBrowser
from commonUtils.ui.tasks.operation_progress import OperationProgress
from features.rclone.remote_policy import direct_kind, LOCAL_COPY_MESSAGE, TEXT_LIMIT


@dataclass(frozen=True)
class RemoteLocation:
    config: Path
    remote: str
    directory: str = ''


class RemoteBrowser(ResourceBrowser):
    def _filter(self, *_):
        # Only filter entries already listed; never start the recursive scanner.
        self.search_timer.stop()
        self.search_pending = False
        self.search_timer.start()

    def _start_search(self):
        if self.closing:
            return
        self.model.set_filter(self.filter.text().strip(), self.navigation.directory)
        self.views.set_root(self.navigation.directory)


class RemoteBrowserView(qt.QMainWindow):
    title_changed = qt.Signal(str)
    idle = qt.Signal()
    close_in_background = True

    def __init__(self, location, parent=None):
        super().__init__(parent)
        from features.rclone import executable
        from features.rclone.remote_resources import RemoteResources
        binary = executable.ensure_rclone()
        if not binary:
            raise ValueError('The rclone executable is required to browse remotes.')
        self.location, self.closing = location, False
        self.extensions, self._extensions_by_feature = [], {}
        self.provider = RemoteResources(location.config, location.remote, binary=binary)
        self._release = self.provider.acquire()
        self.destroyed.connect(self._release)
        content = qt.QWidget(self)
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(content)
        self.file_browser = RemoteBrowser(self.provider, self,
            directory=self.provider.root / location.directory,
            thumbnail=self._thumbnail, details=self._details)
        self.file_browser.filter.setPlaceholderText('Search this folder')
        self.file_browser.notice.setText('Remote · Read-only · Previews stay in memory')
        self.workspace_controls = self.file_browser.workspace_controls
        self.folder_sizes = qt.QCheckBox('Background indexing')
        self.folder_sizes.setEnabled(False)
        self.folder_sizes.hide()
        self.file_browser.activated.connect(self.open_document)
        self.file_browser.directory_changed.connect(lambda *_: self.title_changed.emit(self.view_title))
        self.file_browser.idle.connect(self.idle)
        from desktop.location_context import install_browser_location
        install_browser_location(self.file_browser, self.provider)
        self.operation = OperationProgress(self)
        self.operation.completed.connect(self._completed)
        layout.addWidget(self.file_browser)
        layout.addWidget(self.operation)
        self.menuBar().setNativeMenuBar(False)
        menu = self.menuBar().addMenu('File')
        menu.addAction('Open Remote…', lambda: choose_remote(self))
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(self, self.provider)
        self._private_view_guard.revoked.connect(self.file_browser.storage_location.refresh)

    @property
    def view_title(self):
        directory = self.provider.relative(self.file_browser.navigation.directory)
        return f'Remote — {self.location.config.stem} / {self.location.remote}' + (f' / {directory}' if directory else '')

    def _thumbnail(self, relative, size, cancelled):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        return CryptBrowserView._thumbnail(self, relative, size, cancelled)

    def _details(self, row, cancelled):
        from features.rclone.localcrypt.ui.views import CryptBrowserView
        return CryptBrowserView._details(self, row, cancelled)

    def open_document(self, path):
        if self.closing or self.operation.busy:
            return
        suffix = Path(path).suffix.lower()
        if suffix in {'.pdf', '.epub', '.cbz', '.zip'}:
            from commonUtils.runtime.resource_selection import ResourceChoice
            from services.documents.ui.readers import open_reader_choice
            open_reader_choice(ResourceChoice(self.provider, self.provider.relative(path), self.provider.acquire()),
                               self, 'pdf' if suffix == '.pdf' else 'epub' if suffix == '.epub' else 'comic')
            return
        def read(report, cancelled):
            with self.provider.operation(cancelled):
                kind = direct_kind(path, self.provider.stat(path)['Size'])
                return 'document', path, kind, self.provider.read_bytes(path, limit=TEXT_LIMIT if kind == 'text' else self.provider.max_resource)
        self.operation.start(read, message='Opening remote file…')

    def _completed(self, result, error):
        if not self.closing and not self.operation.cancelled.is_set():
            if error:
                message = error if LOCAL_COPY_MESSAGE in error else error + '\n\n' + LOCAL_COPY_MESSAGE
                qt.QMessageBox.information(self, 'Remote file', message)
            elif result:
                _, path, kind, data = result
                window = qt.QMainWindow()
                window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
                window.setWindowTitle('Remote — ' + Path(path).name + ' (read-only)')
                window.document_resource_path = path
                window.resize(900, 700)
                if kind == 'text':
                    view = qt.QPlainTextEdit()
                    view.setReadOnly(True)
                    view.setPlainText(data.decode('utf-8-sig', errors='replace'))
                else:
                    pixmap = qt.QPixmap()
                    if not pixmap.loadFromData(data):
                        qt.QMessageBox.information(self, 'Remote file', LOCAL_COPY_MESSAGE)
                        return
                    view = qt.QLabel()
                    view.setPixmap(pixmap)
                    scroll = qt.QScrollArea()
                    scroll.setWidget(view)
                    view = scroll
                window.setCentralWidget(view)
                release = self.provider.acquire()
                window.destroyed.connect(release)
                from services.documents.ui.private_views import protect_private_view
                from services.documents.ui.editors import retain
                protect_private_view(window, self.provider)
                retain(window)
                window.show()
        self.idle.emit()

    def prepare_close(self):
        self.closing = True
        self.operation.request_cancel()
        browser_busy = self.file_browser.stop()
        ready = not browser_busy and not self.operation.busy
        if ready:
            self._release()
        return ready


def _workspace(parent):
    while parent is not None:
        workspace = getattr(parent, 'workspace', None)
        if workspace is not None and hasattr(workspace, 'add_view'):
            return workspace
        parent = parent.parentWidget()


def open_remote(config, remote, parent=None, directory='', *, package=None):
    location = RemoteLocation(Path(config), remote, directory)
    parent = parent or qt.QApplication.activeWindow()
    # Workspaces owns an inline unlock route; standalone tabs keep their dialog.
    host = parent
    while host is not None:
        opener = getattr(host, 'open_browser_location', None)
        if callable(opener):
            return opener(location, package=package)
        host = host.parentWidget()
    from features.rclone.localcrypt.ui.views import ensure_session
    if not ensure_session(config, package=package, parent=parent):
        return
    workspace = _workspace(parent)
    try:
        if workspace is not None:
            return workspace.add_view(location)
        from desktop.file_browser import FileBrowserWindow, _windows
        window = FileBrowserWindow(location, parent)
        _windows.append(window)
        window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
        window.show()
        return window
    except Exception as error:
        qt.QMessageBox.warning(parent, 'Open Remote', str(error))


def choose_remote(parent=None):
    from features.rclone import credentials, configuration
    choices = {}
    for config in credentials.get_loaded_credential_config_paths():
        for remote in configuration.get_rclone_remote_names(config):
            choices[f'{config.stem} / {remote} ({config.suffix[1:]})'] = config, remote
    if not choices:
        qt.QMessageBox.information(parent, 'Open Remote', 'Load a credential package in rclone settings first.')
        return
    selected, accepted = qt.QInputDialog.getItem(parent, 'Open Remote', 'Account / remote', list(choices), 0, False)
    if accepted:
        return open_remote(*choices[selected], parent=parent)
