"""Desktop library search, daily notes, connections and rooted file commands."""
import posixpath
from pathlib import PurePosixPath
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.search.providers import search_resources
from commonUtils.search.names import natural_name_key, search_terms
from commonUtils.runtime.operations import OperationCancelled
from features.text_editor import library_files


class LibraryPanels:
    def init_panels(self, side, controls):
        self.positions = {}
        self.folder_pages = {}
        self.aux_generation = 0
        self.aux_pending = None
        self.aux = OperationProgress(self)
        self.aux.completed.connect(self.aux_completed)
        self.connections_progress = OperationProgress(self)
        self.connections_progress.completed.connect(self.connections_completed)
        self.connections_generation = 0
        self.connections_pending = None
        self.aux_snapshot.connect(self.search_snapshot)
        self.search_rows = []
        self.search_shown = 50
        self.search_mode = qt.QComboBox()
        self.search_mode.addItems(['Search within Documents', 'Search in File Names'])
        self.search_mode.currentIndexChanged.connect(self.filter)
        if self.search is not None:
            self.search.setPlaceholderText('Search Notes Library')
        side.insertWidget(1, self.search_mode)
        self.search_results = qt.QTreeWidget()
        self.search_results.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
        self.search_results.header().setStretchLastSection(False)
        self.search_results.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.search_results.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
        self.search_results.setColumnWidth(3, 260)
        self.search_results.itemClicked.connect(self.choose_result)
        self.search_more = qt.QPushButton('Show more notes')
        self.search_more.clicked.connect(self.more_results)
        self.search_more.hide()
        self.search_notice = qt.QLabel()
        self.files_stack = qt.QStackedWidget()
        side.removeWidget(self.tree)
        self.files_stack.addWidget(self.tree)
        self.files_stack.addWidget(self.search_results)
        side.addWidget(self.files_stack, 1)
        side.addWidget(self.search_more)
        side.addWidget(self.search_notice)
        self.panel_tabs = qt.QTabWidget()
        files = qt.QWidget()
        files.setLayout(side)
        self.panel_tabs.addTab(files, 'Files')
        calendar = qt.QWidget()
        layout = qt.QVBoxLayout(calendar)
        self.calendar = qt.QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.clicked.connect(self.open_daily_note)
        self.calendar_notice = qt.QLabel('')
        self.calendar_notice.setWordWrap(True)
        refresh = qt.QPushButton('Refresh daily notes')
        refresh.clicked.connect(self.refresh_calendar)
        layout.addWidget(self.calendar)
        layout.addWidget(self.calendar_notice)
        layout.addWidget(refresh)
        layout.addStretch()
        self.calendar_entries = None
        self.panel_tabs.addTab(calendar, 'Calendar')
        self.panel_tabs.currentChanged.connect(self.panel_changed)
        self.links_tree = qt.QTreeWidget()
        self.links_tree.setHeaderHidden(True)
        self.links_tree.setMinimumWidth(220)
        self.links_tree.itemClicked.connect(self.choose_connection)
        self.links_tree.hide()
        self.links_button = qt.QPushButton('Links')
        self.links_button.setAccessibleName('Backlinks and outgoing links')
        self.links_button.clicked.connect(self.toggle_links)
        controls.addWidget(self.links_button)
        for tree in (self.tree, self.search_results):
            tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda point, tree=tree: self.file_actions(tree, point))

    def decorate_entry(self, item, path, directory):
        landing = directory and bool(self.folder_pages.get(path))
        kind = qt.QStyle.StandardPixmap.SP_DirIcon if directory else qt.QStyle.StandardPixmap.SP_FileIcon
        icon = self.style().standardIcon(kind)
        if landing:
            pixmap = icon.pixmap(24, 24)
            painter = qt.QPainter(pixmap)
            badge = self.style().standardIcon(qt.QStyle.StandardPixmap.SP_FileIcon).pixmap(14, 14)
            painter.drawPixmap(10, 10, badge)
            painter.end()
            icon = qt.QIcon(pixmap)
        item.setIcon(0, icon)
        item.setToolTip(0, ('Folder with same-named note' if landing else 'Folder' if directory else 'File')
                        + ' · ' + path)

    def request_aux(self, kind, work):
        self.aux_generation += 1
        self.aux_pending = (self.aux_generation, kind, work)
        self.aux.request_cancel()
        self.start_aux()

    def start_aux(self):
        if self.aux.busy or self.aux_pending is None or self.closing or self.locked:
            return
        generation, kind, work = self.aux_pending
        self.aux_pending = None
        self.aux_kind, self.aux_running = kind, generation
        self.aux.start(work, show_progress=False)

    def aux_completed(self, result, error):
        if self.closing or self.locked:
            self.close()
            return
        if self.aux_running == self.aux_generation and self.check_provider():
            if self.aux_kind == 'search':
                if error:
                    self.search_notice.setText(error)
                else:
                    self.search_snapshot(self.aux_running, result)
                    self.search_notice.setText('' if result.complete else 'Some items could not be searched.')
            elif self.aux_kind == 'calendar':
                self.calendar_entries = None if error else result
                self.calendar_notice.setText(error or 'Marked days have daily notes. Select a day to open or create one.')
                self.mark_daily_notes()
        self.start_aux()

    def cancel_aux(self):
        self.aux_generation += 1
        self.aux_pending = None
        self.aux.request_cancel()

    def filter(self, *args):
        if not hasattr(self, 'aux') or self.library is None or self.locked or self.closing:
            return
        # A debounced Files callback may arrive after Calendar was selected.
        # Tab switching owns cancellation; hidden search must not cancel its scan.
        if self.panel_tabs.currentIndex() != 0:
            return
        query = self.search.text() if self.search is not None else ''
        searching = bool(search_terms(query))
        self.files_stack.setCurrentWidget(self.search_results if searching else self.tree)
        self.search_more.hide()
        if not searching:
            self.cancel_aux()
            self.search_notice.clear()
            return
        library = self.library
        include_text = self.search_mode.currentIndex() == 0
        generation = self.aux_generation + 1
        self.search_notice.setText('Searching…')
        self.search_shown = 50
        def scan(report, cancelled):
            def listing(folder, *, cancelled):
                try:
                    return library.folders(folder, cancelled=cancelled)
                except ValueError as error:
                    if cancelled():
                        raise OperationCancelled() from error
                    raise OSError(str(error)) from error
            def read(path, *, cancelled):
                return library.read_text(path, cancelled=cancelled)
            return search_resources(library.provider, library.root, query, cancelled=cancelled,
                list_children=listing, read_text=read if include_text else None,
                progress=lambda result: self.aux_snapshot.emit(generation, result))
        self.request_aux('search', scan)

    def search_snapshot(self, generation, result):
        if generation != self.aux_generation or self.closing or self.locked:
            return
        self.search_rows = sorted(result.rows, key=lambda row: (row.get('content_match', False),
            natural_name_key(PurePosixPath(row['path']).name), natural_name_key(row['path'])))
        self.render_results()

    def render_results(self):
        self.search_results.clear()
        for row in self.search_rows[:self.search_shown]:
            from commonUtils.filesystem import format_size
            from services.documents.storage import display_path
            name = PurePosixPath(row['path']).name
            item = qt.QTreeWidgetItem([name, 'Folder' if row['directory'] else PurePosixPath(name).suffix.lstrip('.').upper() or 'File',
                '' if row['directory'] or row.get('size') is None else format_size(row['size']),
                display_path(self.provider, row['path'])])
            for column in range(4):
                item.setToolTip(column, item.text(column))
            item.setForeground(3, self.search_results.palette().brush(qt.QPalette.ColorRole.PlaceholderText))
            item.setData(0, qt.Qt.ItemDataRole.UserRole, (row['path'], row['directory']))
            self.decorate_entry(item, row['path'], row['directory'])
            self.search_results.addTopLevelItem(item)
        self.search_more.setVisible(len(self.search_rows) > self.search_shown)

    def more_results(self):
        self.search_shown += 50
        self.render_results()

    def choose_result(self, item, *args):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if directory:
            self.search.clear()
            self.filter()
            self.reveal_folder(path)
        else:
            self.open_note(path)

    def reveal_folder(self, path):
        self.reveal_path = path
        self.split.widget(0).show()
        self.panel_tabs.setCurrentIndex(0)
        parts = PurePosixPath(path).relative_to(self.library.root or '.').parts
        parent = self.library.root
        for part in parts:
            if parent not in self.loaded:
                self.list_folder(parent)
                return
            parent = posixpath.join(parent, part)
            item = self.items.get(parent)
            if item is not None:
                item.setExpanded(True)
            if self.progress.busy:
                return
        item = self.items.get(path)
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)
        self.reveal_path = None

    def panel_changed(self, index):
        self.cancel_aux()
        if index == 1:
            self.refresh_calendar()
        else:
            self.filter()

    def refresh_calendar(self, *args):
        if self.library is None or self.locked or self.closing or self.panel_tabs.currentIndex() != 1:
            return
        library = self.library
        self.calendar_entries = None
        self.calendar_notice.setText('Finding daily notes…')
        self.request_aux('calendar', lambda report, cancelled: library_files.daily_notes(library, cancelled=cancelled))

    def mark_daily_notes(self):
        self.calendar.setDateTextFormat(qt.QDate(), qt.QTextCharFormat())
        for key in self.calendar_entries or {}:
            style = qt.QTextCharFormat()
            style.setFontWeight(qt.QFont.Weight.Bold)
            style.setFontUnderline(True)
            self.calendar.setDateTextFormat(qt.QDate.fromString(key, 'yyyy-MM-dd'), style)

    def open_daily_note(self, day):
        if self.calendar_entries is None or self.progress.busy or self.locked:
            return
        key = day.toString('yyyy-MM-dd')
        paths = self.calendar_entries.get(key, [])
        if paths:
            path = paths[0]
            if len(paths) > 1:
                path, accepted = qt.QInputDialog.getItem(self, 'Choose daily note', key, paths, 0, False)
                if not accepted:
                    return
            self.open_note(path)
        elif not self.library.supports('create'):
            self.calendar_notice.setText('This library is read-only. Choose a day with an existing note.')
        elif qt.QMessageBox.question(self, 'Create daily note?',
                'Create ' + key + '.md in the Notes Library root?',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
                qt.QMessageBox.StandardButton.No) == qt.QMessageBox.StandardButton.Yes:
            self.mutate(lambda cancelled: self.library.create(key, self.library.root, cancelled=cancelled), created=True)

    def toggle_links(self):
        visible = not self.links_tree.isVisible()
        self.links_tree.setVisible(visible)
        if visible:
            left = self.split.sizes()[0]
            self.split.setSizes([left, max(300, self.split.width() - left - 260), 260])
            self.refresh_connections()
        else:
            self.cancel_connections()

    def cancel_connections(self):
        self.connections_generation += 1
        self.connections_pending = None
        self.connections_progress.request_cancel()

    def start_connections(self):
        if self.connections_progress.busy or self.connections_pending is None or self.closing or self.locked:
            return
        generation, work = self.connections_pending
        self.connections_pending = None
        self.connections_running = generation
        self.connections_progress.start(work, show_progress=False)

    def connections_completed(self, result, error):
        if self.closing or self.locked:
            self.close()
            return
        if self.connections_running == self.connections_generation and self.check_provider():
            self.render_connections(result, error)
        self.start_connections()

    def refresh_connections(self):
        if not self.links_tree.isVisible() or self.library is None or self.locked:
            return
        self.cancel_connections()
        self.links_tree.clear()
        if self.storage.path is None:
            self.links_tree.addTopLevelItem(qt.QTreeWidgetItem(['Open a Markdown note to see its connections.']))
            return
        library = self.library
        path = self.storage.path.relative_to(self.provider.root.resolve()).as_posix()
        self.links_tree.addTopLevelItem(qt.QTreeWidgetItem(['Finding local connections…']))
        from features.text_editor.notes_links import connections
        self.connections_pending = (self.connections_generation,
            lambda report, cancelled: connections(library, path, cancelled=cancelled))
        self.start_connections()

    def render_connections(self, result, error):
        self.links_tree.clear()
        if error:
            self.links_tree.addTopLevelItem(qt.QTreeWidgetItem([error]))
            return
        self.links_tree.addTopLevelItem(qt.QTreeWidgetItem([
            f"{result['words']:,} words · {result['characters']:,} characters"]))
        for key, label in [('incoming', 'Backlinks'), ('outgoing', 'Outgoing links'), ('unresolved', 'Unresolved links')]:
            section = qt.QTreeWidgetItem([f'{label} ({len(result[key])})'])
            self.links_tree.addTopLevelItem(section)
            for path in result[key]:
                item = qt.QTreeWidgetItem([path if key == 'unresolved' else posixpath.relpath(path, self.library.root or '.')])
                if key != 'unresolved':
                    item.setData(0, qt.Qt.ItemDataRole.UserRole, path)
                section.addChild(item)
            section.setExpanded(True)

    def choose_connection(self, item, *args):
        path = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if path:
            self.open_note(path)

    def file_actions(self, tree, point):
        if self.library is None or self.progress.busy or self.locked:
            return
        item = tree.itemAt(point)
        if item is None:
            return
        tree.setCurrentItem(item)
        path, _ = item.data(0, qt.Qt.ItemDataRole.UserRole)
        menu = qt.QMenu(self)
        if self.library.supports('rename'):
            menu.addAction('Move / rename…', lambda: self.rename_path(path))
        if all(self.library.supports(action) for action in ('create', 'rename', 'delete')):
            menu.addAction('Copy…', lambda: self.copy_entry(path))
        if self.library.supports('delete'):
            menu.addAction('Delete…', lambda: self.delete_entry(path))
        if not menu.isEmpty():
            menu.exec(tree.viewport().mapToGlobal(point))

    def rename_path(self, path):
        relative = posixpath.relpath(path, self.library.root or '.')
        destination, accepted = qt.QInputDialog.getText(self, 'Rename or move',
            'Path inside Notes Library (existing folders). Links are not rewritten.', text=relative)
        if accepted:
            self.move_entry(path, posixpath.join(self.library.root, destination))

    def copy_entry(self, path):
        destination, accepted = qt.QInputDialog.getText(self, 'Copy',
            'New path inside Notes Library (existing folders). Existing files are kept.',
            text=posixpath.relpath(path, self.library.root or '.'))
        if accepted:
            self.mutate(lambda cancelled: library_files.copy(self.library, path,
                posixpath.join(self.library.root, destination), cancelled=cancelled), leave=False)

    def delete_entry(self, path):
        if qt.QMessageBox.question(self, 'Delete ' + PurePosixPath(path).name + '?',
                'Permanently delete this item and its contents? Links are not rewritten.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
                qt.QMessageBox.StandardButton.No) == qt.QMessageBox.StandardButton.Yes:
            current = self.history[self.index] if self.index >= 0 else None
            leaving = current is not None and (current == path or current.startswith(path + '/'))
            self.mutate(lambda cancelled: (library_files.remove(self.library, path, cancelled=cancelled), path)[1],
                        deleted=path, leave=leaving)

    def remember_position(self):
        if self.storage.path is not None:
            path = self.storage.path.relative_to(self.provider.root.resolve()).as_posix()
            surface = self.viewer.active_editor() if self.viewer.edit_button.isChecked() else self.viewer.browser
            self.positions[path] = surface.verticalScrollBar().value()

    def restore_position(self, path):
        if path in self.positions:
            surface = self.viewer.active_editor() if self.viewer.edit_button.isChecked() else self.viewer.browser
            surface.verticalScrollBar().setValue(self.positions[path])
