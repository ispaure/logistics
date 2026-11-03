"""Document panes own editors, history and resources without Files/Calendar UI."""
from pathlib import Path, PurePosixPath
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.ui.markdown.navigation import MarkdownNavigation
from .dataview import NotesMarkdownViewer
from .library_connections import LibraryConnections
from ..preparation import prepare_document
from ..notes import NotesLibrary, breadcrumb_folders, fit_breadcrumbs


class NotesBreadcrumbs(qt.QLabel):
    """A shrinking path beside history, with links only to folder notes."""
    def __init__(self, owner):
        super().__init__()
        self.owner, self.entries = owner, []
        self.setMinimumWidth(0)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Preferred)
        self.setTextFormat(qt.Qt.TextFormat.RichText)
        self.setTextInteractionFlags(qt.Qt.TextInteractionFlag.LinksAccessibleByMouse |
                                     qt.Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
        self.linkActivated.connect(self.activate)

    def activate(self, index):
        target = self.entries[int(index)][1]
        if target:
            self.owner.open_note(target)

    def show_path(self, path):
        folders = breadcrumb_folders(self.owner.library.root, path)
        self.entries = [(PurePosixPath(folder).name, self.owner.folder_pages.get(folder)) for folder in folders]
        self.entries.append((PurePosixPath(path).name, None))
        self.setToolTip(' / '.join(label for label, _ in self.entries))
        self.setAccessibleName(self.toolTip())
        self.render_path()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_path()

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, 'entries') and event.type() in (qt.QEvent.Type.PaletteChange, qt.QEvent.Type.FontChange):
            self.render_path()

    def render_path(self):
        from html import escape
        labels = fit_breadcrumbs([label for label, _ in self.entries], self.contentsRect().width(),
                                 self.fontMetrics().horizontalAdvance)
        color = self.palette().color(qt.QPalette.ColorRole.WindowText).name()
        self.setText(' / '.join(
            f'<a href="{i}" style="color:{color};text-decoration:underline">{escape(label)}</a>'
            if self.entries[i][1] else escape(label)
            for i, label in enumerate(labels) if label))


class NotesStatusLine(StatusLine):
    """Keep an empty nested document footer out of the workspace layout."""
    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))


class PageStorage:
    def __init__(self, window):
        self.window, self.data, self.path = window, b'', None
        self.resources = {}
        self.private = True  # Never render diagrams through a temporary file.
    def read_bytes(self, path):
        if path != self.path:
            raise ValueError('Open notes through the Notes Library navigation.')
        return self.data
    def submit_write(self, path, data, expected, completed):
        owner = self.window
        if owner.progress.busy or owner.locked or owner.library is None:
            completed('Notes Library is busy or locked.')
            return
        if path != self.path:
            completed('Save notes through their selected library context.')
            return
        relative = owner.library.contained(path.relative_to(owner.provider.root.resolve()).as_posix())
        owner.pending = ('save', data, completed)
        owner.set_navigation_enabled(False)
        owner.viewer.setEnabled(False)
        def write(report, cancelled):
            from services.documents.storage import DocumentResource
            with DocumentResource(owner.provider, relative, max_bytes=2 * 1024 * 1024, independent=False) as resource:
                if resource.read(cancelled=cancelled) != expected:
                    raise ValueError('Note changed. Reopen it before saving.')
                resource.save(data, cancelled=cancelled)
        owner.progress.start(write, message='Saving note…')

    def load_resource(self, kind, url):
        if self.window.locked or self.path is None or not self.window.check_provider():
            return qt.QImage() if kind == qt.QTextDocument.ResourceType.ImageResource else qt.QByteArray()
        if not url.isLocalFile():
            url = qt.QUrl.fromLocalFile(str(self.path.parent) + '/').resolved(url)
        target = Path(url.toLocalFile()).resolve()
        data = self.resources.get(target)
        if kind == qt.QTextDocument.ResourceType.ImageResource:
            from commonUtils.ui.markdown.images import prepared_image
            return prepared_image(data, getattr(self.resources, 'errors', {}).get(target))
        return qt.QByteArray(data or b'')

    def video_source(self, url):
        if self.window.locked or not self.window.check_provider():
            return None
        return getattr(self.resources, 'videos', {}).get(Path(url.toLocalFile()).resolve())
    def open_markdown_link(self, target):
        from urllib.parse import urlsplit
        link = urlsplit(target)
        if link.scheme == 'file' or link.path.startswith('/'):
            if qt.QUrl(target).host() != qt.QUrl.fromLocalFile(str(self.path)).host():
                self.window.viewer.status.setText('Choose a note inside this Notes Library.')
                return
            import posixpath
            base = qt.QUrl.fromLocalFile(str(self.path.parent)).path(qt.QUrl.ComponentFormattingOption.FullyEncoded)
            name = posixpath.relpath(link.path, base)
            target = link._replace(scheme='', netloc='', path=name).geturl()
        self.window.open_note(target, fragment=link.fragment, resolve_link=True)

    def open_link(self, path, fragment=''):
        owner = self.window
        if owner.library is not None:
            try:
                import posixpath
                from urllib.parse import quote
                relative = path.relative_to(owner.provider.root.resolve()).as_posix()
                current = self.path.relative_to(owner.provider.root.resolve()).as_posix()
                owner.open_note(quote(posixpath.relpath(relative, posixpath.dirname(current) or '.'), safe='/'),
                                fragment=fragment, resolve_link=True)
            except ValueError as error:
                owner.viewer.status.setText(str(error))


class DocumentPresentation:
    """Shared document behavior; each host supplies navigation and refresh hooks."""

    def init_document(self, *, remote=False):
        self.provider = self.library = None
        self.release = self.unsubscribe = lambda: None
        self.closing = self.locked = False
        self.pending_close = False
        self._after_document_save = None
        self.history, self.index = [], -1
        self.storage = PageStorage(self)
        self.viewer = NotesMarkdownViewer(storage=self.storage, allow_edit=not remote)
        old_status = self.viewer.status
        self.viewer.status = NotesStatusLine(old_status.text(), self.viewer)
        self.viewer.layout().replaceWidget(old_status, self.viewer.status)
        old_status.hide()
        old_status.deleteLater()
        self.viewer.layout().setContentsMargins(0, 0, 0, 0)
        self.viewer.layout().setSpacing(2)
        self.viewer.set_editing(False)
        self.viewer.browser.setPlaceholderText('Choose a document from the sidebar.')
        self.canvas = None
        self.text_document = None
        self.document_stack = qt.QStackedWidget()
        self.welcome = qt.QWidget()
        welcome = qt.QVBoxLayout(self.welcome)
        welcome.addStretch()
        welcome.setContentsMargins(40, 32, 40, 32)
        welcome.setSpacing(14)
        self.welcome_title = qt.QLabel('Notes Library')
        title_font = self.welcome_title.font()
        title_font.setPointSizeF(24)
        title_font.setBold(True)
        self.welcome_title.setFont(title_font)
        welcome.addWidget(self.welcome_title)
        hint = qt.QLabel('Choose a file from the sidebar, or create a document to start writing.')
        hint.setWordWrap(True)
        hint.setForegroundRole(qt.QPalette.ColorRole.PlaceholderText)
        welcome.addWidget(hint)
        self.open_card = qt.QPushButton('Open Document')
        self.open_card.clicked.connect(lambda: self.show_sidebar(True))
        self.open_card.hide()
        self.new_card = qt.QPushButton('New Document')
        self.new_card.clicked.connect(self.new_note)
        for card in (self.open_card, self.new_card):
            card.setMinimumHeight(44)
            card.setMaximumWidth(280)
            welcome.addWidget(card, 0, qt.Qt.AlignmentFlag.AlignLeft)
        self.new_card.setVisible(not remote)
        welcome.addStretch()
        self.document_stack.addWidget(self.welcome)
        self.document_stack.addWidget(self.viewer)
        if remote:
            self.viewer.find_action.setVisible(False)
            self.viewer.find_action.setEnabled(False)
            self.viewer.find_action.setShortcuts([])
        self.viewer.new_action.triggered.disconnect()
        self.viewer.new_action.triggered.connect(self.new_note)
        self.viewer.open_action.setEnabled(False)
        self.viewer.save_as_action.setEnabled(False)
        self.navigation = MarkdownNavigation(self, up=True)
        self.breadcrumbs = NotesBreadcrumbs(self)
        self.idle.connect(self.refresh_breadcrumb_path)
        self.navigation.layout().addWidget(self.breadcrumbs, 1)
        self.navigation.setMinimumWidth(0)
        self.navigation.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Preferred)
        self.back = self.navigation.back_button
        self.forward = self.navigation.forward_button
        self.up = self.navigation.up_button
        for button, label in ((self.back, 'Previous note'), (self.forward, 'Next note'),
                              (self.up, 'Browse parent folder')):
            button.setAccessibleName(label)
            button.setToolTip(label)
        self.back.clicked.connect(lambda: self.navigate(-1))
        self.forward.clicked.connect(lambda: self.navigate(1))
        self.up.clicked.connect(self.parent_folder)
        self.back.setEnabled(False)
        self.forward.setEnabled(False)
        self.up.setEnabled(False)
        self.controls_bar = qt.QWidget()
        controls = qt.QHBoxLayout(self.controls_bar)
        controls.setContentsMargins(0, 0, 0, 0)
        self.viewer.place_navigation(self.navigation)
        self.document_controls = controls
        self.document_stack.currentChanged.connect(self.place_navigation)
        controls.addStretch()
        self.save_drawing = qt.QPushButton('Save')
        self.save_drawing.setVisible(False)
        self.save_drawing.clicked.connect(lambda: self.canvas.save_document() if self.canvas is not None else None)
        controls.addWidget(self.save_drawing)
        self.save_action = qt.QAction('Save document', self)
        self.save_action.setShortcut(qt.QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_current_document)
        self.addAction(self.save_action)
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self.completed)
        self.operation_footer = qt.QWidget()
        footer = qt.QHBoxLayout(self.operation_footer)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(0)
        footer.setSizeConstraint(qt.QLayout.SizeConstraint.SetMinAndMaxSize)
        self.operation_footer.setSizePolicy(qt.QSizePolicy.Policy.Expanding, qt.QSizePolicy.Policy.Fixed)
        footer.addWidget(self.progress, 1)
        self.viewer.page_loading.setMaximumWidth(140)
        footer.addWidget(self.viewer.page_loading, 0, qt.Qt.AlignmentFlag.AlignRight)
        footer.addWidget(self.viewer.status, 1)
        self.positions = {}
        self.folder_pages = {}
        self.search = None

    def refresh_breadcrumb_path(self):
        if self.library is not None and not self.locked and not self.closing and self.index >= 0:
            self.breadcrumbs.show_path(self.history[self.index])


    def place_navigation(self, *args):
        markdown = self.document_stack.currentWidget() is self.viewer
        self.controls_bar.setVisible(not markdown and self.document_stack.currentWidget() is not self.welcome)
        self.links_tree.setVisible(markdown and self.links_button.isChecked())
        if not markdown:
            self.cancel_connections()
            self.links_tree.clear()
        if markdown:
            self.viewer.place_navigation(self.navigation)
            toolbar = self.viewer.navigation_toolbar
            for index in range(toolbar.count()):
                if toolbar.itemAt(index).spacerItem() is not None:
                    toolbar.setStretch(index, 0)
            toolbar.setStretchFactor(self.navigation, 1)
        else:
            self.document_controls.insertWidget(0, self.navigation, 1)


    def open_note(self, path, *, remember=True, fragment='', index=None, resolve_link=False):
        if self.progress.busy or self.library is None or self.locked:
            return
        try:
            if not resolve_link:
                path = self.library.contained(path)
        except ValueError as error:
            self.viewer.status.setText(str(error))
            return
        if not self.can_leave_document():
            self.defer_after_save(lambda: self.open_note(path, remember=remember, fragment=fragment,
                                                        index=index, resolve_link=resolve_link))
            return
        self.viewer.speech.stop()
        self.remember_position()
        self.pending = ('note', path, remember, fragment, index)
        self.viewer.setEnabled(False)
        self.set_navigation_enabled(False)
        from features.application import registry
        notebooks_enabled = registry.is_feature_enabled('notebooks')
        current = self.history[self.index] if self.index >= 0 else ''
        def read(report, cancelled):
            return prepare_document(self.library, path, current=current, resolve_link=resolve_link,
                cancelled=cancelled, notebooks_enabled=notebooks_enabled,
                stage=lambda message: self.progress.progress_changed.emit(0, 0, message))
        self.progress.start(read, message='Finding file…' if resolve_link else 'Reading ' + PurePosixPath(path).name + '…')


    def open_other_file(self, path):
        return self.open_note(path)


    @staticmethod
    def discard_note_result(result):
        if result is not None:
            result.close()


    def can_leave_document(self):
        preview = getattr(self, 'file_preview', None)
        if preview is not None and self.document_stack.currentWidget() is preview:
            return not preview.busy
        if self.text_document is not None and self.document_stack.currentWidget() is self.text_document:
            return self.text_document.can_leave()
        if self.canvas is None or self.document_stack.currentWidget() is not self.canvas:
            return self.viewer.can_close()
        if self.canvas.busy:
            return False
        if self.canvas.document is not None and self.canvas.document.dirty:
            answer = qt.QMessageBox.question(self, 'Unsaved document changes', 'Save changes before leaving?',
                qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel)
            if answer == qt.QMessageBox.StandardButton.Cancel:
                return False
            if answer == qt.QMessageBox.StandardButton.Save:
                self.canvas.save_document()
                return False
        return True


    def defer_after_save(self, callback):
        if self.document_saving:
            self._after_document_save = callback


    @property
    def document_saving(self):
        return (bool(getattr(self, 'file_preview', None) and self.file_preview.busy)
                or self.viewer.document_state.save_pending or bool(self.canvas and self.canvas.busy)
                or bool(self.text_document and self.text_document.busy))


    def save_current_document(self):
        current = self.document_stack.currentWidget()
        if current is getattr(self, 'file_preview', None):
            return False
        if current is self.text_document and self.text_document is not None:
            return self.text_document.save()
        if current is self.canvas and self.canvas is not None:
            return self.canvas.save_document()
        return self.viewer.save_document()


    def show_file(self, preview, html):
        self.clear_document()
        self.viewer.status.clear()
        if getattr(self, 'file_preview', None) is None:
            from .file_preview import LibraryFilePreview
            self.file_preview = LibraryFilePreview(self)
            self.file_preview.idle.connect(self.file_preview_idle)
            self.operation_footer.layout().addWidget(self.file_preview.operation, 1)
            self.document_stack.addWidget(self.file_preview)
        self.file_preview.load(preview, html)
        self.document_resource_path = self.provider.root / preview.path
        self.document_provider = self.provider
        self.document_stack.setCurrentWidget(self.file_preview)


    def file_preview_idle(self):
        if self.closing or self.locked or self.pending_close:
            self.close()
        elif not self.resume_after_save(''):
            self.idle.emit()


    def show_text(self, resource, snapshot):
        self.viewer.status.clear()
        if getattr(self, 'file_preview', None) is not None:
            self.file_preview.clear()
        self.viewer.clear_data_views()
        if self.canvas is not None:
            self.canvas.dispose()
        self.viewer.editor.document().setModified(False)
        self.viewer.formatted_editor.document().setModified(False)
        self.storage.path = None
        self.document_resource_path = self.provider.root / resource.path
        self.document_provider = self.provider
        if self.text_document is None:
            from .library_text import LibraryTextEditor
            self.text_document = LibraryTextEditor(self, status=NotesStatusLine())
            self.text_document.saved.connect(self.text_saved)
            self.text_document.idle.connect(lambda: self.close() if self.closing or self.locked else None)
            self.operation_footer.layout().addWidget(self.text_document.operation, 1)
            self.operation_footer.layout().addWidget(self.text_document.status, 1)
            self.document_stack.addWidget(self.text_document)
        self.text_document.load(resource, snapshot, writable=self.library.writable)
        self.document_stack.setCurrentWidget(self.text_document)
        self.save_drawing.hide()


    def text_saved(self, error):
        if self.closing or self.locked or self.pending_close and not error:
            self.close()
            return
        self.pending_close = False
        if not error:
            self.library.connection_index.invalidate()
            self.document_saved.emit()
        if not self.resume_after_save(error) and not error:
            if self.search is not None and self.search.text():
                self.filter()
            self.refresh_connections()


    def resume_after_save(self, error):
        callback, self._after_document_save = self._after_document_save, None
        if callback is not None and not error and not self.closing and not self.locked and not self.pending_close:
            callback()
            return True
        return False


    def show_canvas(self, document):
        self.viewer.status.clear()
        if getattr(self, 'file_preview', None) is not None:
            self.file_preview.clear()
        self.viewer.clear_data_views()
        if self.text_document is not None:
            self.text_document.clear()
        self.storage.path = None
        self.document_resource_path = self.provider.root / document.resource.path
        self.document_provider = self.provider
        self.viewer.editor.document().setModified(False)
        self.viewer.formatted_editor.document().setModified(False)
        self.viewer.document_state.new()
        self.viewer.document_title.setText('')
        if self.canvas is None:
            from features.notebooks.ui.workspace import NotebookWorkspace
            owner = self
            class LibraryCanvas(NotebookWorkspace):
                def open(self, book, key):
                    super().open(book, key)
                    owner.operation_footer.layout().addWidget(self.operation, 1)

                def clear(self):
                    operation = getattr(self, 'operation', None)
                    if operation is not None:
                        self.layout.addWidget(operation)
                    super().clear()
                    self.operation = None

                def saved(self, document, error):
                    super().saved(document, error)
                    if error:
                        owner.pending_close = False
                    owner.resume_after_save(error)
            self.canvas = LibraryCanvas(self, library=False)
            self.document_stack.addWidget(self.canvas)
        else:
            self.canvas.dispose()
        self.canvas.document = document
        self.canvas.open(document.book, document.key)
        self.document_stack.setCurrentWidget(self.canvas)
        self.save_drawing.setVisible(True)
        self.save_drawing.setEnabled(document.writable)


    def resource_provider(self):
        return self.provider


    def prepare_credential_lock(self):
        return not self.progress.busy and self.can_leave_document()


    def retire_private_content(self):
        self.retire()


    def credentials_revoked(self):
        self.revoked.emit()


    def check_provider(self):
        try:
            from services.documents.storage import check_document_access
            check_document_access(self.provider)
            return True
        except (OSError, ValueError):
            self.retire()
            return False


    def navigate(self, offset):
        index = self.index + offset
        if 0 <= index < len(self.history):
            self.open_note(self.history[index], remember=False, index=index)


    def clear_document(self):
        self.viewer.status.clear()
        self.breadcrumbs.entries = []
        self.breadcrumbs.clear()
        self.breadcrumbs.setToolTip('')
        self.breadcrumbs.setAccessibleName('')
        if getattr(self, 'file_preview', None) is not None:
            self.file_preview.clear()
        self.viewer.browser.inline_videos.clear()
        self.viewer.formatted_editor.inline_videos.clear()
        self.viewer.clear_data_views()
        if self.text_document is not None:
            self.text_document.clear()
        self.up.setEnabled(False)
        if self.canvas is not None:
            self.canvas.dispose()
        self.viewer.speech.stop()
        self.storage.data = b''
        self.storage.resources = {}
        self.storage.path = None
        self.viewer.document_state.new()
        self.viewer.document_title.setText('')
        self.viewer.location.clear()
        self.viewer.history.clear()
        self.viewer.history_index = -1
        self.viewer.browser.clear()
        self.viewer.editor.clear()
        self.viewer.formatted_editor.clear()
        self.document_stack.setCurrentWidget(self.welcome)
        self.save_drawing.hide()


    def request_close(self):
        from commonUtils.ui.document_host import CloseOutcome, close_document
        if not self.prepare_close():
            return CloseOutcome.PENDING if self.closing or self.pending_close or self.document_saving else CloseOutcome.VETOED
        return CloseOutcome.ACCEPTED if close_document(self) else CloseOutcome.PENDING


    def remember_position(self):
        if self.storage.path is not None:
            path = self.storage.path.relative_to(self.provider.root.resolve()).as_posix()
            surface = self.viewer.active_editor() if self.viewer.edit_button.isChecked() else self.viewer.browser
            self.positions[path] = surface.verticalScrollBar().value()

    def restore_position(self, path):
        if path in self.positions:
            surface = self.viewer.active_editor() if self.viewer.edit_button.isChecked() else self.viewer.browser
            surface.verticalScrollBar().setValue(self.positions[path])

    def complete_save(self, values, error):
        data, completed = values
        if not error:
            self.storage.data = data
        completed(error)
        if not error:
            self.library.connection_index.invalidate()
            self.document_saved.emit()
        self.progress.hide()
        self.idle.emit()
        if self.pending_close and not error:
            self._after_document_save = None
            self.close()
        else:
            self.pending_close = False
            if self.resume_after_save(error):
                return
            if not error:
                if self.search is not None and self.search.text():
                    self.filter()
                self.refresh_connections()
        return

    def publish_note(self, values, result):
        if not self.check_provider():
            self.discard_note_result(result)
            return
        path, remember, fragment, index = values
        path = result.path
        self.folder_pages.update(result.folder_pages)
        self.refresh_document_entries()
        if remember:
            del self.history[self.index + 1:]
            self.history.append(path)
            self.index = len(self.history) - 1
        elif index is not None:
            self.index = index
        if result.kind != 'markdown':
            self.viewer.browser.inline_videos.clear()
            self.viewer.formatted_editor.inline_videos.clear()
            self.library.release_media(path)
        if result.kind is None:
            self.show_file(result.preview, result.rendered)
            self.back.setEnabled(self.index > 0)
            self.forward.setEnabled(self.index < len(self.history) - 1)
            self.up.setEnabled(True)
            self.refresh_connections()
            self.idle.emit()
            return
        if result.kind == 'notebook':
            self.show_canvas(result.notebook)
            self.back.setEnabled(self.index > 0)
            self.forward.setEnabled(self.index < len(self.history) - 1)
            self.up.setEnabled(True)
            self.refresh_connections()
            self.idle.emit()
            return
        if result.kind == 'text':
            self.show_text(result.resource, result.snapshot)
            self.back.setEnabled(self.index > 0)
            self.forward.setEnabled(self.index < len(self.history) - 1)
            self.up.setEnabled(True)
            self.refresh_connections()
            self.idle.emit()
            return
        if self.canvas is not None:
            self.canvas.dispose()
        if self.text_document is not None:
            self.text_document.clear()
        if getattr(self, 'file_preview', None) is not None:
            self.file_preview.clear()
        self.document_stack.setCurrentWidget(self.viewer)
        self.save_drawing.setVisible(False)
        self.viewer.clear_data_views()
        self.storage.path = (self.provider.root / path).resolve()
        self.document_resource_path = self.provider.root / path
        self.document_provider = self.provider
        self.storage.data, self.storage.resources = result.data, result.resources
        self.library.release_media(path)
        self.viewer.history.clear()
        self.viewer.history_index = -1
        # Leaving was confirmed before the read. Keep the old draft on read
        # failure, then retire it here without prompting a second time.
        self.viewer._sync_formatted()
        self.viewer.editor.document().setModified(False)
        self.viewer.formatted_editor.document().setModified(False)
        self.viewer.open_document(self.storage.path, fragment=fragment)
        if getattr(self, 'edit_created', None) == path:
            self.edit_created = None
            self.viewer.set_editing(True)
        if not fragment:
            self.restore_position(path)
        self.back.setEnabled(self.index > 0)
        self.forward.setEnabled(self.index < len(self.history) - 1)
        self.up.setEnabled(True)
        self.refresh_connections()


class NotesDocumentPane(LibraryConnections, DocumentPresentation, qt.QWidget):
    idle = qt.Signal()
    document_saved = qt.Signal()
    revoked = qt.Signal()

    def __init__(self, workspace, label):
        super().__init__()
        self.workspace = workspace
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(label)
        self.init_document()
        self.init_connections()
        self.split = qt.QSplitter()
        self.split.addWidget(self.document_stack)
        self.split.addWidget(self.links_tree)
        self.split.setStretchFactor(0, 1)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.controls_bar)
        layout.addWidget(self.split, 1)
        layout.addWidget(self.operation_footer)
        self.place_navigation()
        self.revoked.connect(self.retire)
        self.pending = ('initial',)
        provider, root = workspace.provider, workspace.library.root
        def acquire(report, cancelled):
            release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
            try:
                return provider, release, NotesLibrary(provider, root, connection_index=workspace.library.connection_index)
            except BaseException:
                release()
                raise
        self.progress.start(acquire, message='Opening Notes Library…')
        self.viewer.setEnabled(False)

    def set_navigation_enabled(self, enabled):
        # Navigation lives in the workspace; document interaction is gated by
        # its own progress and editor state.
        return

    def refresh_document_entries(self):
        return

    def new_note(self, *args):
        return self.workspace.new_note(*args)

    def show_sidebar(self, visible):
        return self.workspace.show_sidebar(visible)

    def parent_folder(self):
        if self.index >= 0:
            self.workspace.document_tabs.parent_folder(self)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_connections()

    def completed(self, result, error):
        kind, *values = self.pending
        if self.closing or self.locked:
            if result is not None:
                if kind == 'initial':
                    result[1]()
                elif kind == 'note':
                    self.discard_note_result(result)
            self.close()
            self.idle.emit()
            return
        self.progress.hide()
        if kind == 'note' and self.progress.cancelled.is_set():
            if result is not None:
                self.discard_note_result(result)
            result, error = None, error or 'Opening cancelled.'
        self.viewer.setEnabled(self.storage.path is not None or (kind == 'note' and not error))
        if kind == 'save':
            self.complete_save(values, error)
            return
        if error:
            if kind == 'note':
                self.library.release_media(self.history[self.index] if self.index >= 0 else None)
            self.viewer.status.setText(error)
        elif kind == 'initial':
            self.provider, self.release, self.library = result
            from services.documents.ui.private_views import protect_private_view
            protect_private_view(self, self.provider)
            self.check_provider()
        else:
            self.publish_note(values, result)
        self.idle.emit()

    def clear_content(self):
        self._after_document_save = None
        if self.library is not None:
            self.library.close()
        self.cancel_connections()
        self.clear_document()
        self.history.clear()
        self.positions.clear()
        self.folder_pages.clear()
        self.links_tree.clear()

    def retire(self):
        self.locked = True
        self.progress.request_cancel()
        self.clear_content()
        self.setEnabled(False)
        if not self.progress.busy and not self.connections_progress.busy:
            self.close()

    def prepare_close(self):
        if not self.closing and not self.locked and self.document_saving:
            self.pending_close = True
            self._after_document_save = None
            return False
        if not self.closing and not self.locked and not self.can_leave_document():
            self.pending_close = self.document_saving
            if self.pending_close:
                self._after_document_save = None
            return False
        self._after_document_save = None
        self.closing = True
        self.viewer.clear_data_views()
        self.progress.request_cancel()
        self.cancel_connections()
        if self.text_document is not None:
            self.text_document.operation.request_cancel()
            self.text_document.search.close_panel()
        preview = getattr(self, 'file_preview', None)
        if preview is not None:
            preview.operation.request_cancel()
        return (not self.progress.busy and not self.connections_progress.busy
                and not (self.viewer.data_views and self.viewer.data_views.progress.busy)
                and not (self.text_document and (self.text_document.busy or self.text_document.search.busy))
                and not (preview and preview.busy))

    def closeEvent(self, event):
        if not self.prepare_close():
            event.ignore()
            return
        self.clear_content()
        self.unsubscribe()
        self.release()
        event.accept()
