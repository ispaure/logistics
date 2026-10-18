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
        self.private = True  # Never render diagrams through a temporary file.
    def read_bytes(self, path):
        if path != self.path:
            raise ValueError('Open notes through the Notes Library navigation.')
        return self.data
    def load_resource(self, *args):
        return None
    def open_link(self, path, fragment=''):
        owner = self.window
        if owner.library is not None:
            try:owner.open_note(path.relative_to(owner.provider.root.resolve()).as_posix(), fragment=fragment)
            except ValueError as error:owner.viewer.status.setText(str(error))


class NotesLibraryWindow(qt.QMainWindow):
    idle = qt.Signal()
    revoked = qt.Signal()

    def __init__(self, factory, label, *, remote=False):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle('Notes Library — ' + label)
        self.resize(1000, 750)
        self.provider = self.library = None
        self.release = self.unsubscribe = lambda: None
        self.closing = self.locked = False
        self.history, self.index = [], -1
        self.items, self.loaded = {}, set()
        self.storage = PageStorage(self)
        self.viewer = MarkdownViewer(storage=self.storage)
        self.viewer.browser.setPlaceholderText('Choose a Markdown note from the sidebar.')
        self.viewer.back_button.hide(); self.viewer.forward_button.hide()
        if remote:
            self.viewer.find_action.setVisible(False)
            self.viewer.find_action.setEnabled(False)
            self.viewer.find_action.setShortcuts([])
        self.tree = qt.QTreeWidget(); self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self.expand)
        self.tree.itemActivated.connect(self.choose)
        self.tree.itemClicked.connect(self.choose)
        self.search = None
        sidebar = qt.QWidget(); side = qt.QVBoxLayout(sidebar); side.setContentsMargins(0, 0, 0, 0)
        if not remote:
            self.search = qt.QLineEdit(); self.search.setPlaceholderText('Filter loaded notes')
            self.search.textChanged.connect(self.filter)
            side.addWidget(self.search)
        side.addWidget(self.tree)
        self.menu = qt.QToolButton(); self.menu.setText('☰'); self.menu.setAccessibleName('Browse Notes Library')
        self.menu.clicked.connect(lambda: sidebar.setVisible(not sidebar.isVisible()))
        self.back = reader_button(self, 'Previous note', icon='previous')
        self.forward = reader_button(self, 'Next note', icon='next')
        self.up = reader_button(self, 'Browse parent folder', icon='up')
        self.back.clicked.connect(lambda: self.navigate(-1)); self.forward.clicked.connect(lambda: self.navigate(1))
        self.up.clicked.connect(self.parent_folder)
        self.back.setEnabled(False); self.forward.setEnabled(False); self.up.setEnabled(False)
        controls = qt.QHBoxLayout()
        for button in (self.menu, self.back, self.forward, self.up):controls.addWidget(button)
        controls.addStretch()
        self.split = qt.QSplitter(); self.split.addWidget(sidebar); self.split.addWidget(self.viewer); self.split.setSizes([260, 740])
        self.progress = OperationProgress(self); self.progress.completed.connect(self.completed)
        body = qt.QWidget(); layout = qt.QVBoxLayout(body); layout.addLayout(controls)
        layout.addWidget(self.split, 1); layout.addWidget(self.progress); self.setCentralWidget(body)
        self.revoked.connect(self.retire)
        self.pending = ('initial',)
        def initial(report, cancelled):
            provider = factory()
            release = provider.acquire() if hasattr(provider, 'acquire') else lambda: None
            try:
                library = NotesLibrary(provider)
                with operation(provider, cancelled):rows = provider.list('', cancelled=cancelled)
                if vault_root(provider, '', rows) is None:
                    raise ValueError('This location has no .obsidian directory.')
                notes = library.visible_rows(rows)
                if cancelled():raise ValueError('Notes Library closed.')
                return provider, release, library, notes
            except BaseException:
                release()
                raise
        self.progress.start(initial, message='Opening Notes Library…')
        self.tree.setEnabled(False)

    def list_folder(self, path):
        if self.progress.busy or self.library is None or self.locked:return
        self.pending = ('folder', path)
        self.tree.setEnabled(False)
        self.progress.start(lambda report, cancelled: self.library.folders(path, cancelled=cancelled), message='Loading notes…')

    def expand(self, item):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory and path not in self.loaded:self.list_folder(path)

    def choose(self, item, *args):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if not directory:self.open_note(path)

    def open_note(self, path, *, remember=True, fragment='', index=None):
        if self.progress.busy or self.library is None or self.locked:return
        try:path = self.library.contained(path)
        except ValueError as error:
            self.viewer.status.setText(str(error));return
        self.viewer.speech.stop()
        self.pending = ('note', path, remember, fragment, index)
        self.tree.setEnabled(False)
        self.progress.start(lambda report, cancelled: self.library.read(path, cancelled=cancelled), message='Opening note…')

    def completed(self, result, error):
        kind, *values = self.pending
        if self.closing or self.locked:
            if kind == 'initial' and result:result[1]()
            self.close();self.idle.emit();return
        self.tree.setEnabled(True)
        if error:
            self.viewer.status.setText(error)
            self.idle.emit();return
        if kind == 'initial':
            self.provider, self.release, self.library, rows = result
            if getattr(self.provider, 'private', False) and hasattr(self.provider, 'context'):
                from features.rclone import session
                self.unsubscribe = session.on_forget(self.provider.context, self.revoked.emit)
                if session.credentials(self.provider.context) is None:
                    self.retire();return
            if not self.check_provider():return
            self.populate('', rows)
        elif kind == 'folder':
            if not self.check_provider():return
            self.populate(values[0], result)
        else:
            if not self.check_provider():return
            path, remember, fragment, index = values
            if remember:
                del self.history[self.index + 1:];self.history.append(path);self.index = len(self.history) - 1
            elif index is not None:self.index = index
            self.storage.path, self.storage.data = (self.provider.root / path).resolve(), result
            self.viewer.history.clear();self.viewer.history_index = -1
            self.viewer.open_document(self.storage.path, fragment=fragment)
            self.back.setEnabled(self.index > 0);self.forward.setEnabled(self.index < len(self.history) - 1)
            self.up.setEnabled(True)
        self.idle.emit()

    def check_provider(self):
        try:
            if hasattr(self.provider, '_check_active'):self.provider._check_active()
            return True
        except (OSError, ValueError):
            self.retire()
            return False

    def populate(self, path, rows):
        parent = self.items.get(path)
        if parent:parent.takeChildren()
        self.loaded.add(path)
        for row in rows:
            item = qt.QTreeWidgetItem([row['name']]);item.setData(0, qt.Qt.ItemDataRole.UserRole, (row['path'], row['directory']))
            self.items[row['path']] = item
            if row['directory']:item.setChildIndicatorPolicy(qt.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            (parent.addChild if parent else self.tree.addTopLevelItem)(item)
        if self.search:self.filter()

    def filter(self, *args):
        query = self.search.text().casefold()
        for path, item in self.items.items():
            _, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
            item.setHidden(not directory and query not in path.casefold())

    def navigate(self, offset):
        index = self.index + offset
        if 0 <= index < len(self.history):self.open_note(self.history[index], remember=False, index=index)

    def parent_folder(self):
        if self.index < 0:return
        parent = str(PurePosixPath(self.history[self.index]).parent)
        parent = '' if parent == '.' else parent
        self.split.widget(0).show()
        item = self.items.get(parent)
        if item:item.setExpanded(True);self.tree.scrollToItem(item)

    def clear_content(self):
        self.viewer.speech.stop()
        self.storage.data = b''; self.storage.path = None
        self.viewer._source_bytes = self.viewer._rich_source = self.viewer._rich_snapshot = None
        self.viewer._loaded_path = None
        self.viewer.document_title.setText('');self.viewer.location.clear()
        self.viewer.history.clear(); self.viewer.history_index = -1
        self.viewer.browser.clear(); self.viewer.editor.clear(); self.viewer.formatted_editor.clear()
        self.tree.clear(); self.items.clear(); self.history.clear(); self.loaded.clear()
        if self.search is not None:self.search.clear()

    def retire(self):
        self.locked = True
        self.progress.request_cancel()
        self.clear_content()
        self.setWindowTitle('Notes Library locked');self.setEnabled(False)
        if not self.progress.busy:self.close()

    def prepare_close(self):
        self.closing = True
        self.progress.request_cancel()
        return not self.progress.busy

    def closeEvent(self, event):
        if not self.prepare_close():event.ignore();return
        self.clear_content()
        self.unsubscribe();self.release()
        event.accept()


def open_notes(factory, label, *, remote=False):
    from commonUtils.ui.document_host import show_document
    from services.documents.ui.editors import retain
    window = NotesLibraryWindow(factory, label, remote=remote)
    retain(window)
    return show_document(window)
