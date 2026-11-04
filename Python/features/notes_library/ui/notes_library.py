"""A lazy Notes Library document over local, encrypted or remote providers."""
from pathlib import PurePosixPath
from commonUtils.ui import pyside as qt
from features.notes_library.notes import NotesLibrary, operation
from .library_panels import LibraryPanels, FolderPageTree
from ..navigation import PathChange, MutationResult
from .document import DocumentPresentation


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


class NotesLibraryWindow(LibraryPanels, DocumentPresentation, qt.QMainWindow):
    idle = qt.Signal()
    document_saved = qt.Signal()
    revoked = qt.Signal()
    aux_snapshot = qt.Signal(int, object)

    def __init__(self, factory, label, *, remote=False, root=""):
        super().__init__()
        self.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.library_label = label
        self.setWindowTitle('Notes Library — ' + label)
        self.resize(1000, 750)
        self.init_document(remote=remote)
        self.items, self.loaded = {}, set()
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
        from commonUtils.ui.appearance.icons import set_painted_icon
        from .library_icons import ActionArtwork
        self.new_note_button = qt.QToolButton()
        self.new_folder_button = qt.QToolButton()
        self.collapse_button = qt.QToolButton()
        for button, icon, label in ((self.new_note_button, 'edit', 'New document'),
                                    (self.new_folder_button, 'folder_add', 'New folder'),
                                    (self.collapse_button, 'collapse', 'Collapse all folders')):
            set_painted_icon(button, ActionArtwork, icon)
            button.setAccessibleName(label)
            button.setToolTip(label)
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        self.rename_button = qt.QPushButton('Rename…')
        self.file_actions_button = qt.QToolButton()
        self.file_actions_button.setText('…')
        self.file_actions_button.setAccessibleName('Selection actions')
        self.file_actions_button.setToolTip('Move, copy or delete the selected file or folder')
        self.file_actions_button.clicked.connect(self.selected_file_actions)
        self.new_note_button.clicked.connect(self.new_note)
        self.new_folder_button.clicked.connect(lambda: self.new_entry(folder=True))
        self.rename_button.clicked.connect(self.rename_entry)
        note_controls.addStretch()
        for button in (self.new_note_button, self.new_folder_button, self.collapse_button, self.rename_button, self.file_actions_button):
            note_controls.addWidget(button)
        note_controls.addStretch()
        self.note_controls.setVisible(not remote)
        side.addWidget(self.note_controls)
        side.addWidget(self.tree)
        self.menu = qt.QToolButton()
        self.menu.setText('▤')
        self.menu.setAccessibleName('Browse Notes Library')
        self.menu.hide()
        self.init_panels(side, self.document_controls)
        self.split = qt.QSplitter()
        self.split.addWidget(self.panel_tabs)
        self.split.addWidget(self.document_stack)
        self.split.addWidget(self.links_panel)
        self.split.setStretchFactor(1, 1)
        self.split.setCollapsible(0, False)
        self.split.setSizes([260, 740])
        body = qt.QWidget()
        layout = qt.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.controls_bar)
        layout.addWidget(self.split, 1)
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


    def refresh_document_entries(self):
        self.refresh_entry_icons()

    def set_navigation_enabled(self, enabled):
        self.tree.setEnabled(enabled)
        self.note_controls.setEnabled(enabled)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_connections()

    def show_sidebar(self, visible):
        self.panel_tabs.setVisible(True)
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


    def completed(self, result, error):
        kind, *values = self.pending
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
            self.complete_save(values, error)
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
            self.library.connection_index.invalidate()
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
            elif self.links_panel.isVisible():
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
            self.publish_note(values, result)
        self.idle.emit()

    def selected_parent(self):
        tree = self.search_results if self.files_stack.currentWidget() is self.search_results else self.tree
        item = tree.currentItem()
        if item is None:
            return self.library.root
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        parent = path if directory else str(PurePosixPath(path).parent)
        return '' if parent == '.' else parent


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
        self.rename_path(path)

    def move_entry(self, source, destination):
        if self.library is None or not self.library.supports('rename'):
            return
        self.mutate(lambda cancelled: self.library.move(source, destination, cancelled=cancelled), source=source)

    def rename_tree_entry(self, source, name):
        if name == PurePosixPath(source).name:
            return
        from ..library_files import renamed_path
        try:
            destination = renamed_path(source, name)
        except ValueError as error:
            self.viewer.status.setText(str(error))
            return
        self.move_entry(source, destination)

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


    def parent_folder(self):
        if self.index < 0:
            return
        parent = str(PurePosixPath(self.history[self.index]).parent)
        parent = '' if parent == '.' else parent
        self.reveal_folder(parent)


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
        self.backlinks_tree.clear()
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
