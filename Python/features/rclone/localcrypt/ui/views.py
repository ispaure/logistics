"""Session unlock, provider-backed browsing and existing private document hosts."""
from pathlib import Path

from commonUtils.ui import pyside as qt
from commonUtils.ui.resources.browser import ResourceBrowser
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.ui.document_host import show_document
from features.rclone import session, executable
from features.rclone.desktop_service import service

_windows = []


def ensure_session(config_path, *, package=None, parent=None):
    path = Path(config_path)
    if path.suffix != '.session':
        return True
    if session.credentials(path) is not None and (package is None or session.package_path(path) == Path(package)):
        return True
    package = Path(package) if package else session.package_path(path)
    if package is None:
        qt.QMessageBox.warning(parent, 'Unlock credentials', 'Select and unlock the matching credential ZIP in Settings first.')
        return False
    from desktop.dialogs.archive_password import ask_validated_password
    from features.rclone.desktop_credentials import DesktopCredentialLoad
    values = ask_validated_password(package, 'Unlock the crypt settings and cloud credentials in this ZIP.',
                                    lambda password: service.credentials.prepare_load(DesktopCredentialLoad(package, path), password), parent)
    if values is None:
        return False
    try:
        service.credentials.unlock(values)
    except ValueError:
        qt.QMessageBox.warning(parent, 'Unlock credentials', 'Credentials changed while loading. Try again.')
        return False
    return True


from services.documents.ui.markdown import MarkdownStorage, PrivateMarkdownWindow, choose_destination
from services.documents.markdown import prepare_markdown


class CryptBrowserView(qt.QMainWindow):
    title_changed = qt.Signal(str)
    idle = qt.Signal()
    close_in_background = True
    def __init__(self, item, parent=None, *, directory=None):
        super().__init__(parent)
        self.closing = False
        self.extensions = []
        self._extensions_by_feature = {}
        self.provider = None
        self.file_browser = None
        self.item = item
        content = qt.QWidget(self)
        layout = qt.QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(content)
        self.open_operation = OperationProgress(self)
        self.open_operation.completed.connect(self._opened)
        self.provider = service.localcrypt.open(item) if ensure_session(item.context, package=item.package, parent=self) else None
        # Cancellation leaves a locked browser with an explicit retry button.
        if self.provider is None:
            self.retry = qt.QPushButton('Unlock credential ZIP', self)
            self.retry.clicked.connect(self._unlock)
            layout.addWidget(self.retry)
            self.file_browser = None
            self.workspace_controls = qt.QHBoxLayout()
            self.folder_sizes = qt.QCheckBox()
            return
        self._install_browser(directory)

    def _unlock(self):
        if ensure_session(self.item.context, package=self.item.package, parent=self):
            try:
                self.provider = service.localcrypt.open(self.item)
                self.retry.hide()
                self._install_browser(None)
                self.title_changed.emit(self.view_title)
            except Exception:
                qt.QMessageBox.warning(self, 'Encrypted copy', 'The local crypt view could not be opened.')

    def _install_browser(self, directory):
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(self, self.provider)
        self._release_provider = self.provider.acquire()
        self.destroyed.connect(self._release_provider)
        self.file_browser = ResourceBrowser(self.provider, self, directory=directory, thumbnail=self._thumbnail, details=self._details, actions=(
            ('Move to…', lambda row: True, self.move_item),
            ('Edit comic metadata…', lambda row: row['directory'] or Path(row['path']).suffix.lower() in {'.cbz', '.zip'}, self.edit_metadata),
            ('Edit EPUB metadata…', lambda row: not row['directory'] and Path(row['path']).suffix.lower() == '.epub', self.edit_epub_metadata),))
        self.centralWidget().layout().addWidget(self.file_browser)
        self.centralWidget().layout().addWidget(self.open_operation)
        self.file_browser.activated.connect(self.open_document)
        self.file_browser.directory_changed.connect(lambda path: self.title_changed.emit(self.view_title))
        self.file_browser.idle.connect(self.idle)
        from desktop.location_context import install_browser_location
        install_browser_location(self.file_browser, self.provider)
        from features.application import registry
        self.notes_offer = None
        if registry.is_feature_enabled('text_editor'):
            from features.text_editor.ui.notes_offer import NotesFolderOffer
            self.notes_offer = NotesFolderOffer(self.file_browser)
            self.notes_offer.progress.completed.connect(lambda *args: self.idle.emit())
        self._private_view_guard.revoked.connect(self.file_browser.storage_location.refresh)
        self.workspace_controls = self.file_browser.workspace_controls
        from commonUtils.ui.file_browser.controls import navigation_button
        self.import_button = navigation_button(self, 'Move into this folder…', qt.QStyle.StandardPixmap.SP_DialogOpenButton)
        import_menu = qt.QMenu(self.import_button)
        for label, folder in (('Move file into this folder…', False), ('Move folder into this folder…', True)):
            import_menu.addAction(label, lambda checked=False, folder=folder: self.import_item(folder))
        self.import_button.setMenu(import_menu)
        self.import_button.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.workspace_controls.addWidget(self.import_button)
        self.folder_sizes = qt.QCheckBox('Background indexing')
        self.folder_sizes.setEnabled(False)
        self.folder_sizes.hide()
        self.menuBar().addMenu('File').addAction('Close', self._close_tab, qt.QKeySequence(qt.QKeySequence.StandardKey.Close))
        qt.QApplication.instance().aboutToQuit.connect(self.provider.close)

    def _thumbnail(self, relative, size, cancelled):
        """Domain previews read through the active provider and stay in RAM."""
        from commonUtils.runtime.operations import check_cancelled
        path = self.provider.root / relative
        suffix = path.suffix.lower()
        from features.images.document import IMAGE_EXTENSIONS
        if suffix in IMAGE_EXTENSIONS:
            from features.images.ui.viewer import open_image_choice
            from commonUtils.runtime.resources.selection import ResourceChoice
            return open_image_choice(ResourceChoice(self.provider, self.provider.relative(path), self.provider.acquire()), self)
        check_cancelled(cancelled)
        if suffix in {'.cbz', '.zip'}:
            from features.comics.library import ComicDocument
            from features.comics.pages import ComicPages
            return ComicPages(path, ComicDocument(path, source=self.provider)).cover(size)
        if suffix == '.epub':
            from features.books.epub import EPUBBook
            from features.books.ui.preview import cover_thumbnail
            return cover_thumbnail(EPUBBook(path, source=self.provider), size)[0]
        if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}:
            from commonUtils.ui.file_browser.thumbnails import image_thumbnail
            with self.provider.open(relative) as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            check_cancelled(cancelled)
            return image_thumbnail(data, size) if len(data) <= 16 * 1024 * 1024 else b''
        return b''

    def _details(self, row, cancelled):
        """Supply domain metadata to the shared information panel, without disk state."""
        from commonUtils.filesystem import BrowserDetails
        from commonUtils.runtime.operations import check_cancelled
        path = self.provider.root / row['path']
        with self.provider.operation(cancelled):
            check_cancelled(cancelled)
            if path.suffix.lower() in {'.cbz', '.zip'}:
                from features.comics.library import ComicDocument
                from features.comics.pages import ComicPages
                document = ComicDocument(path, source=self.provider)
                pages = ComicPages(path, document)
                fields = [('Pages', len(pages.pages))]
                for field in document.info.FIELDS:
                    try:
                        value = document.info.get_field(field)
                    except ValueError:
                        continue
                    if value:
                        fields.append((field, value))
                cover = pages.cover((360, 500))
                check_cancelled(cancelled)
                return [('Comic Metadata', BrowserDetails(tuple(fields), cover))]
            if path.suffix.lower() == '.epub':
                from features.books.epub import EPUBBook
                from features.books.ui.preview import cover_thumbnail
                book = EPUBBook(path, source=self.provider)
                fields = [('Title', book.title)]
                for key, label in (('creator', 'Author'), ('language', 'Language'), ('publisher', 'Publisher'),
                                   ('date', 'Published'), ('subject', 'Tags'), ('description', 'Description')):
                    values = book.values(key)
                    if values:
                        fields.append((label, '\n'.join(values)))
                cover, message = cover_thumbnail(book, (360, 500))
                check_cancelled(cancelled)
                return [('Book Metadata', BrowserDetails(tuple(fields), cover, message))]
            if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}:
                from commonUtils.ui.file_browser.thumbnails import image_thumbnail
                with self.provider.open(path) as stream:
                    data = stream.read(16 * 1024 * 1024 + 1)
                check_cancelled(cancelled)
                if len(data) > 16 * 1024 * 1024:
                    return [('Image Information', BrowserDetails(message='The image exceeds the preview memory limit.'))]
                buffer = qt.QBuffer()
                buffer.setData(qt.QByteArray(data))
                buffer.open(qt.QIODevice.OpenModeFlag.ReadOnly)
                dimensions = qt.QImageReader(buffer).size()
                fields = (('Width', dimensions.width()), ('Height', dimensions.height())) if dimensions.isValid() else ()
                return [('Image Information', BrowserDetails(fields, image_thumbnail(data, (360, 500))))]
            return ()

    def import_item(self, folder=False):
        from commonUtils.runtime.resources.local import LocalFiles
        from commonUtils.runtime.resources.mutations import move_resource
        from features.rclone.localcrypt.mapping import for_path, storage_root
        if self.file_browser.operation.busy:
            return
        selected = (qt.QFileDialog.getExistingDirectory(self, 'Move local folder into LocalCrypt') if folder else
                    qt.QFileDialog.getOpenFileName(self, 'Move local file into LocalCrypt')[0])
        if not selected:
            return
        path = Path(selected)
        boundary = storage_root().absolute()
        if for_path(path) or path == boundary or boundary in path.parents:
            qt.QMessageBox.warning(self, 'Move', 'Use Move to from the decrypted LocalCrypt browser for encrypted files.')
            return
        source = LocalFiles(path.parent)
        target = '/'.join(p for p in (self.provider.relative(self.file_browser.navigation.directory), path.name) if p)
        self.file_browser.mutate(lambda cancelled: move_resource(source, path.name, self.provider, target, cancelled=cancelled))

    def move_item(self, path):
        from commonUtils.runtime.resources.mutations import move_resource
        selected = choose_destination(self, self.provider, Path(path).name, 'Move')
        if selected is None:
            return
        destination, target, release = selected
        def work(cancelled):
            try:
                move_resource(self.provider, self.provider.relative(path), destination, target, cancelled=cancelled)
            finally:
                release()
        if not self.file_browser.mutate(work):
            release()

    @property
    def view_title(self):
        directory = self.file_browser.navigation.directory if self.file_browser else self.item.data
        return f'🕵️ Private - {self.item.remote} · {directory.name if directory != self.item.data else "LocalCrypt"}'

    def edit_epub_metadata(self, path):
        from features.books.ui.metadata_window import MetadataWindow
        release = self.provider.acquire()
        try:
            window = MetadataWindow(path, source=self.provider)
        except Exception:
            release()
            raise
        window.destroyed.connect(release)
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(window, self.provider)
        _windows.append(window)
        window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
        window.show()
        return window

    def edit_metadata(self, path):
        from features.comics.ui.metadata_editor import MetadataEditor
        rows = self.file_browser.selected_rows() if self.file_browser else []
        selected = [self.provider.root / row['path'] for row in rows]
        targets = [self.provider.root / row['path'] for row in rows
                   if row['directory'] or Path(row['path']).suffix.lower() in {'.cbz', '.zip'}] if path in selected else [path]
        release = self.provider.acquire()
        try:
            window = MetadataEditor(targets, source=self.provider)
        except Exception:
            release()
            raise
        window.destroyed.connect(release)
        from services.documents.ui.private_views import protect_private_view
        protect_private_view(window, self.provider)
        _windows.append(window)
        window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
        window.saved.connect(self._comic_metadata_saved)
        window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        window.show()
        return window

    def _comic_metadata_saved(self, path):
        browser = self.file_browser
        if self.closing or browser is None or browser.preview is None:
            return
        relative = self.provider.relative(path)
        if any(row['path'] == relative for row in browser.selected_rows()):
            # Re-read metadata through the existing cancellable preview worker.
            # It coalesces batch notifications and rejects older in-flight reads.
            browser.preview.request()

    def open_document(self, path, fragment='', *, password=None):
        if self.closing or self.open_operation.busy:
            return
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == '.rmdoc':
            from services.documents.ui.notebooks import open_notebook_choice
            from commonUtils.runtime.resources.selection import ResourceChoice
            return open_notebook_choice(ResourceChoice(self.provider, self.provider.relative(path), self.provider.acquire()), self)
        if suffix in {'.pdf', '.epub', '.cbz', '.zip'}:
            from services.documents.ui.readers import open_reader_choice
            from commonUtils.runtime.resources.selection import ResourceChoice
            return open_reader_choice(ResourceChoice(self.provider, self.provider.relative(path), self.provider.acquire()),
                                      self, 'pdf' if suffix == '.pdf' else 'epub' if suffix == '.epub' else 'comic', password=password)
        from commonUtils.formats.code_syntax import SOURCE_EXTENSIONS
        if suffix in SOURCE_EXTENSIONS and suffix not in {'.md', '.markdown'}:
            from services.documents.ui.editors import open_editor_choice
            from commonUtils.runtime.resources.selection import ResourceChoice
            open_editor_choice(ResourceChoice(self.provider, self.provider.relative(path), self.provider.acquire()), self)
            return
        self.pending_document = (path, fragment, password)
        self.pending_markdown_edit = bool(qt.QApplication.keyboardModifiers() & qt.Qt.KeyboardModifier.AltModifier)
        if suffix in {'.md', '.markdown'}:
            callback = lambda report, cancelled: ('markdown', prepare_markdown(self.provider, path))
        else:
            qt.QMessageBox.information(self, 'Private file', 'This browser opens notebooks, PDF, text/source files, Markdown, EPUB and comic ZIP/CBZ files.')
            return
        def open_private(report, cancelled):
            with self.provider.operation(cancelled):
                return callback(report, cancelled)
        self.open_operation.start(open_private, message='Opening private document…')

    def _opened(self, result, error):
        if self.closing or self.open_operation.cancelled.is_set():
            self.idle.emit()
            return
        path, fragment, password = self.pending_document
        if error or result is None:
            from services.documents.zip_passwords import is_password_error
            if is_password_error(error):
                from desktop.dialogs.archive_password import ask_password
                password = ask_password(path, error, self, source=self.provider)
                if password:
                    self.open_document(path, fragment, password=password)
            return
        kind, payload = result
        if kind == 'markdown':
            data, resources = payload
            storage = MarkdownStorage(self.provider, path, data, resources, self._open_link)
            release = self.provider.acquire()
            try:
                window = PrivateMarkdownWindow(path, storage, edit=self.pending_markdown_edit)
            except Exception:
                release()
                raise
            window.destroyed.connect(release)
            if fragment:
                window.viewer.browser.scrollToAnchor(fragment)
            _windows.append(window)
            window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
            show_document(window)
        self.open_operation.hide()

    def _open_link(self, path, fragment=''):
        if self.closing:
            browser = open_browser(self.item)
            if browser is not None:
                browser.open_document(path, fragment)
        else:
            self.open_document(path, fragment)

    def _close_tab(self):
        parent = self.parentWidget()
        (parent if isinstance(parent, qt.QDockWidget) else self).close()

    def prepare_close(self):
        from commonUtils.ui.resources.picker import resource_tasks_pending
        if resource_tasks_pending(self):
            return False
        self.closing = True
        self.open_operation.request_cancel()
        browser_busy = self.file_browser.stop() if self.file_browser else False
        notes = getattr(self, 'notes_offer', None)
        notes_ready = notes is None or notes.prepare_close()
        ready = not (browser_busy or self.open_operation.busy) and notes_ready
        if ready and self.provider is not None:
            self._release_provider()
        return ready

    def closeEvent(self, event):
        if self.prepare_close():
            event.accept()
        else:
            event.ignore()


def open_browser(item, parent=None):
    binary = executable.ensure_rclone()
    if binary is None:
        return None
    if not ensure_session(item.context, package=item.package, parent=parent):
        return None
    window = CryptBrowserView(item, parent)
    window.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
    window.resize(1100, 750)
    window.setWindowTitle(f'🕵️ Private - File Browser — {item.remote}')
    window.title_changed.connect(lambda title: window.setWindowTitle(f'🕵️ Private - File Browser — {title.removeprefix("🕵️ Private - ")}'))
    _windows.append(window)
    window.destroyed.connect(lambda: _windows.remove(window) if window in _windows else None)
    window.show()
    return window
