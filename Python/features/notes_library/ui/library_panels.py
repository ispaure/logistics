"""Desktop library search, daily notes, connections and rooted file commands."""
import posixpath
from pathlib import PurePosixPath
from commonUtils.ui import pyside as qt
from commonUtils.ui.tasks.operation_progress import OperationProgress
from commonUtils.search.providers import search_resources
from commonUtils.search.names import natural_name_key, search_terms
from commonUtils.runtime.operations import OperationCancelled
from features.notes_library import library_files
from .library_icons import entry_icon
from .library_connections import LibraryConnections


class SearchNotice(qt.QLabel):
    """Reserve a sidebar row only while there is a search message."""
    changed = qt.Signal()
    def __init__(self):
        super().__init__()
        self.hide()

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))
        self.changed.emit()

    def clear(self):
        self.setText('')


class FolderPageTree(qt.QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.position().toPoint())
        point = event.position().toPoint()
        linked_folder = (item is not None and item.font(0).underline()
                         and self.columnAt(point.x()) == 0 and self.visualItemRect(item).contains(point))
        self.viewport().setCursor(qt.Qt.CursorShape.PointingHandCursor if linked_folder
                                  else qt.Qt.CursorShape.ArrowCursor)


class LibrarySearchTree(FolderPageTree):
    def keyPressEvent(self, event):
        if event.key() in (qt.Qt.Key.Key_Return, qt.Qt.Key.Key_Enter) and self.currentItem() is not None:
            self.itemActivated.emit(self.currentItem(), self.currentColumn())
            event.accept()
            return
        super().keyPressEvent(event)


class LibraryPanels(LibraryConnections):
    def init_panels(self, side, controls):
        qt.QApplication.instance().paletteChanged.connect(self.refresh_entry_icons)
        self.positions = {}
        self.folder_pages = {}
        self.aux_generation = 0
        self.aux_pending = None
        self.aux = OperationProgress(self)
        self.aux.completed.connect(self.aux_completed)
        self.aux_snapshot.connect(self.search_snapshot)
        self.search_mode = qt.QComboBox()
        self.search_mode.addItems(['Search within Documents', 'Search in File Names'])
        self.search_inputs = qt.QStackedWidget()
        self.search_footers = qt.QStackedWidget()
        self.files_stack = qt.QStackedWidget()
        side.removeWidget(self.tree)
        self.files_stack.addWidget(self.tree)
        self._search_interfaces = []
        first_input = self.search
        if first_input is not None:
            side.removeWidget(first_input)
        for index, placeholder in enumerate(('Search in documents', 'Search file names')):
            control = first_input if index == 0 else qt.QLineEdit() if first_input is not None else None
            if control is not None:
                control.setPlaceholderText(placeholder)
                if index:
                    qt.connect_search(control, lambda control=control: self.filter_search_input(control))
            self.search_inputs.addWidget(control if control is not None else qt.QWidget())
            results = LibrarySearchTree()
            results.setHeaderLabels(['Name', 'Type', 'Size', 'Path'])
            results.header().setStretchLastSection(False)
            results.header().setSectionResizeMode(0, qt.QHeaderView.ResizeMode.Stretch)
            for column in (1, 2):
                results.header().setSectionResizeMode(column, qt.QHeaderView.ResizeMode.ResizeToContents)
            results.setColumnWidth(3, 260)
            results.itemClicked.connect(self.choose_result)
            results.itemActivated.connect(self.choose_result)
            more = qt.QPushButton('Show more notes')
            more.clicked.connect(lambda checked=False, index=index:
                self.more_results() if self._search_scope == index else None)
            more.hide()
            notice = SearchNotice()
            notice.changed.connect(lambda index=index:
                self.sync_search_footer() if self._search_scope == index else None)
            footer = qt.QWidget()
            footer_layout = qt.QVBoxLayout(footer)
            footer_layout.setContentsMargins(0, 0, 0, 0)
            footer_layout.addWidget(more)
            footer_layout.addWidget(notice)
            self.search_footers.addWidget(footer)
            self.files_stack.addWidget(results)
            self._search_interfaces.append(dict(search=control, search_results=results,
                search_more=more, search_notice=notice, search_rows=[], search_shown=50,
                search_query=None, search_paused=False))
        self._search_scope = 0
        for name, value in self._search_interfaces[0].items():
            setattr(self, name, value)
        self.search_mode.currentIndexChanged.connect(self.select_search_scope)
        side.insertWidget(0, self.search_mode)
        side.insertWidget(1, self.search_inputs)
        side.addWidget(self.files_stack, 1)
        side.addWidget(self.search_footers)
        self.search_footers.hide()
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
        self.init_connections()
        self.document_saved.connect(self.invalidate_search_interfaces)
        for tree in (self.tree, *(state['search_results'] for state in self._search_interfaces)):
            tree.setContextMenuPolicy(qt.Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda point, tree=tree: self.file_actions(tree, point))

    def remember_search_interface(self):
        state = self._search_interfaces[self._search_scope]
        for name in tuple(state):
            state[name] = getattr(self, name)

    def filter_search_input(self, control):
        # A hidden field can still have a queued debounce callback.
        if control is self.search:
            self.filter()

    def select_search_scope(self, index):
        active = self.panel_tabs.currentIndex() == 0
        if active:
            self.cancel_aux()
        self.remember_search_interface()
        self._search_scope = index
        for name, value in self._search_interfaces[index].items():
            setattr(self, name, value)
        self.search_inputs.setCurrentIndex(index)
        self.search_footers.setCurrentIndex(index)
        searching = self.search is not None and bool(search_terms(self.search.text()))
        self.files_stack.setCurrentWidget(self.search_results if searching else self.tree)
        self.sync_search_footer()
        if active:
            self.resume_search_interface()

    def resume_search_interface(self):
        query = self.search.text() if self.search is not None else ''
        if self.search_paused or self.search_query != query:
            self.filter()

    def invalidate_search_interfaces(self):
        for state in self._search_interfaces:
            state['search_query'] = None
        self.search_query = None

    def clear_search_interfaces(self):
        for state in self._search_interfaces:
            state['search_results'].clear()
            state['search_rows'].clear()
            state['search_notice'].clear()
            state['search_more'].hide()
            state['search_query'] = None
            state['search_paused'] = False
            if state['search'] is not None:
                with qt.QSignalBlocker(state['search']):
                    state['search'].clear()
        self.search_rows = []
        self.search_query = None
        self.search_paused = False
        self.search_footers.hide()

    def sync_search_footer(self):
        self.search_footers.setVisible(bool(self.search_notice.text())
            or len(self.search_rows) > self.search_shown)

    def decorate_entry(self, item, path, directory):
        landing = directory and bool(self.folder_pages.get(path))
        item.setIcon(0, entry_icon(directory, landing_page=landing))
        font = item.font(0)
        font.setUnderline(landing)
        item.setFont(0, font)
        item.setToolTip(0, ('Folder with same-named note' if landing else 'Folder' if directory else 'File')
                        + ' · ' + path)

    def refresh_entry_icons(self, *args):
        for tree in (self.tree, *(state['search_results'] for state in self._search_interfaces)):
            iterator = qt.QTreeWidgetItemIterator(tree)
            while iterator.value() is not None:
                item = iterator.value()
                entry = item.data(0, qt.Qt.ItemDataRole.UserRole)
                if entry:
                    path, directory = entry
                    self.decorate_entry(item, path, directory)
                iterator += 1

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
                self.search_query = self._search_running_query
                self.search_paused = False
                self.sync_search_footer()
            elif self.aux_kind == 'calendar':
                self.calendar_entries = None if error else result
                self.calendar_notice.setText(error or 'Marked days have daily notes. Select a day to open or create one.')
                self.mark_daily_notes()
        self.start_aux()

    def cancel_aux(self):
        if ((self.aux.busy and getattr(self, 'aux_kind', None) == 'search'
                and self.aux_running == self.aux_generation)
                or (self.aux_pending is not None and self.aux_pending[1] == 'search')):
            self.search_paused = True
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
            self.search_rows = []
            self.search_results.clear()
            self.search_query = ''
            self.search_paused = False
            self.sync_search_footer()
            return
        library = self.library
        include_text = self.search_mode.currentIndex() == 0
        generation = self.aux_generation + 1
        self._search_running_query = query
        self.search_query = None
        self.search_paused = False
        self.search_notice.setText('Searching…')
        self.sync_search_footer()
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
        self.sync_search_footer()

    def more_results(self):
        self.search_shown += 50
        self.render_results()

    def choose_result(self, item, *args):
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        page = self.folder_pages.get(path) if directory else None
        if page:
            self.open_note(page)
        elif directory:
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
            self.resume_search_interface()

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

    def selected_file_actions(self):
        tree = self.search_results if self.files_stack.currentWidget() is self.search_results else self.tree
        item = tree.currentItem()
        if item is None:
            self.viewer.status.setText('Select a file or folder first.')
            return
        self.file_actions(tree, tree.visualItemRect(item).center())

    def file_actions(self, tree, point):
        if self.library is None or self.progress.busy or self.locked:
            return
        item = tree.itemAt(point)
        if item is None:
            return
        tree.setCurrentItem(item)
        path, directory = item.data(0, qt.Qt.ItemDataRole.UserRole)
        if path == self.library.root:
            self.viewer.status.setText('The library root is a drop destination. Select one of its files or folders for actions.')
            return
        menu = qt.QMenu(self)
        if not directory and getattr(self, 'document_tabs', None) is not None:
            menu.addAction('Open in new tab', lambda: self.open_note(path, new_tab=True))
        if self.library.supports('rename'):
            menu.addAction('Rename…', lambda: self.rename_path(path))
            menu.addAction('Move…', lambda: self.move_path(path))
        if all(self.library.supports(action) for action in ('create', 'rename', 'delete')):
            menu.addAction('Copy…', lambda: self.copy_entry(path))
        if self.library.supports('delete'):
            menu.addAction('Delete…', lambda: self.delete_entry(path))
        if not menu.isEmpty():
            menu.exec(tree.viewport().mapToGlobal(point))

    def rename_path(self, path):
        name, accepted = qt.QInputDialog.getText(self, 'Rename',
            'Name. Links are not rewritten.', text=PurePosixPath(path).name)
        if accepted:
            self.rename_tree_entry(path, name)

    def move_path(self, path):
        from commonUtils.ui.resources.picker import choose_resource
        projection = library_files.LibraryFolderProvider(self.library, exclude=path)
        choice = choose_resource([('Notes Library', lambda: (projection,
            projection.acquire() if hasattr(projection, 'acquire') else lambda: None))],
            parent=self, mode='folder')
        if choice is not None:
            try:
                destination = posixpath.join(projection.library_path(choice.path), PurePosixPath(path).name)
                if destination != path:
                    self.move_entry(path, destination)
            finally:
                choice.close()

    def copy_entry(self, path):
        from services.documents.mutations import copy_path
        default = posixpath.relpath(copy_path(path, directory=self.library.provider.entry(path)['directory']), self.library.root or '.')
        destination, accepted = qt.QInputDialog.getText(self, 'Copy',
            'Copy beside the source, or choose another path. Existing files are kept.',
            text=default)
        if accepted:
            self.mutate(lambda cancelled: library_files.copy(self.library, path,
                None if destination == default else posixpath.join(self.library.root, destination), cancelled=cancelled), leave=False)

    def delete_entry(self, path):
        if qt.QMessageBox.question(self, 'Delete ' + PurePosixPath(path).name + '?',
                'Permanently delete this item and its contents? Links are not rewritten.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.No,
                qt.QMessageBox.StandardButton.No) == qt.QMessageBox.StandardButton.Yes:
            current = self.history[self.index] if self.index >= 0 else None
            leaving = current is not None and (current == path or current.startswith(path + '/'))
            self.mutate(lambda cancelled: (library_files.remove(self.library, path, cancelled=cancelled), path)[1],
                        deleted=path, leave=leaving)
