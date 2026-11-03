"""A lazy Notes Library document over local, encrypted or remote providers."""
from pathlib import Path, PurePosixPath
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.ui.appearance.status_line import StatusLine
from .dataview import NotesMarkdownViewer
from commonUtils.ui.markdown.navigation import MarkdownNavigation
from features.notes_library.notes import NotesLibrary, vault_root, operation, document_kind, MAX_NOTE
from .library_panels import LibraryPanels, FolderPageTree
from ..notes import breadcrumb_folders, fit_breadcrumbs
from ..navigation import PathChange, MutationResult


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
        owner.tree.setEnabled(False)
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


class NotesNameDelegate(qt.QStyledItemDelegate):
    """Keep the displayed name authoritative until the provider move succeeds."""
    def createEditor(self, parent, option, index):
        owner = self.parent().owner
        if owner.library is None or owner.progress.busy or owner.locked:
            return None
        return super().createEditor(parent, option, index)

    def setModelData(self, editor, model, index):
        path, _ = index.data(qt.Qt.ItemDataRole.UserRole)
        self.parent().owner.rename_tree_entry(path, editor.text())


class NotesTree(FolderPageTree):
    """Internal drops request a provider move; only success changes the tree."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.rename_click = False
        self.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(qt.Qt.DropAction.MoveAction)
        self.setEditTriggers(qt.QAbstractItemView.EditTrigger.SelectedClicked |
                             qt.QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setItemDelegate(NotesNameDelegate(self))

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        self.rename_click = bool(item is not None and item.isSelected() and
            item.flags() & qt.Qt.ItemFlag.ItemIsEditable and
            event.button() == qt.Qt.MouseButton.LeftButton and
            event.modifiers() == qt.Qt.KeyboardModifier.NoModifier)
        super().mousePressEvent(event)

    def dropEvent(self, event):
        event.ignore()
        if event.source() is not self:
            return
        source = self.currentItem()
        if source is None:
            return
        target = self.itemAt(event.position().toPoint())
        role = qt.Qt.ItemDataRole.UserRole
        path, _ = source.data(0, role)
        if path == self.owner.library.root:
            return
        parent = self.owner.library.root
        if target is not None:
            target_path, directory = target.data(0, role)
            parent = target_path if directory else str(PurePosixPath(target_path).parent)
            parent = '' if parent == '.' else parent
        self.owner.move_entry(path, '/'.join(filter(None, (parent, PurePosixPath(path).name))))


class NotesLibraryWindow(LibraryPanels, qt.QMainWindow):
    idle = qt.Signal()
    document_saved = qt.Signal()
    revoked = qt.Signal()
    aux_snapshot = qt.Signal(int, object)

    def __init__(self, factory, label, *, remote=False, root="", document_only=False):
        super().__init__()
        self.document_only = document_only
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Notes Library — ' + label)
        self.resize(1000, 750)
        self.provider = self.library = None
        self.release = self.unsubscribe = lambda: None
        self.closing = self.locked = False
        self.pending_close = False
        self._after_document_save = None
        self.history, self.index = [], -1
        self.items, self.loaded = {}, set()
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
        self.tree = NotesTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self.expand)
        self.tree.itemActivated.connect(self.choose)
        self.tree.itemClicked.connect(lambda item, column: self.choose(item)
                                      if not self.tree.rename_click else None)
        self.search = None
        sidebar = qt.QWidget()
        side = qt.QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        if not remote:
            self.search = qt.QLineEdit()
            self.search.setPlaceholderText('Filter loaded notes')
            qt.connect_search(self.search, self.filter)
            side.addWidget(self.search)
        side.addWidget(qt.QLabel('Notes Library · File names'))
        self.note_controls = qt.QWidget()
        note_controls = qt.QHBoxLayout(self.note_controls)
        note_controls.setContentsMargins(0, 0, 0, 0)
        self.new_note_button = qt.QPushButton('New Document')
        self.new_folder_button = qt.QPushButton('New folder')
        self.rename_button = qt.QPushButton('Rename / Move…')
        self.file_actions_button = qt.QToolButton()
        self.file_actions_button.setText('…')
        self.file_actions_button.setAccessibleName('Selection actions')
        self.file_actions_button.setToolTip('Move, copy or delete the selected file or folder')
        self.file_actions_button.clicked.connect(self.selected_file_actions)
        self.new_note_button.clicked.connect(self.new_note)
        self.new_folder_button.clicked.connect(lambda: self.new_entry(folder=True))
        self.rename_button.clicked.connect(self.rename_entry)
        for button in (self.new_note_button, self.new_folder_button, self.rename_button, self.file_actions_button):
            note_controls.addWidget(button)
        self.note_controls.setVisible(not remote)
        side.addWidget(self.note_controls)
        side.addWidget(self.tree)
        self.viewer.new_action.triggered.disconnect()
        self.viewer.new_action.triggered.connect(self.new_note)
        self.viewer.open_action.setEnabled(False)
        self.viewer.save_as_action.setEnabled(False)
        self.menu = qt.QToolButton()
        self.menu.setText('▤')
        self.menu.setAccessibleName('Browse Notes Library')
        self.menu.hide()
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
        self.init_panels(side, controls)
        self.save_action = qt.QAction('Save document', self)
        self.save_action.setShortcut(qt.QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save_current_document)
        self.addAction(self.save_action)
        self.split = qt.QSplitter()
        self.split.addWidget(self.panel_tabs)
        self.split.addWidget(self.document_stack)
        self.split.addWidget(self.links_tree)
        self.split.setStretchFactor(1, 1)
        self.split.setCollapsible(0, False)
        self.split.setSizes([260, 740])
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self.completed)
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.controls_bar)
        layout.addWidget(self.split, 1)
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
        layout.addWidget(self.operation_footer)
        self.setCentralWidget(body)
        self.place_navigation()
        self.revoked.connect(self.retire)
        self.pending = ('initial',)
        def initial(report, cancelled):
            provider = factory()
            release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
            try:
                library = NotesLibrary(provider, root)
                if document_only:
                    return provider, release, library, [], {}
                with operation(provider, cancelled):
                    rows = provider.list(library.root, cancelled=cancelled)
                notes = library.visible_rows(rows)
                if cancelled():
                    raise ValueError('Notes Library closed.')
                pages = library.folder_pages(notes, cancelled=cancelled)
                return provider, release, library, notes, pages
            except BaseException:
                release()
                raise
        self.progress.start(initial, message='Opening Notes Library…')
        self.tree.setEnabled(False)
        self.viewer.setEnabled(False)

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

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_connections()

    def show_sidebar(self, visible):
        self.panel_tabs.setVisible(not self.document_only)
        self.open_card.hide()

    def list_folder(self, path):
        if self.progress.busy or self.library is None or self.locked:
            return
        self.pending = ('folder', path)
        self.tree.setEnabled(False)
        def read(report, cancelled):
            rows = self.library.folders(path, cancelled=cancelled)
            pages = self.library.folder_pages(rows, cancelled=cancelled)
            return rows, pages
        self.progress.start(read, message='Loading notes…')

    def expand(self, item):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory and path not in self.loaded:
            self.list_folder(path)

    def choose(self, item, *args):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not directory:
            self.open_note(path)
        elif self.folder_pages.get(path):
            self.open_note(self.folder_pages[path])

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
        self.tree.setEnabled(False)
        pages = {}
        def read(report, cancelled):
            current = self.history[self.index] if self.index >= 0 else ''
            resolved, _, data = self.library.load_note(path, current=current, resolve_link=resolve_link,
                cancelled=cancelled, stage=lambda message: self.progress.progress_changed.emit(0, 0, message))
            folders = breadcrumb_folders(self.library.root, resolved)
            pages.update(self.library.folder_pages(
                [{'path': folder, 'directory': True} for folder in folders], cancelled=cancelled))
            if document_kind(resolved) is None:
                from ..file_preview import FilePreview
                preview = FilePreview.open(self.provider, resolved, cancelled=cancelled)
                try:
                    return resolved, (preview, preview.page())
                except BaseException:
                    preview.close()
                    raise
            if document_kind(resolved) == 'text':
                from services.documents.storage import DocumentResource
                from commonUtils.persistence.text import decode_bytes
                resource = DocumentResource(self.provider, resolved, max_bytes=MAX_NOTE)
                try:
                    snapshot = decode_bytes(resource.read(cancelled=cancelled), path=self.provider.root / resolved)
                    return resolved, (resource, snapshot)
                except BaseException:
                    resource.close()
                    raise
            if document_kind(resolved) == 'notebook':
                from features.application import registry
                if not registry.is_feature_enabled('notebooks'):
                    raise ValueError('Enable Notebooks to open Remarkable Documents.')
                from features.notebooks.notebook import Notebook, MAX_ARCHIVE
                from features.notebooks.storage import NotebookDocument
                from services.documents.storage import DocumentResource
                resource = DocumentResource(self.provider, resolved, max_bytes=MAX_ARCHIVE)
                try:
                    document = NotebookDocument(Notebook.read(resource.read(cancelled=cancelled)), resource=resource)
                    return resolved, document
                except BaseException:
                    resource.close()
                    raise
            from services.documents.markdown import prepare_markdown
            self.progress.progress_changed.emit(0, 0, 'Preparing embedded media…')
            return resolved, prepare_markdown(self.provider, self.provider.root / resolved, data=data, cancelled=cancelled,
                                             image_source=self.library.image_source(resolved, cancelled=cancelled))
        def read_with_path(report, cancelled):
            return read(report, cancelled), pages
        self.progress.start(read_with_path, message='Finding file…' if resolve_link else 'Reading ' + PurePosixPath(path).name + '…')

    def open_other_file(self, path):
        return self.open_note(path)

    def completed(self, result, error):
        kind, *values = self.pending
        pages = {}
        if kind == 'note' and result is not None:
            result, pages = result
        if self.closing or self.locked:
            if kind == 'initial' and result:
                result[1]()
            elif kind == 'note':
                self.discard_note_result(result)
            self.close()
            self.idle.emit()
            return
        self.tree.setEnabled(True)
        self.note_controls.setEnabled(True)
        self.progress.hide()
        if kind == 'note' and self.progress.cancelled.is_set():
            self.discard_note_result(result)
            result, error = None, error or 'Opening cancelled.'
        self.viewer.setEnabled(self.storage.path is not None or (kind == 'note' and not error))
        if kind == 'save':
            data, completed = values
            if not error:
                self.storage.data = data
            completed(error)
            if not error:
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
        if error:
            if kind == 'note':
                current = self.history[self.index] if self.index >= 0 else None
                self.library.release_media(current)
            self.viewer.status.setText(error)
            if kind == 'mutation':
                # Mutations cancel background readers before dispatch, including
                # those that fail without changing any files.
                if self.panel_tabs.currentIndex() == 1:
                    self.refresh_calendar()
                elif self.search is not None and self.search.text():
                    self.filter()
                self.refresh_connections()
            elif kind == 'folder':
                self.reveal_path = None
            self.idle.emit()
            return
        if kind == 'mutation':
            if not self.check_provider():
                return
            source, deleted, created = values
            mutation = result
            destination = mutation.destination
            if source is not None or deleted is not None:
                try:
                    from desktop.document_catalog import relocate
                    relocate(self.provider, source, destination, deleted=deleted)
                except (OSError, ValueError, PermissionError):
                    mutation.reference_errors.append('Some saved references could not be updated.')
                    self.viewer.status.setText('Files changed; ' + mutation.reference_errors[0])
            if mutation.refresh_errors:
                self.viewer.status.setText('Files updated; some folders could not refresh. ' + mutation.refresh_errors[0])
            change = PathChange(source, destination, deleted)
            current = self.history[self.index] if self.index >= 0 else None
            self.history, self.index = change.history(self.history, self.index)
            self.positions = change.positions(self.positions)
            if change.removes(current):
                self.clear_document()
                current = None
                self.index = -1
            if deleted:
                self.back.setEnabled(self.index > 0)
                self.forward.setEnabled(0 <= self.index < len(self.history) - 1)
            self.tree.clear()
            self.items.clear()
            self.loaded.clear()
            self.folder_pages.clear()
            for folder, rows in mutation.folders:
                entries, pages = rows
                self.populate(folder, entries, pages)
            if self.panel_tabs.currentIndex() == 1:
                self.refresh_calendar()
            if created:
                self.edit_created = destination
                self.open_note(destination)
            elif current is not None and change.remap(current) != current:
                if self.storage.path is not None:
                    self.storage.path = (self.provider.root / change.remap(current)).resolve()
                self.open_note(change.remap(current), remember=False)
            elif self.links_tree.isVisible():
                self.refresh_connections()
            self.idle.emit()
            return
        if kind == 'initial':
            self.provider, self.release, self.library, rows, pages = result
            from features.notes_library.notes import library_name
            self.document_container_title = library_name(self.provider, self.library.root)
            self.setWindowTitle(self.document_container_title)
            self.welcome_title.setText(self.document_container_title)
            from services.documents.ui.private_views import protect_private_view
            protect_private_view(self, self.provider)
            if not self.check_provider():
                return
            self.populate(self.library.root, rows, pages)
            self.new_note_button.setEnabled(self.library.supports('create'))
            self.new_card.setEnabled(self.library.supports('create'))
            self.new_folder_button.setEnabled(self.library.supports('create'))
            self.rename_button.setEnabled(self.library.supports('rename'))
            self.file_actions_button.setEnabled(any(self.library.supports(action) for action in ('rename', 'delete')))
            self.tree.setDragEnabled(self.library.supports('rename'))
            self.tree.setAcceptDrops(self.library.supports('rename'))
        elif kind == 'folder':
            if not self.check_provider():
                return
            rows, pages = result
            self.populate(values[0], rows, pages)
            if getattr(self, 'reveal_path', None) is not None:
                self.reveal_folder(self.reveal_path)
        else:
            if not self.check_provider():
                self.discard_note_result(result)
                return
            path, remember, fragment, index = values
            path, result = result
            self.folder_pages.update(pages)
            self.refresh_entry_icons()
            if remember:
                del self.history[self.index + 1:]
                self.history.append(path)
                self.index = len(self.history) - 1
            elif index is not None:
                self.index = index
            if document_kind(path) != 'markdown':
                self.viewer.browser.inline_videos.clear()
                self.viewer.formatted_editor.inline_videos.clear()
                self.library.release_media(path)
            if document_kind(path) is None:
                self.show_file(*result)
                self.back.setEnabled(self.index > 0)
                self.forward.setEnabled(self.index < len(self.history) - 1)
                self.up.setEnabled(True)
                self.refresh_connections()
                self.idle.emit()
                return
            if PurePosixPath(path).suffix.lower() == '.rmdoc':
                self.show_canvas(result)
                self.back.setEnabled(self.index > 0)
                self.forward.setEnabled(self.index < len(self.history) - 1)
                self.up.setEnabled(True)
                self.refresh_connections()
                self.idle.emit()
                return
            if document_kind(path) == 'text':
                self.show_text(*result)
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
            self.storage.data, self.storage.resources = result
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
        self.idle.emit()

    @staticmethod
    def discard_note_result(result):
        if result and PurePosixPath(result[0]).suffix.lower() == '.rmdoc':
            result[1].close()
        elif result and document_kind(result[0]) is None:
            result[1][0].close()
        elif result and document_kind(result[0]) == 'text':
            result[1][0].close()
        elif result and document_kind(result[0]) == 'markdown':
            getattr(result[1][1], 'close', lambda: None)()

    def selected_parent(self):
        tree = self.search_results if self.files_stack.currentWidget() is self.search_results else self.tree
        item = tree.currentItem()
        if item is None:
            return self.library.root
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        parent = path if directory else str(PurePosixPath(path).parent)
        return '' if parent == '.' else parent

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

    def new_note(self, *args):
        if self.progress.busy or self.locked or self.library is None or not self.library.supports('create'):
            return
        menu = qt.QMenu(self)
        for title, extension, icon in [('Remarkable Document', 'rmdoc', qt.QStyle.StandardPixmap.SP_FileDialogDetailedView),
                                       ('Markdown', 'md', qt.QStyle.StandardPixmap.SP_FileIcon)]:
            action = menu.addAction(self.style().standardIcon(icon), title)
            from features.application import registry
            action.setEnabled(extension != 'rmdoc' or registry.is_feature_enabled('notebooks'))
            action.triggered.connect(lambda checked=False, ext=extension: self.new_entry(extension=ext))
        menu.exec(qt.QCursor.pos())

    def new_entry(self, *, folder=False, extension='md'):
        from features.application import registry
        if extension == 'rmdoc' and not registry.is_feature_enabled('notebooks'):
            self.viewer.status.setText('Enable Notebooks to create Remarkable Documents.')
            return
        if self.progress.busy or self.locked or self.library is None or not self.library.supports('create'):
            return
        name, accepted = qt.QInputDialog.getText(self, 'New folder' if folder else 'New Remarkable Document' if extension == 'rmdoc' else 'New Markdown document', 'Folder name' if folder else 'File name')
        if not accepted:
            return
        parent = self.selected_parent()
        if not folder:
            known = {path for path, item in self.items.items() if item.data(0, qt.Qt.ItemDataRole.UserRole)[1]}
            folders = sorted(set(self.loaded) | known | {self.library.root, parent})
            labels = ['./' if folder == self.library.root else str(PurePosixPath(folder).relative_to(self.library.root or '.')) + '/' for folder in folders]
            selected, accepted = qt.QInputDialog.getItem(self, 'Save inside Notes Library',
                'Library folder (choose or enter a relative path)', labels, folders.index(parent), True)
            if not accepted:
                return
            try:
                parent = (folders[labels.index(selected)] if selected in labels
                          else self.library.contained(str(PurePosixPath(self.library.root) / selected)))
            except ValueError as error:
                self.viewer.status.setText(str(error))
                return
        def create(cancelled):
            action = self.library.create_folder if folder else self.library.create
            return action(name, parent, cancelled=cancelled) if folder else action(name, parent, extension=extension, cancelled=cancelled)
        self.mutate(create, created=not folder)

    def rename_entry(self):
        if self.library is None or self.progress.busy or self.locked:
            return
        tree = self.search_results if self.files_stack.currentWidget() is self.search_results else self.tree
        item = tree.currentItem()
        if item is None:
            return
        path, _ = item.data(0, qt.Qt.ItemDataRole.UserRole)
        relative = PurePosixPath(path).relative_to(self.library.root or '.').as_posix()
        destination, accepted = qt.QInputDialog.getText(self, 'Rename or move',
            'Path inside Notes Library (existing folders). Links are not rewritten.', text=relative)
        if accepted:
            self.move_entry(path, '/'.join(filter(None, (self.library.root, destination))))

    def move_entry(self, source, destination):
        if self.library is None or not self.library.supports('rename'):
            return
        self.mutate(lambda cancelled: self.library.move(source, destination, cancelled=cancelled), source=source)

    def rename_tree_entry(self, source, name):
        if name == PurePosixPath(source).name:
            return
        if not name.strip() or name in ('.', '..') or '/' in name or '\\' in name:
            self.viewer.status.setText('Enter a file or folder name without path separators.')
            return
        self.move_entry(source, str(PurePosixPath(source).with_name(name)))

    def mutate(self, work, *, source=None, created=False, deleted=None, leave=True):
        if self.progress.busy or self.locked:
            return
        if leave and not self.can_leave_document():
            self.defer_after_save(lambda: self.mutate(work, source=source, created=created,
                                                     deleted=deleted, leave=leave))
            return
        folders = set(self.loaded)
        self.remember_position()
        self.cancel_aux()
        self.cancel_connections()
        self.pending = ('mutation', source, deleted, created)
        self.tree.setEnabled(False)
        self.note_controls.setEnabled(False)
        self.viewer.setEnabled(False)
        def run(report, cancelled):
            destination = work(cancelled)
            change = PathChange(source, destination, deleted)
            paths = {change.remap(path) for path in folders} | {self.library.root, str(PurePosixPath(destination).parent)}
            from commonUtils.runtime.operations import OperationCancelled
            rows, errors = [], []
            for path in sorted(paths, key=lambda path: (len(PurePosixPath(path).parts), path)):
                if deleted and (path == deleted or path.startswith(deleted + '/')):
                    continue
                try:
                    entries = self.library.folders(path, cancelled=cancelled)
                    pages = self.library.folder_pages(entries, cancelled=cancelled)
                    rows.append((path, (entries, pages)))
                except (OSError, ValueError, OperationCancelled) as error:
                    errors.append(str(error))
            # Once published, retain the new path even if refreshing is cancelled.
            return MutationResult(destination, rows, errors)
        # The worker returns the authoritative destination, including an added .md.
        self.progress.start(run, message='Updating Notes Library…')

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

    def populate(self, path, rows, pages=None):
        self.folder_pages.update(pages or {})
        parent = self.items.get(path)
        if path == self.library.root and parent is None:
            parent = qt.QTreeWidgetItem(['Library root'])
            parent.setData(0, qt.Qt.ItemDataRole.UserRole, (path, True))
            parent.setFlags(parent.flags() & ~qt.Qt.ItemFlag.ItemIsDragEnabled)
            self.decorate_entry(parent, path, True)
            parent.setToolTip(0, 'Drop a file or folder here to move it to the library root')
            self.tree.addTopLevelItem(parent)
            self.items[path] = parent
        if parent:
            parent.takeChildren()
        self.loaded.add(path)
        for row in rows:
            item = qt.QTreeWidgetItem([row['name']])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, (row['path'], row['directory']))
            if self.library.supports('rename'):
                item.setFlags(item.flags() | qt.Qt.ItemFlag.ItemIsEditable)
            self.decorate_entry(item, row['path'], row['directory'])
            self.items[row['path']] = item
            if row['directory']:
                item.setChildIndicatorPolicy(qt.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            (parent.addChild if parent else self.tree.addTopLevelItem)(item)
        if path == self.library.root and parent is not None:
            parent.setExpanded(True)
        if self.search and self.search.text():
            self.filter()

    def navigate(self, offset):
        index = self.index + offset
        if 0 <= index < len(self.history):
            self.open_note(self.history[index], remember=False, index=index)

    def parent_folder(self):
        if self.index < 0:
            return
        parent = str(PurePosixPath(self.history[self.index]).parent)
        parent = '' if parent == '.' else parent
        self.reveal_folder(parent)

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

    def clear_content(self):
        self._after_document_save = None
        if self.library is not None:
            self.library.close()
        self.cancel_aux()
        self.cancel_connections()
        self.clear_document()
        self.tree.clear()
        self.items.clear()
        self.history.clear()
        self.loaded.clear()
        self.positions.clear()
        self.folder_pages.clear()
        self.search_results.clear()
        self.search_rows.clear()
        self.links_tree.clear()
        self.search_notice.clear()
        self.calendar_notice.clear()
        self.calendar_entries = None
        self.mark_daily_notes()
        if self.search is not None:
            self.search.clear()

    def retire(self):
        self.locked = True
        self.document_container_title = None
        self.progress.request_cancel()
        self.clear_content()
        self.setWindowTitle('Notes Library locked')
        self.setEnabled(False)
        if not self.progress.busy and not self.aux.busy and not self.connections_progress.busy:
            self.close()

    def prepare_close(self):
        if not self.closing and not self.locked and (
                self.document_saving):
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
        if getattr(self, 'file_preview', None) is not None:
            self.file_preview.operation.request_cancel()
        self.viewer.clear_data_views()
        if self.text_document is not None:
            self.text_document.operation.request_cancel()
            self.text_document.search.close_panel()
        self.progress.request_cancel()
        self.cancel_aux()
        self.cancel_connections()
        return (not self.progress.busy and not self.aux.busy and not self.connections_progress.busy
                and not (self.viewer.data_views and self.viewer.data_views.progress.busy)
                and not (self.text_document and (self.text_document.busy or self.text_document.search.busy))
                and not (getattr(self, 'file_preview', None) and self.file_preview.busy))

    def request_close(self):
        from commonUtils.ui.document_host import CloseOutcome, close_document
        if not self.prepare_close():
            return CloseOutcome.PENDING if self.closing or self.pending_close or self.document_saving else CloseOutcome.VETOED
        return CloseOutcome.ACCEPTED if close_document(self) else CloseOutcome.PENDING

    def closeEvent(self, event):
        if not self.prepare_close():
            event.ignore()
            return
        self.clear_content()
        self.unsubscribe()
        self.release()
        event.accept()


def open_notes(factory, label, *, remote=False, root=""):
    from commonUtils.ui.document_host import show_document, current_document_host
    host = current_document_host(destination='notes_library')
    application_host = current_document_host()
    if host is not None or application_host is not None:
        from features.application import registry
        if not registry.is_feature_enabled('notes_library'):
            raise ValueError('Enable Notes Library to open a library.')
        if ((host is not None and host.closing)
                or (application_host is not None and application_host.closing)):
            raise ValueError('Notes Library is closing. Finish or cancel closing before opening a library.')
    if host is not None:
        return host.open_library(factory, label, remote=remote, root=root)
    from services.documents.ui.editors import retain
    from .library_workspace import TabbedNotesLibrary
    window = TabbedNotesLibrary(factory, label, remote=remote, root=root)
    retain(window)
    return show_document(window)
