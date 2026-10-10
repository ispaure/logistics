"""A palette-aware archive workspace, backed by shared Logistics workers."""
from pathlib import Path, PurePosixPath
import zipfile

from commonUtils.ui import pyside as qt
from commonUtils.ui.operation_progress import OperationProgress
from commonUtils.operations import OperationCancelled
from services.zip_passwords import resolve_password, is_password_error, remember_verified_password
from ui_new.dialogs.archive_password import ask_password
from .. import backend
from .create import NewArchiveDialog


FILTER = 'Supported archives (*.zip *.cbz *.tar *.tar.gz *.tgz *.tar.bz2 *.tbz2 *.tar.xz *.txz);;All files (*)'


def size_text(size):
    if size is None:
        return '—'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            return f'{size:,.0f} {unit}' if unit == 'B' else f'{size:,.1f} {unit}'
        size /= 1024


class ImagePreview(qt.QLabel):
    def __init__(self):
        super().__init__()
        self.original = None
        self.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(qt.QSizePolicy.Policy.Ignored, qt.QSizePolicy.Policy.Ignored)

    def set_preview(self, pixmap):
        self.original = pixmap
        self._scale()

    def _scale(self):
        if self.original is not None:
            self.setPixmap(self.original.scaled(self.size(), qt.Qt.AspectRatioMode.KeepAspectRatio,
                                               qt.Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale()

    def clear(self):
        self.original = None
        super().clear()


class ArchiveItem(qt.QTreeWidgetItem):
    def __lt__(self, other):
        column = self.treeWidget().sortColumn()
        left = self.data(0, qt.Qt.ItemDataRole.UserRole)
        right = other.data(0, qt.Qt.ItemDataRole.UserRole)
        if left and right and left[1] != right[1]:
            return left[1]
        if column in (1, 2, 3):
            role = int(qt.Qt.ItemDataRole.UserRole) + 1
            return (self.data(column, role) or 0) < (other.data(column, role) or 0)
        return self.text(column).casefold() < other.text(column).casefold()


class ArchivePage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 15)
        self.setObjectName('archiveWorkspace')
        self.setAcceptDrops(True)
        self.path = None
        self.members = ()
        self.folder = ''
        self.closing = False
        self._pending = None
        self._retry = None
        self._build()
        self._render()

    @property
    def busy(self):
        return self.task.busy

    def _build(self):
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        toolbar = qt.QHBoxLayout()
        self.commands = {}
        for key, title, icon, callback in [
            ('open', 'Open archive…', qt.QStyle.StandardPixmap.SP_DialogOpenButton, self.open_dialog),
            ('create', 'Create archive…', qt.QStyle.StandardPixmap.SP_FileDialogNewFolder, self.new_archive),
            ('extract', 'Extract all…', qt.QStyle.StandardPixmap.SP_ArrowDown, self.extract_all),
            ('selected', 'Extract selected…', qt.QStyle.StandardPixmap.SP_DirOpenIcon, self.extract_selected),
            ('test', 'Test integrity', qt.QStyle.StandardPixmap.SP_DialogApplyButton, self.test),
        ]:
            button = qt.QToolButton()
            button.setText(title)
            button.setAccessibleName(title)
            button.setToolTip(title)
            button.setIcon(self.style().standardIcon(icon))
            button.setIconSize(qt.QSize(24, 24))
            button.setToolButtonStyle(qt.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.clicked.connect(callback)
            self.commands[key] = button
            toolbar.addWidget(button)
        toolbar.addStretch()
        self.edit_menu = qt.QToolButton()
        self.edit_menu.setText('Edit ZIP')
        self.edit_menu.setAccessibleName('Edit ZIP archive')
        self.edit_menu.setPopupMode(qt.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = qt.QMenu(self.edit_menu)
        menu.addAction('Add files…', self.add_files)
        menu.addAction('Add folder…', self.add_folder)
        self.remove_action = menu.addAction('Remove selected entries…', self.remove_selected)
        self.edit_menu.setMenu(menu)
        toolbar.addWidget(self.edit_menu)
        layout.addLayout(toolbar)
        location_row = qt.QHBoxLayout()
        self.location = qt.QLineEdit()
        self.location.setPlaceholderText('Open an archive, paste its path, or drop it here')
        self.location.setAccessibleName('Archive path')
        self.location.returnPressed.connect(lambda: self.open_archive(self.location.text().strip()))
        location_row.addWidget(self.location, 1)
        self.reload = qt.QToolButton()
        self.reload.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_BrowserReload))
        self.reload.setToolTip('Reload archive')
        self.reload.setAccessibleName('Reload archive')
        self.reload.clicked.connect(self.refresh)
        location_row.addWidget(self.reload)
        layout.addLayout(location_row)
        self.summary = qt.QLabel('ARCHIVES  /  ZIP · AES ZIP · TAR · GZIP · XZ')
        self.summary.setTextFormat(qt.Qt.TextFormat.PlainText)
        layout.addWidget(self.summary)
        self.splitter = qt.QSplitter()
        self.folders = qt.QTreeWidget()
        self.folders.setHeaderLabel('Folders')
        self.folders.setMinimumWidth(140)
        self.folders.setAccessibleName('Archive folders')
        self.folders.itemSelectionChanged.connect(self._folder_selected)
        self.splitter.addWidget(self.folders)
        contents = qt.QWidget()
        content_layout = qt.QVBoxLayout(contents)
        content_layout.setContentsMargins(0, 0, 0, 0)
        row = qt.QHBoxLayout()
        self.up = qt.QToolButton()
        self.up.setIcon(self.style().standardIcon(qt.QStyle.StandardPixmap.SP_ArrowUp))
        self.up.setToolTip('Parent folder (Alt+Up)')
        self.up.setAccessibleName('Parent folder')
        self.up.clicked.connect(self._up)
        row.addWidget(self.up)
        self.breadcrumb = qt.QLabel('Archive contents')
        self.breadcrumb.setTextFormat(qt.Qt.TextFormat.PlainText)
        row.addWidget(self.breadcrumb, 1)
        self.search = qt.QLineEdit()
        self.search.setPlaceholderText('Search all entries…')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(180)
        self.search.setAccessibleName('Search archive entries')
        self.search.textChanged.connect(self._render)
        row.addWidget(self.search)
        content_layout.addLayout(row)
        self.files = qt.QTreeWidget()
        self.files.setHeaderLabels(['Name', 'Size', 'Packed', 'Saved', 'Modified', 'Protection'])
        self.files.setRootIsDecorated(False)
        self.files.setAlternatingRowColors(True)
        self.files.setSelectionMode(qt.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.files.setSortingEnabled(True)
        self.files.setAccessibleName('Archive entries')
        self.files.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        self.files.header().setSectionResizeMode(4, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.files.itemDoubleClicked.connect(self._activate)
        self.files.itemSelectionChanged.connect(self._selection)
        self.files.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._context_menu)
        content_layout.addWidget(self.files, 1)
        self.empty = qt.QLabel('<h1>Your archive workbench</h1>'
                              '<p>Explore, pack, protect and unpack your files.</p><br>'
                              '<p><b>ZIP for sharing · AES for privacy · TAR for Linux</b></p>'
                              '<p>Open an archive above, or drop files here to start a new one.</p>')
        self.empty.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        self.empty.setMargin(24)
        content_layout.addWidget(self.empty, 1)
        self.splitter.addWidget(contents)
        preview_panel = self.preview_panel = qt.QWidget()
        preview_layout = qt.QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.details = qt.QLabel('ENTRY DETAILS')
        self.details.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        preview_layout.addWidget(self.details)
        self.preview_button = qt.QPushButton('Preview file')
        self.preview_button.clicked.connect(self.preview_selected)
        preview_layout.addWidget(self.preview_button)
        self.preview_text = qt.QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText('Select a file for details. Preview text and images without extracting them.')
        self.preview_text.setAccessibleName('Archive text preview')
        preview_layout.addWidget(self.preview_text, 1)
        self.preview_image = ImagePreview()
        self.preview_image.setAlignment(qt.Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setAccessibleName('Archive image preview')
        self.image_scroll = qt.QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setWidget(self.preview_image)
        self.image_scroll.hide()
        preview_layout.addWidget(self.image_scroll, 1)
        self.splitter.addWidget(preview_panel)
        self.splitter.setSizes([180, 680, 250])
        layout.addWidget(self.splitter, 1)
        self.status = qt.QLabel('Ready. Sources and existing output files are preserved.')
        self.status.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.task = OperationProgress(self)
        self.task.completed.connect(self._completed)
        layout.addWidget(self.task)
        self.setStyleSheet('''
            QWidget#archiveWorkspace QToolButton { padding: 6px; }
            QWidget#archiveWorkspace QTreeWidget::item { padding: 3px 4px; margin: 0; }
            QWidget#archiveWorkspace QHeaderView::section { padding: 6px 4px; }
        ''')
        for key, callback in [('Ctrl+O', self.open_dialog), ('Ctrl+N', self.new_archive),
                              ('Alt+Up', self._up), ('Ctrl+F', self.search.setFocus), ('F5', self.refresh)]:
            shortcut = qt.QShortcut(qt.QKeySequence(key), self)
            shortcut.setContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(callback)

    def _enabled(self):
        available = bool(self.path) and not self.busy and not self.closing
        for key, button in self.commands.items():
            button.setEnabled(not self.busy and not self.closing if key in ('open', 'create') else available)
        selection = self.files.selectedItems()
        editable = available and str(self.path).lower().endswith(('.zip', '.cbz'))
        self.edit_menu.setEnabled(editable)
        self.remove_action.setEnabled(editable and bool(selection))
        self.commands['selected'].setEnabled(available and bool(selection))
        self.preview_button.setEnabled(available and len(selection) == 1 and not selection[0].data(0, qt.Qt.ItemDataRole.UserRole)[1])
        for widget in (self.location, self.reload, self.files, self.folders, self.search, self.up):
            widget.setEnabled(not self.busy and not self.closing)

    def open_dialog(self):
        if self.busy:
            return
        path, _ = qt.QFileDialog.getOpenFileName(self, 'Open archive', str(self.path or ''), FILTER)
        if path:
            self.open_archive(path)

    def open_archive(self, path):
        if self.busy or self.closing or not path:
            return
        candidate = Path(path).absolute()
        self._run('open', lambda progress, cancelled, password: backend.entries(candidate, progress=progress, cancelled=cancelled), candidate)

    def refresh(self):
        if self.path:
            self.open_archive(self.path)

    def _run(self, kind, work, path=None, *, unlock=False, password=None):
        if self.busy or self.closing:
            return
        path = path or self.path
        self._pending = kind, work, path, unlock
        self._retry = None
        def job(progress, cancelled):
            try:
                secret = resolve_password(path, password=password, cancelled=cancelled) if unlock and zipfile.is_zipfile(path) else password
                result = work(progress, cancelled, secret)
                if kind in ('edit', 'create') and result is not None and secret:
                    remember_verified_password(result, secret)
                return result
            except OperationCancelled:
                return None
        self.task.start(job, message={'open': 'Reading archive headers…', 'create': 'Creating and verifying archive…',
                                      'extract': 'Preparing extraction…', 'test': 'Checking every entry…',
                                      'preview': 'Reading preview…', 'edit': 'Rebuilding and verifying ZIP…'}[kind])
        self.status.setText(self.task.message.text())
        self._enabled()

    def _completed(self, result, error):
        kind, work, path, unlock = self._pending
        self._pending = None
        self.task.hide()
        if error and unlock and is_password_error(error) and not self.closing:
            password = ask_password(path, error, self)
            if password is not None:
                # Keep shutdown aware of a retry queued after the worker's finish signal.
                self._retry = (kind, work, path, unlock, password)
                qt.QTimer.singleShot(0, self, self._retry_job)
                return
        if error:
            self.status.setText(f'Operation failed: {error}')
        elif result is None:
            self.status.setText('Cancelled. No output was published.')
        elif kind == 'open':
            self.path, self.members = path, result
            self.folder = ''
            self.location.setText(str(path))
            self.preview_text.clear()
            self.search.clear()
            self._build_folders()
            self._render()
            files = [entry for entry in result if not entry.directory]
            try:
                packed = path.stat().st_size
            except OSError:
                packed = 0
            self.summary.setText(f'{path.name}  /  {len(files):,} files  /  {size_text(sum(entry.size for entry in files))} unpacked  /  {size_text(packed)} archive'
                                 + ('  /  Encrypted' if any(entry.encrypted for entry in result) else ''))
            self.status.setText('Archive opened. Double-click folders to explore; select files to extract or preview.')
        elif kind == 'preview':
            if isinstance(result, bytes):
                pixmap = qt.QPixmap()
                pixmap.loadFromData(result, 'PNG')
                self.preview_image.set_preview(pixmap)
                self.preview_text.hide()
                self.image_scroll.show()
            else:
                self.preview_text.setPlainText(result)
                self.preview_text.show()
                self.image_scroll.hide()
            self.status.setText('Preview ready.')
        elif kind == 'test':
            self.status.setText(f'Integrity check passed: {result:,} entries read successfully.'
                                + (' TAR has no per-entry checksums.' if not zipfile.is_zipfile(path) else ''))
        elif kind == 'extract':
            self.status.setText(f'Extracted to {result}')
        elif kind in ('create', 'edit'):
            self.status.setText(f'Archive verified and saved: {result}')
            if not self.closing:
                qt.QTimer.singleShot(0, self, lambda: self.open_archive(result))
        self._enabled()
        self.idle.emit()

    def _retry_job(self):
        retry, self._retry = self._retry, None
        if retry and not self.closing:
            kind, work, path, unlock, password = retry
            self._run(kind, work, path, unlock=unlock, password=password)
        else:
            self._enabled()
            self.idle.emit()

    def _build_folders(self):
        self.folders.blockSignals(True)
        self.folders.clear()
        root = qt.QTreeWidgetItem(self.folders, ['All contents'])
        root.setData(0, qt.Qt.ItemDataRole.UserRole, '')
        nodes = {'': root}
        folder_names = set()
        for entry in self.members:
            parts = PurePosixPath(entry.name).parts
            for i in range(1, len(parts) + (1 if entry.directory else 0)):
                folder_names.add('/'.join(parts[:i]) + '/')
        for folder in sorted(folder_names):
            parent = folder.rstrip('/').rsplit('/', 1)[0] + '/' if '/' in folder.rstrip('/') else ''
            node = qt.QTreeWidgetItem(nodes[parent], [PurePosixPath(folder).name])
            node.setData(0, qt.Qt.ItemDataRole.UserRole, folder)
            node.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon))
            nodes[folder] = node
        root.setExpanded(True)
        self.folders.setCurrentItem(root)
        self._folder_nodes = nodes
        self.folders.blockSignals(False)

    def _folder_selected(self):
        item = self.folders.currentItem()
        if item:
            self.folder = item.data(0, qt.Qt.ItemDataRole.UserRole)
            self.search.clear()
            self._render()

    def _render(self):
        query = self.search.text().casefold().strip()
        self.files.setSortingEnabled(False)
        self.files.clear()
        rows = {}
        for entry in self.members:
            if query:
                if query not in entry.name.casefold():
                    continue
                name, directory = entry.name, entry.directory
            else:
                if not entry.name.startswith(self.folder):
                    continue
                relative = entry.name[len(self.folder):].rstrip('/')
                if not relative:
                    continue
                name = relative.split('/')[0]
                directory = '/' in relative or entry.directory
            full_name = (name if query else self.folder + name) + ('/' if directory and not name.endswith('/') else '')
            if full_name in rows:
                continue
            exact = not directory or entry.name.rstrip('/') == full_name.rstrip('/')
            size, packed = (entry.size, entry.packed) if exact and not directory else (None, None)
            saved = f'{(1 - packed / size) * 100:.0f}%' if size and packed is not None else '—'
            item = ArchiveItem(self.files, [name.rstrip('/'), size_text(size), size_text(packed), saved,
                                                  entry.modified if exact else '', 'Encrypted' if exact and entry.encrypted else ''])
            item.setData(0, qt.Qt.ItemDataRole.UserRole, (full_name, directory))
            role = int(qt.Qt.ItemDataRole.UserRole) + 1
            for column, value in ((1, size), (2, packed), (3, (1 - packed / size) if size and packed is not None else 0)):
                item.setData(column, role, value)
            item.setIcon(0, self.style().standardIcon(qt.QStyle.StandardPixmap.SP_DirIcon if directory else qt.QStyle.StandardPixmap.SP_FileIcon))
            item.setToolTip(0, full_name)
            rows[full_name] = item
        self.files.setSortingEnabled(True)
        self.files.sortItems(0, qt.Qt.SortOrder.AscendingOrder)
        self.breadcrumb.setText('Search results' if query else '/ ' + self.folder)
        self.empty.setVisible(not self.path)
        self.folders.setVisible(bool(self.path))
        self.preview_panel.setVisible(bool(self.path))
        self.search.setVisible(bool(self.path))
        self.breadcrumb.setVisible(bool(self.path))
        self.up.setVisible(bool(self.path))
        self.files.setVisible(bool(self.path))
        self._selection()

    def _context_menu(self, position):
        if not self.files.selectedItems() or self.busy:
            return
        menu = qt.QMenu(self)
        if self.preview_button.isEnabled():
            menu.addAction('Preview file', self.preview_selected)
        menu.addAction('Extract selected…', self.extract_selected)
        if self.remove_action.isEnabled():
            menu.addSeparator()
            menu.addAction('Remove from ZIP…', self.remove_selected)
        menu.exec(self.files.viewport().mapToGlobal(position))

    def _activate(self, item, column=0):
        name, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory:
            self.folders.setCurrentItem(self._folder_nodes[name])
        else:
            self.preview_selected()

    def _up(self):
        if self.folder and not self.busy:
            parent = self.folder.rstrip('/').rsplit('/', 1)[0] + '/' if '/' in self.folder.rstrip('/') else ''
            self.folders.setCurrentItem(self._folder_nodes[parent])

    def _selection(self):
        selection = self.files.selectedItems()
        self.preview_text.clear()
        self.preview_image.clear()
        self.image_scroll.hide()
        self.preview_text.show()
        if len(selection) == 1:
            name, directory = selection[0].data(0, qt.Qt.ItemDataRole.UserRole)
            entry = next((entry for entry in self.members if entry.name.rstrip('/') == name.rstrip('/')), None)
            details = f'{"FOLDER" if directory else "FILE"}\n{name}'
            if entry and not directory:
                details += f'\n\nSize: {size_text(entry.size)}\nPacked: {size_text(entry.packed)}\nModified: {entry.modified}'
                details += '\nProtection: ' + ('Encrypted' if entry.encrypted else 'None')
            self.details.setText(details)
        else:
            self.details.setText(f'{len(selection)} entries selected' if selection else 'ENTRY DETAILS')
        self._enabled()

    def _extract(self, selected=None):
        if self.busy or not self.path:
            return
        base = qt.QFileDialog.getExistingDirectory(self, 'Choose parent folder for extraction', str(self.path.parent))
        if not base:
            return
        name, accepted = qt.QInputDialog.getText(self, 'Extract archive', 'New destination folder name (existing folders are kept):',
                                                qt.QLineEdit.EchoMode.Normal, self.path.stem + '-extracted')
        if not accepted:
            return
        if not name.strip() or name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
            self.status.setText('Enter a single, nonempty folder name.')
            return
        destination = Path(base) / name.strip()
        path = self.path
        self._run('extract', lambda progress, cancelled, password: backend.extract(path, destination, selected=selected,
                  password=password, progress=progress, cancelled=cancelled), unlock=True)

    def extract_all(self):
        self._extract()

    def extract_selected(self):
        selected = [item.data(0, qt.Qt.ItemDataRole.UserRole)[0] for item in self.files.selectedItems()]
        if selected:
            self._extract(selected)

    def test(self):
        if self.path:
            path = self.path
            self._run('test', lambda progress, cancelled, password: backend.test_archive(path, password=password,
                       progress=progress, cancelled=cancelled), unlock=True)

    def preview_selected(self):
        selection = self.files.selectedItems()
        if len(selection) == 1:
            name, directory = selection[0].data(0, qt.Qt.ItemDataRole.UserRole)
            if not directory:
                path = self.path
                preview = backend.preview_image if PurePosixPath(name).suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tif', '.tiff') else backend.preview
                self._run('preview', lambda progress, cancelled, password: preview(path, name, password=password,
                            progress=progress, cancelled=cancelled), unlock=True)

    def new_archive(self, checked=False, sources=()):
        if self.busy or self.closing:
            return
        dialog = NewArchiveDialog(sources, self)
        try:
            if dialog.exec() != qt.QDialog.DialogCode.Accepted:
                return
            options = dialog.options()
        finally:
            dialog.deleteLater()
        self._run('create', lambda progress, cancelled, password: backend.create(**options, progress=progress, cancelled=cancelled),
                  options['destination'], password=options['password'])

    def _edit(self, sources=(), remove=()):
        if self.busy or not self.path:
            return
        path = self.path
        self._run('edit', lambda progress, cancelled, password: backend.update_zip(path, sources=sources,
                  remove=remove, password=password, progress=progress, cancelled=cancelled), unlock=True)

    def add_files(self):
        paths, _ = qt.QFileDialog.getOpenFileNames(self, 'Add files to ZIP')
        if paths:
            self._edit(sources=paths)

    def add_folder(self):
        path = qt.QFileDialog.getExistingDirectory(self, 'Add folder to ZIP')
        if path:
            self._edit(sources=[path])

    def remove_selected(self):
        selected = [item.data(0, qt.Qt.ItemDataRole.UserRole)[0] for item in self.files.selectedItems()]
        if not selected:
            return
        question = qt.QMessageBox(self)
        question.setWindowTitle('Remove archive entries')
        question.setTextFormat(qt.Qt.TextFormat.PlainText)
        question.setText(f'Remove {len(selected)} selected entries from {self.path.name}?')
        question.setInformativeText('Selected folders include all their contents. The ZIP is rebuilt and verified before saving.')
        question.setDetailedText('\n'.join(selected))
        question.setStandardButtons(qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel)
        question.setDefaultButton(qt.QMessageBox.StandardButton.Cancel)
        if question.exec() == qt.QMessageBox.StandardButton.Yes:
            self._edit(remove=selected)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and not self.busy and not self.closing and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths or self.busy or self.closing:
            return
        event.acceptProposedAction()
        if len(paths) == 1 and paths[0].is_file() and any(str(paths[0]).lower().endswith(ext) for ext in
                ('.zip', '.cbz', '.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2', '.tbz2')):
            self.open_archive(paths[0])
        else:
            self.new_archive(sources=paths)

    def can_close(self):
        return True

    def prepare_close(self):
        self.closing = True
        self._retry = None
        if self.busy:
            self.task.request_cancel()
            return False
        return True
