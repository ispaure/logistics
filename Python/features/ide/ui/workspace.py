"""Project-scoped documents, non-detachable groups and cooperative workers."""
from collections import Counter, deque
from dataclasses import replace
from typing import Callable, NamedTuple
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine
from commonUtils.ui.tasks.operations import ResultWorker
from commonUtils.ui.code_editor.search import SearchPanel
from commonUtils.ui.workspaces.scoped_tabs import ScopedTabBar
from commonUtils.persistence.text import read_text_file
from features.ide.ui.documents import EditorDocument
from features.ide.ui.browser import ProjectBrowser
from features.ide.ui.navigation import Navigation
from features.ide.ui.autosave import pause_autosave


class _FileTabBar(ScopedTabBar):
    def tabInserted(self, index):
        super().tabInserted(index)
        button = self.tabButton(index, qt.QTabBar.ButtonPosition.RightSide)
        if button is not None:
            button.setFixedSize(20, 20)
            button.setIconSize(qt.QSize(16, 16))


class _OpenTarget(NamedTuple):
    """Captured destination intent; groups are revalidated when a read completes."""
    path: Path
    group: qt.QTabWidget | None
    explicit_group: bool
    position: int | None
    on_open: Callable[[qt.QWidget], object] | None


class _RestoreFile(NamedTuple):
    path: Path
    cursor: int
    scroll: int | None
    record: dict

    @classmethod
    def decode(cls, record, group=None):
        if not isinstance(record, dict) or not isinstance(record.get('path'), str):
            return None
        cursor = record.get('cursor', 0)
        scroll = record.get('scroll', 0)
        retained = dict(record) if group is None else dict(record, group=group)
        return cls(Path(record['path']), max(0, cursor) if isinstance(cursor, int) else 0,
                   scroll if isinstance(scroll, int) else None, retained)


class _RestoreGroup(NamedTuple):
    active: Path | None
    files: tuple[_RestoreFile | None, ...]


class _RestorePlan(NamedTuple):
    """Decoded workspace state shared by file opens and delayed layout restore."""

    browser: object
    groups: tuple[_RestoreGroup, ...]
    unavailable: tuple[tuple[int, _RestoreFile], ...]
    active_group: int
    splitter: tuple[int, ...]
    editors: tuple[int, ...]

    @classmethod
    def decode(cls, state):
        def records(value):
            return value if isinstance(value, list) else []

        def group_index(value):
            return value if isinstance(value, int) and 0 <= value < 3 else 0

        def widths(key):
            sizes = records(state.get(key))
            if all(isinstance(n, int) and n >= 0 for n in sizes) and any(sizes):
                return tuple(sizes)
            return ()

        groups = []
        for index, entry in enumerate(records(state.get('groups'))[:3]):
            if not isinstance(entry, dict):
                entry = {}
            active = entry.get('active')
            # Keep slots for the open limit. Later entries can still supply scroll
            # positions for a file already open in this group.
            files = tuple(_RestoreFile.decode(record, index) for record in records(entry.get('files')))
            groups.append(_RestoreGroup(Path(active) if isinstance(active, str) else None, files))

        unavailable = []
        for record in records(state.get('unavailable'))[:1500]:
            file = _RestoreFile.decode(record)
            if file is not None:
                unavailable.append((group_index(file.record.get('group')), file))

        return cls(state.get('browser', {}), tuple(groups), tuple(unavailable),
                   group_index(state.get('active_group')), widths('splitter'), widths('editors'))


class ProjectWorkspace(Navigation, qt.QMainWindow):
    title_changed = qt.Signal(str)
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowFlags(qt.Qt.WindowType.Widget)
        self.project = project
        self.view_title = project.name
        self.host_page = None
        self.documents = {}
        self.pending_opens = Counter()
        self.unavailable = []
        self.restoring = True
        self.groups = []
        self.active_group = None
        self.worker = None
        self.queue = deque()
        self.closing = False
        from features.ide.ui.menus import build_menus
        central = qt.QWidget(self)
        self.setCentralWidget(central)
        layout = qt.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.workspace_controls_widget = qt.QWidget(self)
        self.workspace_controls = qt.QHBoxLayout(self.workspace_controls_widget)
        self.workspace_controls.setContentsMargins(0, 0, 0, 0)
        self.workspace_controls.addStretch()
        self.workspace_controls_widget.hide()
        layout.addWidget(self.workspace_controls_widget)
        build_menus(self)
        self.init_navigation()
        self.splitter = qt.QSplitter()
        layout.addWidget(self.splitter, 1)
        self.browser = ProjectBrowser(project, self)
        self.browser.opened.connect(self.open_path)
        self.browser.changed.connect(self.changed)
        self.splitter.addWidget(self.browser)
        self.editors = qt.QSplitter()
        self.splitter.addWidget(self.editors)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setChildrenCollapsible(False)
        self.editors.setChildrenCollapsible(False)
        em = self.fontMetrics().horizontalAdvance('M')
        self.browser.setMinimumWidth(max(160, em * 18))
        self.editors.setMinimumWidth(max(220, em * 24))
        self.splitter.setSizes([max(220, em * 24), 800])
        self.search = SearchPanel(self)
        self.search.hide()
        self.search.idle.connect(self.idle)
        layout.addWidget(self.search)
        self.status = StatusLine()
        layout.addWidget(self.status)
        self.autosave_notice = qt.QLabel()
        self.autosave_notice.setWordWrap(True)
        self.autosave_notice.setTextFormat(qt.Qt.TextFormat.PlainText)
        self.autosave_notice.hide()
        layout.addWidget(self.autosave_notice)
        self.splitter.splitterMoved.connect(self.changed)
        self.editors.splitterMoved.connect(self.changed)
        self.add_group()
        self.reset_root()
        self.watch = qt.QFileSystemWatcher(self)
        self.watch.fileChanged.connect(self.external_change)
        self.restore(project.layout)

    def action(self, label, callback, shortcut=None):
        menu = self.menus['Edit' if label in ('Comment / Uncomment', 'Complete…') else 'Navigate']
        action = menu.addAction(label)
        action.triggered.connect(lambda checked=False: callback())
        if shortcut is not None:
            action.setShortcut(qt.QKeySequence(shortcut))
            action.setShortcutContext(qt.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(action)
        return action

    def error(self, error):
        self.status.setText(str(error))

    def reset_root(self):
        self.browser.reset_root()
        for doc in self.views():
            getattr(doc, 'editor', doc).set_column_guide(self.project.column_guide)
        self.status.setText(str(self.project.root) + ('' if self.project.root.is_dir() else ' — unavailable; registration retained'))

    def run(self, callback, done, failed=None):
        if self.closing:
            return
        self.queue.append((callback, done, failed))
        self.start_next()

    def cancelled(self):
        return self.closing or bool(self.worker and self.worker.isInterruptionRequested())

    def start_next(self):
        if self.worker or not self.queue:
            return
        callback, done, failed = self.queue.popleft()
        worker = self.worker = ResultWorker(callback, self)
        def finished():
            self.worker = None
            try:
                if not self.closing and not worker.isInterruptionRequested():
                    if worker.error:
                        (failed or self.error)(worker.error)
                    else:
                        done(worker.result)
            except Exception as error:
                self.error(error)
            finally:
                worker.deleteLater()
                self.start_next()
                self.idle.emit()
        worker.finished.connect(finished)
        worker.start()

    def add_group(self):
        if len(self.groups) >= 3:
            return None
        group = qt.QTabWidget()
        group.setTabBar(_FileTabBar(group, self.editors, lambda: self.groups, self.drop_editor, self.can_drop_editor))
        # Keep file tabs compact independently of the outer project headers.
        group.tabBar().setStyleSheet('QTabBar::tab { padding: 0px 10px; }')
        group.setMinimumWidth(max(160, self.fontMetrics().horizontalAdvance('M') * 16))
        group.setTabsClosable(True)
        group.tabCloseRequested.connect(lambda index: self.close_document(group.widget(index)))
        group.currentChanged.connect(lambda index: self.activate(group))
        group.tabBar().tabMoved.connect(self.changed)
        self.groups.append(group)
        self.editors.addWidget(group)
        self.active_group = group
        self.editors.setSizes([1] * len(self.groups))
        self.changed.emit()
        return group

    def activate(self, group):
        self.active_group = group
        if hasattr(self, 'search'):
            self.search.set_editor(self.current if isinstance(self.current, EditorDocument) else None)
        self.changed.emit()

    @property
    def current(self):
        return self.active_group.currentWidget() if self.active_group else None

    def group_for(self, doc):
        return next((g for g in self.groups if g.indexOf(doc) >= 0), None)

    def open_dialog(self):
        paths, _ = qt.QFileDialog.getOpenFileNames(self, 'Open text files', str(self.project.root))
        for path in paths:
            self.open_path(path)

    def open_path(self, path, group=None, position=None, encoding=None, restored_record=None, on_open=None):
        if self.closing:
            return
        path = Path(path).expanduser().resolve()
        for existing in self.documents:
            try:
                if path.samefile(existing):
                    path = existing
                    break
            except OSError:
                continue
        explicit_group = group in self.groups
        group = group if explicit_group else self.active_group
        request = _OpenTarget(path, group, explicit_group, position, on_open)
        def loaded(snapshot):
            self._publish_open(request, snapshot)
        if path in self.documents:
            loaded(None)
        else:
            self.pending_opens[path] += 1
            def completed():
                self.pending_opens[path] -= 1
                if not self.pending_opens[path]:
                    del self.pending_opens[path]
            def opened(snapshot):
                completed()
                loaded(snapshot)
            def failed(error):
                completed()
                if encoding is None and ('decode' in error or 'codec' in error):
                    from commonUtils.persistence.text import ENCODINGS
                    value, ok = qt.QInputDialog.getItem(self, 'Choose original encoding',
                        'Decoding failed; choose the source encoding', ENCODINGS, 0, False)
                    if ok:
                        self.open_path(path, group, position, value, restored_record, on_open)
                        return
                if restored_record is not None:
                    self.unavailable.append(restored_record)
                self.error(error)
            self.run(lambda: read_text_file(path, encoding=encoding), opened, failed)

    def _publish_open(self, request, snapshot):
        """Mount a captured open into its surviving group and existing shared buffer."""
        path, group, explicit_group, position, on_open = request
        representative = self.documents.get(path)
        target = group if group in self.groups else self.active_group
        doc = self.view_for(path, target)
        if doc is None and representative is not None and not explicit_group:
            doc = representative
            target = self.group_for(doc)
        if doc is None:
            from features.ide.ui.markdown_document import MarkdownDocument
            document_type = MarkdownDocument if path.suffix.lower() in ('.md', '.markdown') else EditorDocument
            document_type = type(representative) if representative else document_type
            doc = document_type(snapshot, self, buffer=representative.buffer if representative else None)
            getattr(doc, 'editor', doc).set_column_guide(self.project.column_guide)
            if representative is None:
                self.documents[path] = doc
                buffer = doc.buffer
                from features.ide.ui.autosave import AutoSave
                buffer.autosave = AutoSave(self, buffer)
                buffer.markers.run = self.run
                buffer.text.modificationChanged.connect(lambda _: self.update_buffer_titles(buffer))
                self.watch.addPath(str(path))
            if isinstance(doc, EditorDocument):
                doc.link_requested.connect(lambda request, doc=doc: self.query_link(doc, request))
                doc.viewport().installEventFilter(self)
            target.addTab(doc, self.document_icon(doc), doc.title)
            doc.focused.connect(lambda: self.activate(self.group_for(doc)))
            doc.cursorPositionChanged.connect(self.changed)
            doc.verticalScrollBar().valueChanged.connect(self.changed)
        target.setCurrentWidget(doc)
        self.activate(target)
        doc.setFocus()
        self.place_view(doc, position=position)
        if on_open is not None:
            on_open(doc)
        self.changed.emit()

    def views(self):
        return [g.widget(i) for g in self.groups for i in range(g.count())]

    def view_for(self, path, group=None):
        group = group or self.active_group
        return next((group.widget(i) for i in range(group.count()) if group.widget(i).path == path), None) if group else None

    def split_right(self):
        source = self.current
        group = self.add_group()
        if source and group:
            self.navigate_to(source.path, group=group, position=source.textCursor().position(),
                             scroll=source.verticalScrollBar().value())

    def update_buffer_titles(self, buffer):
        self.browser.refresh_unsaved()
        for view in buffer.views:
            group = self.group_for(view)
            if group:
                group.setTabText(group.indexOf(view), view.title)
                group.setTabIcon(group.indexOf(view), self.document_icon(view))
        self.changed.emit()

    def document_icon(self, doc):
        icon = self.browser.model.fileIcon(self.browser.model.index(str(doc.path)))
        return icon if not icon.isNull() else qt.QFileIconProvider().icon(qt.QFileInfo(str(doc.path)))

    def retarget_documents(self, old, new):
        """Follow a successful filesystem rename without replacing live buffers."""
        def updated(path):
            return new / path.relative_to(old) if path.is_relative_to(old) else path
        moved = [(path, updated(path), doc) for path, doc in self.documents.items()
                 if path.is_relative_to(old)]
        for path, target, doc in moved:
            self.documents.pop(path)
            self.watch.removePath(str(path))
            doc.buffer.snapshot = replace(doc.buffer.snapshot, path=target)
            self.documents[target] = doc.buffer.views[0]
            doc.buffer.configure()
            doc.buffer.markers.changed()
            self.watch.addPath(str(target))
            self.update_buffer_titles(doc.buffer)
        self.history = [(str(updated(Path(path))), position, scroll, group)
                        for path, position, scroll, group in self.history]
        self.browser.refresh_unsaved()

    def update_title(self, doc):
        self.update_buffer_titles(doc.buffer)

    def refresh_autosave_notice(self):
        errors = [doc.buffer.autosave.error for doc in self.documents.values() if doc.buffer.autosave.error]
        self.autosave_notice.setText('\n'.join(errors))
        self.autosave_notice.setVisible(bool(errors))

    def set_autosave(self, mode):
        self.project.autosave = mode
        for doc in self.documents.values():
            doc.buffer.autosave.timer.stop()
            if mode == 'after_delay':
                doc.buffer.autosave.schedule()
        self.changed.emit()

    def save_current(self, save_as=False):
        doc = self.current
        return self.save_document(doc, save_as) if doc else True

    @pause_autosave
    def save_document(self, doc, save_as=False):
        if doc.buffer.autosave.busy:
            self.error('Autosave is finishing. Please retry Save when it completes.')
            return False
        doc.buffer.autosave.timer.stop()
        target = None
        expected = None
        if save_as:
            name, _ = qt.QFileDialog.getSaveFileName(self, 'Save As', str(doc.path), 'All files (*)',
                options=qt.QFileDialog.Option.DontConfirmOverwrite)
            if not name:
                return False
            target = Path(name).resolve()
            for other in self.documents.values():
                if other.buffer is doc.buffer:
                    continue
                same = target == other.path
                try:
                    same = same or target.samefile(other.path)
                except OSError:
                    pass
                if same:
                    self.error('That file already has an open buffer.')
                    return False
        old = doc.path
        try:
            if target and target != old and target.exists():
                from commonUtils.persistence.text import MAX_BYTES
                with target.open('rb') as stream:
                    expected = stream.read(MAX_BYTES + 1)
                if len(expected) > MAX_BYTES:
                    raise ValueError('Destination exceeds the 16 MiB file limit.')
                if qt.QMessageBox.question(self, 'Replace file?', str(target),
                        qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                        qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Yes:
                    return False
            doc.save(target, expected=expected)
        except (OSError, ValueError) as error:
            self.error(f'Save failed: {error}. Reload or Save As a new file to preserve both versions.')
            return False
        self.documents.pop(old, None)
        self.documents[doc.path] = doc.buffer.views[0]
        self.watch.removePath(str(old))
        self.watch.addPath(str(doc.path))
        self.update_title(doc)
        doc.buffer.autosave.reset()
        self.status.setText('Saved.')
        return True

    @pause_autosave
    def confirm_document(self, doc):
        if doc.buffer.autosave.busy:
            self.error('Autosave is finishing. Please retry closing when it completes.')
            return False
        doc.buffer.autosave.timer.stop()
        if not doc.document().isModified():
            return True
        choice = qt.QMessageBox.question(self, 'Unsaved changes', f'Save changes to {doc.path.name}?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Save)
        if choice == qt.QMessageBox.StandardButton.Save:
            return self.save_document(doc)
        return choice == qt.QMessageBox.StandardButton.Discard

    def close_document(self, doc, *, prune=True):
        if doc is None or (len(doc.buffer.views) == 1 and not self.confirm_document(doc)):
            return False
        group = self.group_for(doc)
        group.removeTab(group.indexOf(doc))
        remaining = [view for view in doc.buffer.views if view is not doc]
        if remaining:
            self.documents[doc.path] = remaining[0]
        else:
            self.documents.pop(doc.path, None)
            self.watch.removePath(str(doc.path))
        doc.release()
        self.browser.refresh_unsaved()
        self.refresh_autosave_notice()
        if prune:
            self.remove_empty_groups()
        self.activate(self.active_group)
        self.changed.emit()
        return True

    def close_all(self):
        group = self.active_group
        while group.count():
            if not self.close_document(group.widget(0)):
                return False
        return True

    def close_group(self):
        if len(self.groups) == 1:
            return
        group = self.active_group
        # Closing a layout column retains every buffer by moving its tabs.
        target = self.groups[max(0, self.groups.index(group) - 1)]
        if target is group:
            target = self.groups[1]
        while group.count():
            doc = group.widget(0)
            if self.view_for(doc.path, target):
                self.close_document(doc, prune=False)
            else:
                group.removeTab(0)
                target.addTab(doc, self.document_icon(doc), doc.title)
        self.groups.remove(group)
        group.setParent(None)
        group.deleteLater()
        self.activate(target)

    def remove_empty_groups(self):
        for group in tuple(self.groups):
            if group.count() == 0 and len(self.groups) > 1:
                self.groups.remove(group)
                group.setParent(None)
                group.deleteLater()
        if self.active_group not in self.groups:
            self.activate(self.groups[0])

    def can_drop_editor(self, doc, target, placement='tabs', index=None):
        source = self.group_for(doc)
        if source is None or target not in self.groups or self.closing:
            return False
        if placement == 'tabs' or (placement in ('left', 'right') and not target.count()):
            return True
        if placement not in ('left', 'right'):
            return False
        # A single-file column is repositioned, not duplicated. Its own edge
        # would make no layout change and should not show a misleading preview.
        if source.count() == 1:
            return source is not target
        return len(self.groups) < 3

    def drop_editor(self, doc, target, placement='tabs', index=None):
        if not self.can_drop_editor(doc, target, placement, index):
            return False
        source = self.group_for(doc)
        if not target.count():
            placement = 'tabs'
        if placement != 'tabs':
            if source.count() == 1:
                self.groups.remove(source)
                position = self.groups.index(target) + (placement == 'right')
                self.groups.insert(position, source)
                self.editors.insertWidget(position, source)
                self.activate(source)
                doc.setFocus()
                self.changed.emit()
                return True
            position = self.groups.index(target) + (placement == 'right')
            target = self.add_group()
            self.groups.remove(target)
            self.groups.insert(position, target)
            self.editors.insertWidget(position, target)
        if source is target:
            destination = max(0, min(index if index is not None else target.count()-1, target.count()-1))
            target.tabBar().moveTab(source.indexOf(doc), destination)
        else:
            existing = self.view_for(doc.path, target)
            if existing:
                self.close_document(doc)
                doc = existing
            else:
                source.removeTab(source.indexOf(doc))
                target.insertTab(target.count() if index is None else index, doc, self.document_icon(doc), doc.title)
        target.setCurrentWidget(doc)
        self.activate(target)
        self.remove_empty_groups()
        doc.setFocus()
        self.changed.emit()
        return True

    def move(self, direction):
        doc = self.current
        if not doc:
            return
        index = self.groups.index(self.active_group) + direction
        if index == len(self.groups) and len(self.groups) < 3:
            self.add_group()
        if 0 <= index < len(self.groups):
            self.drop_editor(doc, self.groups[index])

    def install_project_menu(self, page):
        from features.ide.ui.menus import install_project_menu
        install_project_menu(self, page)

    def find(self):
        self.search.set_editor(self.current if isinstance(self.current, EditorDocument) else None)
        if self.current and not isinstance(self.current, EditorDocument):
            self.current.show_find()
            return
        self.search.open(replace=True)

    def locate(self):
        if self.current:
            self.browser.locate(self.current.path)

    def external_change(self, path):
        path = Path(path)
        doc = self.documents.get(path)
        if doc is None:
            return
        snapshot, buffer = doc.snapshot, doc.buffer
        def changed_on_disk():
            try:
                with path.open('rb') as stream:
                    return stream.read(len(snapshot.original) + 1) != snapshot.original
            except FileNotFoundError:
                return True
        def checked(changed):
            if path in self.documents and self.documents[path].buffer is buffer and buffer.snapshot is snapshot and changed:
                self.status.setText(f'File changed or removed externally: {path}. Reload to read it; saving checks for conflicts.')
        self.run(changed_on_disk, checked)
        if path.exists():
            self.watch.addPath(str(path))

    @pause_autosave
    def reload_current(self):
        doc = self.current
        if not doc:
            return
        if doc.buffer.autosave.busy:
            self.error('Autosave is finishing. Please retry Reload when it completes.')
            return
        doc.buffer.autosave.timer.stop()
        if doc.document().isModified() and qt.QMessageBox.question(self, 'Reload?', 'Discard unsaved buffer and reload?',
                qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Discard:
            return
        try:
            doc.reload()
            doc.buffer.autosave.reset()
        except (OSError, ValueError) as error:
            self.error(error)

    def state(self):
        if self.restoring:
            return self.project.layout
        return {'unavailable': self.unavailable, 'browser': self.browser.state(), 'groups': [{'files': [{'path': str(g.widget(i).path), 'cursor': g.widget(i).textCursor().position(), 'scroll': g.widget(i).verticalScrollBar().value()} for i in range(g.count())],
                            'active': str(g.currentWidget().path) if g.currentWidget() else None} for g in self.groups],
                'active_group': self.groups.index(self.active_group) if self.active_group in self.groups else 0,
                'splitter': self.saved_sizes(self.splitter, 'splitter'),
                'editors': self.saved_sizes(self.editors, 'editors')}

    def saved_sizes(self, splitter, key):
        sizes = splitter.sizes()
        if any(sizes):
            return sizes
        previous = self.project.layout.get(key)
        if isinstance(previous, list) and len(previous) == splitter.count() and all(isinstance(n, int) and n >= 0 for n in previous) and any(previous):
            return previous
        return [1] * splitter.count()

    def restore(self, state):
        plan = _RestorePlan.decode(state)
        self.browser.restore(plan.browser)
        for index, entry in enumerate(plan.groups):
            group = self.groups[0] if index == 0 else self.add_group()
            for file in entry.files[:500]:
                if file is not None and not self._retain_if_missing(file):
                    self.open_path(file.path, group, file.cursor, restored_record=file.record)

        returned = []
        for index, file in plan.unavailable:
            if self._retain_if_missing(file):
                continue
            while len(self.groups) <= index:
                self.add_group()
            self.open_path(file.path, self.groups[index], file.cursor, restored_record=file.record)
            returned.append((index, file))

        def restored(_):
            self._finish_restore(plan, returned)
        self.run(lambda: None, restored)

    def _retain_if_missing(self, file):
        if file.path.is_file():
            return False
        self.unavailable.append(file.record)
        return True

    def _finish_restore(self, plan, returned):
        """Apply scroll positions, selection and widths after the queued reads."""
        def place_scroll(group, file):
            if file is not None and file.scroll is not None:
                doc = self.view_for(file.path.resolve(), group)
                if doc:
                    self.place_view(doc, scroll=file.scroll)

        self.restoring = False
        for index, file in returned:
            group = self.groups[index] if index < len(self.groups) else self.groups[0]
            place_scroll(group, file)
        for group, entry in zip(self.groups, plan.groups):
            doc = self.view_for(entry.active.resolve(), group) if entry.active is not None else None
            for file in entry.files:
                place_scroll(group, file)
            if doc and self.group_for(doc) is group:
                group.setCurrentWidget(doc)
        active = plan.active_group
        self.activate(self.groups[active] if active < len(self.groups) else self.groups[0])
        if plan.splitter:
            self.splitter.setSizes(plan.splitter)
        if plan.editors:
            sizes = plan.editors
            # Earlier drag previews were accidentally QSplitter children.
            # Recover the real widths from those alternating hidden panes.
            if len(sizes) == 2 * self.editors.count() and not any(sizes[::2]):
                sizes = sizes[1::2]
            self.editors.setSizes(sizes)

    @pause_autosave
    def can_close(self):
        if self.worker or self.queue:
            self.error('Please wait for the current operation to finish before closing.')
            return False
        return all(self.confirm_document(doc) for doc in list(self.documents.values()))

    def prepare_close(self):
        if self.host_page is not None:
            if not self.host_page._closing_approved and not self.can_close():
                return False
            self.project.layout = self.state()
        self.queue.clear()
        self.pending_opens.clear()
        if self.worker:
            self.worker.cancel()
        ready = self.search.prepare_close() and self.worker is None
        if getattr(self, 'project_find', None) is not None:
            ready = self.project_find.prepare_close() and ready
        self.closing = ready
        if ready:
            self.browser.git_status.stop()
            for doc in self.views():
                doc.buffer.autosave.timer.stop()
                if hasattr(doc, 'speech'):
                    doc.speech.stop()
                    if doc._diagram_renderer:
                        doc._diagram_renderer.cancel()
        return ready
