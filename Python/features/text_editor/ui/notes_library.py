"""A lazy Notes Library document over local, encrypted or remote providers."""
from pathlib import Path, PurePosixPath
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.ui.markdown.viewer import MarkdownViewer
from commonUtils.ui.readers.reader_chrome import reader_button
from features.text_editor.notes import NotesLibrary, vault_root, operation


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
        data = self.resources.get(Path(url.toLocalFile()))
        if kind == qt.QTextDocument.ResourceType.ImageResource:
            return qt.QImage.fromData(data) if data else qt.QImage()
        return qt.QByteArray(data or b'')
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


class NotesTree(qt.QTreeWidget):
    """Internal drops request a provider move; only success changes the tree."""
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setDragDropMode(qt.QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(qt.Qt.DropAction.MoveAction)
        self.setEditTriggers(qt.QAbstractItemView.EditTrigger.NoEditTriggers)

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
        parent = self.owner.library.root
        if target is not None:
            target_path, directory = target.data(0, role)
            parent = target_path if directory else str(PurePosixPath(target_path).parent)
            parent = '' if parent == '.' else parent
        self.owner.move_entry(path, '/'.join(filter(None, (parent, PurePosixPath(path).name))))


class NotesLibraryWindow(qt.QMainWindow):
    idle = qt.Signal()
    revoked = qt.Signal()

    def __init__(self, factory, label, *, remote=False, root=""):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Notes Library — ' + label)
        self.resize(1000, 750)
        self.provider = self.library = None
        self.release = self.unsubscribe = lambda: None
        self.closing = self.locked = False
        self.pending_close = False
        self.history, self.index = [], -1
        self.items, self.loaded = {}, set()
        self.storage = PageStorage(self)
        self.viewer = MarkdownViewer(storage=self.storage, allow_edit=not remote)
        self.viewer.browser.setPlaceholderText('Choose a Markdown note from the sidebar.')
        self.viewer.back_button.hide()
        self.viewer.forward_button.hide()
        if remote:
            self.viewer.find_action.setVisible(False)
            self.viewer.find_action.setEnabled(False)
            self.viewer.find_action.setShortcuts([])
        self.tree = NotesTree(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self.expand)
        self.tree.itemActivated.connect(self.choose)
        self.tree.itemClicked.connect(self.choose)
        self.search = None
        sidebar = qt.QWidget()
        side = qt.QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        if not remote:
            self.search = qt.QLineEdit()
            self.search.setPlaceholderText('Filter loaded notes')
            self.search.textChanged.connect(self.filter)
            side.addWidget(self.search)
        side.addWidget(qt.QLabel('Notes Library · File names'))
        self.note_controls = qt.QWidget()
        note_controls = qt.QHBoxLayout(self.note_controls)
        note_controls.setContentsMargins(0, 0, 0, 0)
        self.new_note_button = qt.QPushButton('New note')
        self.new_folder_button = qt.QPushButton('New folder')
        self.rename_button = qt.QPushButton('Rename / Move…')
        self.new_note_button.clicked.connect(self.new_note)
        self.new_folder_button.clicked.connect(lambda: self.new_entry(folder=True))
        self.rename_button.clicked.connect(self.rename_entry)
        for button in (self.new_note_button, self.new_folder_button, self.rename_button):
            note_controls.addWidget(button)
        self.note_controls.setVisible(not remote)
        side.addWidget(self.note_controls)
        side.addWidget(self.tree)
        self.viewer.new_action.triggered.disconnect()
        self.viewer.new_action.triggered.connect(self.new_note)
        self.viewer.open_action.setEnabled(False)
        self.viewer.save_as_action.setEnabled(False)
        self.menu = qt.QToolButton()
        self.menu.setText('☰')
        self.menu.setAccessibleName('Browse Notes Library')
        self.menu.clicked.connect(lambda: sidebar.setVisible(not sidebar.isVisible()))
        self.back = reader_button(self, 'Previous note', icon='previous')
        self.forward = reader_button(self, 'Next note', icon='next')
        self.up = reader_button(self, 'Browse parent folder', icon='up')
        self.back.clicked.connect(lambda: self.navigate(-1))
        self.forward.clicked.connect(lambda: self.navigate(1))
        self.up.clicked.connect(self.parent_folder)
        self.back.setEnabled(False)
        self.forward.setEnabled(False)
        self.up.setEnabled(False)
        controls = qt.QHBoxLayout()
        for button in (self.menu, self.back, self.forward, self.up):
            controls.addWidget(button)
        controls.addStretch()
        self.split = qt.QSplitter()
        self.split.addWidget(sidebar)
        self.split.addWidget(self.viewer)
        self.split.setSizes([260, 740])
        self.progress = OperationProgress(self)
        self.progress.completed.connect(self.completed)
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        layout.addLayout(controls)
        layout.addWidget(self.split, 1)
        layout.addWidget(self.progress)
        self.setCentralWidget(body)
        self.revoked.connect(self.retire)
        self.pending = ('initial',)
        def initial(report, cancelled):
            provider = factory()
            release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
            try:
                library = NotesLibrary(provider, root)
                with operation(provider, cancelled):
                    rows = provider.list(library.root, cancelled=cancelled)
                if vault_root(provider, library.root, rows) is None:
                    raise ValueError('This location has no .obsidian directory.')
                notes = library.visible_rows(rows)
                if cancelled():
                    raise ValueError('Notes Library closed.')
                return provider, release, library, notes
            except BaseException:
                release()
                raise
        self.progress.start(initial, message='Opening Notes Library…')
        self.tree.setEnabled(False)
        self.viewer.setEnabled(False)

    def list_folder(self, path):
        if self.progress.busy or self.library is None or self.locked:
            return
        self.pending = ('folder', path)
        self.tree.setEnabled(False)
        self.progress.start(lambda report, cancelled: self.library.folders(path, cancelled=cancelled), message='Loading notes…')

    def expand(self, item):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory and path not in self.loaded:
            self.list_folder(path)

    def choose(self, item, *args):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not directory:
            self.open_note(path)

    def open_note(self, path, *, remember=True, fragment='', index=None, resolve_link=False):
        if self.progress.busy or self.library is None or self.locked:
            return
        try:
            if not resolve_link:
                path = self.library.contained(path)
        except ValueError as error:
            self.viewer.status.setText(str(error))
            return
        if not self.viewer.can_close():
            return
        self.viewer.speech.stop()
        self.pending = ('note', path, remember, fragment, index)
        self.viewer.setEnabled(False)
        self.tree.setEnabled(False)
        def read(report, cancelled):
            from services.documents.markdown import prepare_markdown
            resolved = path
            if resolve_link:
                current = self.storage.path.relative_to(self.provider.root.resolve()).as_posix()
                resolved, _ = self.library.link(current, path, cancelled=cancelled)
            data = self.library.read(resolved, cancelled=cancelled)
            return resolved, prepare_markdown(self.provider, self.provider.root / resolved, data=data, cancelled=cancelled,
                                             image_source=self.library.image_source(resolved))
        self.progress.start(read, message='Opening note…')

    def completed(self, result, error):
        kind, *values = self.pending
        if self.closing or self.locked:
            if kind == 'initial' and result:
                result[1]()
            self.close()
            self.idle.emit()
            return
        self.tree.setEnabled(True)
        self.note_controls.setEnabled(True)
        self.progress.hide()
        self.viewer.setEnabled(self.storage.path is not None or (kind == 'note' and not error))
        if kind == 'save':
            data, completed = values
            if not error:
                self.storage.data = data
            completed(error)
            self.progress.hide()
            self.idle.emit()
            if self.pending_close and not error:
                self.close()
            else:
                self.pending_close = False
            return
        if error:
            self.viewer.status.setText(error)
            self.idle.emit()
            return
        if kind == 'mutation':
            if not self.check_provider():
                return
            source, _, created = values
            destination, result, refresh_errors = result
            if refresh_errors:
                self.viewer.status.setText('Files updated; some folders could not refresh. ' + refresh_errors[0])
            def remap(path):
                return destination + path[len(source):] if source is not None and (
                    path == source or path.startswith(source + '/')) else path
            current = self.history[self.index] if self.index >= 0 else None
            self.history = [remap(path) for path in self.history]
            self.tree.clear()
            self.items.clear()
            self.loaded.clear()
            for folder, rows in result:
                self.populate(folder, rows)
            if created:
                self.open_note(destination)
            elif current is not None and remap(current) != current:
                self.open_note(remap(current), remember=False)
            self.idle.emit()
            return
        if kind == 'initial':
            self.provider, self.release, self.library, rows = result
            from services.documents.ui.private_views import protect_private_view
            protect_private_view(self, self.provider)
            if not self.check_provider():
                return
            self.populate(self.library.root, rows)
            self.new_note_button.setEnabled(self.library.supports('create'))
            self.new_folder_button.setEnabled(self.library.supports('create'))
            self.rename_button.setEnabled(self.library.supports('rename'))
            self.tree.setDragEnabled(self.library.supports('rename'))
            self.tree.setAcceptDrops(self.library.supports('rename'))
        elif kind == 'folder':
            if not self.check_provider():
                return
            self.populate(values[0], result)
        else:
            if not self.check_provider():
                return
            path, remember, fragment, index = values
            path, result = result
            if remember:
                del self.history[self.index + 1:]
                self.history.append(path)
                self.index = len(self.history) - 1
            elif index is not None:
                self.index = index
            self.storage.path = (self.provider.root / path).resolve()
            self.storage.data, self.storage.resources = result
            self.viewer.history.clear()
            self.viewer.history_index = -1
            # Leaving was confirmed before the read. Keep the old draft on read
            # failure, then retire it here without prompting a second time.
            self.viewer._sync_formatted()
            self.viewer.editor.document().setModified(False)
            self.viewer.formatted_editor.document().setModified(False)
            self.viewer.open_document(self.storage.path, fragment=fragment)
            self.back.setEnabled(self.index > 0)
            self.forward.setEnabled(self.index < len(self.history) - 1)
            self.up.setEnabled(True)
        self.idle.emit()

    def selected_parent(self):
        item = self.tree.currentItem()
        if item is None:
            return self.library.root
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        parent = path if directory else str(PurePosixPath(path).parent)
        return '' if parent == '.' else parent

    def new_note(self, *args):
        self.new_entry()

    def new_entry(self, *, folder=False):
        if self.progress.busy or self.locked or self.library is None or not self.library.supports('create'):
            return
        name, accepted = qt.QInputDialog.getText(self, 'New folder' if folder else 'New note', 'Folder name' if folder else 'File name')
        if not accepted:
            return
        parent = self.selected_parent()
        def create(cancelled):
            action = self.library.create_folder if folder else self.library.create
            return action(name, parent, cancelled=cancelled)
        self.mutate(create, created=not folder)

    def rename_entry(self):
        if self.library is None or self.progress.busy or self.locked:
            return
        item = self.tree.currentItem()
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

    def mutate(self, work, *, source=None, created=False):
        if self.progress.busy or self.locked or not self.viewer.can_close():
            return
        folders = set(self.loaded)
        self.pending = ('mutation', source, None, created)
        self.tree.setEnabled(False)
        self.note_controls.setEnabled(False)
        self.viewer.setEnabled(False)
        def run(report, cancelled):
            destination = work(cancelled)
            def remap(path):
                return destination + path[len(source):] if source is not None and (
                    path == source or path.startswith(source + '/')) else path
            paths = {remap(path) for path in folders} | {self.library.root, str(PurePosixPath(destination).parent)}
            from commonUtils.runtime.operations import OperationCancelled
            rows, errors = [], []
            for path in sorted(paths, key=lambda path: (len(PurePosixPath(path).parts), path)):
                try:
                    rows.append((path, self.library.folders(path, cancelled=cancelled)))
                except (OSError, ValueError, OperationCancelled) as error:
                    errors.append(str(error))
            # Once published, retain the new path even if refreshing is cancelled.
            return destination, rows, errors
        # The worker returns the authoritative destination, including an added .md.
        self.progress.start(run, message='Updating Notes Library…')

    def resource_provider(self):
        return self.provider

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

    def populate(self, path, rows):
        parent = self.items.get(path)
        if parent:
            parent.takeChildren()
        self.loaded.add(path)
        for row in rows:
            item = qt.QTreeWidgetItem([row['name']])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, (row['path'], row['directory']))
            self.items[row['path']] = item
            if row['directory']:
                item.setChildIndicatorPolicy(qt.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            (parent.addChild if parent else self.tree.addTopLevelItem)(item)
        if self.search:
            self.filter()

    def filter(self, *args):
        query = self.search.text().casefold()
        for path, item in self.items.items():
            _, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
            item.setHidden(not directory and query not in path.casefold())

    def navigate(self, offset):
        index = self.index + offset
        if 0 <= index < len(self.history):
            self.open_note(self.history[index], remember=False, index=index)

    def parent_folder(self):
        if self.index < 0:
            return
        parent = str(PurePosixPath(self.history[self.index]).parent)
        parent = '' if parent == '.' else parent
        self.split.widget(0).show()
        item = self.items.get(parent)
        if item:
            item.setExpanded(True)
            self.tree.scrollToItem(item)

    def clear_content(self):
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
        self.tree.clear()
        self.items.clear()
        self.history.clear()
        self.loaded.clear()
        if self.search is not None:
            self.search.clear()

    def retire(self):
        self.locked = True
        self.progress.request_cancel()
        self.clear_content()
        self.setWindowTitle('Notes Library locked')
        self.setEnabled(False)
        if not self.progress.busy:
            self.close()

    def prepare_close(self):
        if not self.closing and not self.locked and not self.viewer.can_close():
            self.pending_close = self.viewer.document_state.save_pending
            return False
        self.closing = True
        self.progress.request_cancel()
        return not self.progress.busy

    def closeEvent(self, event):
        if not self.prepare_close():
            event.ignore()
            return
        self.clear_content()
        self.unsubscribe()
        self.release()
        event.accept()


def open_notes(factory, label, *, remote=False, root=""):
    from commonUtils.ui.document_host import show_document
    from services.documents.ui.editors import retain
    window = NotesLibraryWindow(factory, label, remote=remote, root=root)
    retain(window)
    return show_document(window)
