"""Project-scoped documents, non-detachable groups and cooperative workers."""
from collections import deque
from pathlib import Path
from commonUtils.ui import pyside as qt
from commonUtils.ui.operations import ResultWorker
from commonUtils.ui.code_editor.search import SearchPanel
from commonUtils.persistence.text import read_text_file
from .documents import EditorDocument
from .browser import ProjectBrowser
from .navigation import Navigation


class ProjectWorkspace(Navigation, qt.QWidget):
    changed = qt.Signal()
    idle = qt.Signal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.documents = {}
        self.unavailable = []
        self.restoring = True
        self.groups = []
        self.active_group = None
        self.worker = None
        self.queue = deque()
        self.closing = False
        layout = qt.QVBoxLayout(self)
        self.bar = qt.QToolBar()
        layout.addWidget(self.bar)
        for label, callback, shortcut in [
            ('Open…', self.open_dialog, qt.QKeySequence.StandardKey.Open),
            ('Save', self.save_current, qt.QKeySequence.StandardKey.Save),
            ('Save As…', lambda: self.save_current(True), qt.QKeySequence.StandardKey.SaveAs),
            ('Reload', self.reload_current, None), ('Find / Replace', self.find, qt.QKeySequence.StandardKey.Find),
            ('Split right', self.add_group, None), ('Move left', lambda: self.move(-1), None),
            ('Move right', lambda: self.move(1), None), ('Close group', self.close_group, None),
            ('Close all in group', self.close_all, None), ('Locate file', self.locate, None)]:
            self.action(label, callback, shortcut)
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
        self.search = SearchPanel(self)
        self.search.hide()
        self.search.idle.connect(self.idle)
        layout.addWidget(self.search)
        self.status = qt.QLabel()
        self.status.setWordWrap(True)
        self.status.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        layout.addWidget(self.status)
        self.splitter.splitterMoved.connect(self.changed)
        self.editors.splitterMoved.connect(self.changed)
        self.add_group()
        self.reset_root()
        self.watch = qt.QFileSystemWatcher(self)
        self.watch.fileChanged.connect(self.external_change)
        self.restore(project.layout)

    def action(self, label, callback, shortcut=None):
        action = self.bar.addAction(label)
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
            if not self.closing and not worker.isInterruptionRequested():
                if worker.error:
                    (failed or self.error)(worker.error)
                else:
                    done(worker.result)
            worker.deleteLater()
            self.start_next()
            self.idle.emit()
        worker.finished.connect(finished)
        worker.start()

    def add_group(self):
        if len(self.groups) >= 3:
            return None
        group = qt.QTabWidget()
        group.setMovable(True)
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
            self.search.set_editor(self.current)
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

    def open_path(self, path, group=None, position=None, encoding=None):
        path = Path(path).expanduser().resolve()
        for existing in self.documents:
            try:
                if path.samefile(existing):
                    path = existing
                    break
            except OSError:
                continue
        group = group if group in self.groups else self.active_group
        def loaded(snapshot):
            doc = self.documents.get(path)
            if doc is None:
                doc = EditorDocument(snapshot, self)
                self.documents[path] = doc
                doc.viewport().installEventFilter(self)
                target = group if group in self.groups else self.active_group
                target.addTab(doc, doc.title)
                doc.document().modificationChanged.connect(lambda _: self.update_title(doc))
                doc.focused.connect(lambda: self.activate(self.group_for(doc)))
                doc.cursorPositionChanged.connect(self.changed)
                doc.verticalScrollBar().valueChanged.connect(self.changed)
                self.watch.addPath(str(path))
            target = self.group_for(doc)
            target.setCurrentWidget(doc)
            self.activate(target)
            doc.setFocus()
            if position is not None:
                cursor = doc.textCursor()
                cursor.setPosition(min(position, doc.document().characterCount() - 1))
                doc.setTextCursor(cursor)
                doc.centerCursor()
            self.changed.emit()
        if path in self.documents:
            loaded(None)
        else:
            def failed(error):
                if encoding is None and ('decode' in error or 'codec' in error):
                    from commonUtils.persistence.text import ENCODINGS
                    value, ok = qt.QInputDialog.getItem(self, 'Choose original encoding',
                        'Decoding failed; choose the source encoding', ENCODINGS, 0, False)
                    if ok:
                        self.open_path(path, group, position, value)
                        return
                self.error(error)
            self.run(lambda: read_text_file(path, encoding=encoding), loaded, failed)

    def update_title(self, doc):
        group = self.group_for(doc)
        if group:
            group.setTabText(group.indexOf(doc), doc.title)
        self.changed.emit()

    def save_current(self, save_as=False):
        doc = self.current
        return self.save_document(doc, save_as) if doc else True

    def save_document(self, doc, save_as=False):
        target = None
        expected = None
        if save_as:
            name, _ = qt.QFileDialog.getSaveFileName(self, 'Save As', str(doc.path), 'All files (*)',
                options=qt.QFileDialog.Option.DontConfirmOverwrite)
            if not name:
                return False
            target = Path(name).resolve()
            for other in self.documents.values():
                if other is doc:
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
        self.documents[doc.path] = doc
        self.watch.removePath(str(old))
        self.watch.addPath(str(doc.path))
        self.update_title(doc)
        self.status.setText('Saved.')
        return True

    def confirm_document(self, doc):
        if not doc.document().isModified():
            return True
        choice = qt.QMessageBox.question(self, 'Unsaved changes', f'Save changes to {doc.path.name}?',
            qt.QMessageBox.StandardButton.Save | qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
            qt.QMessageBox.StandardButton.Save)
        if choice == qt.QMessageBox.StandardButton.Save:
            return self.save_document(doc)
        return choice == qt.QMessageBox.StandardButton.Discard

    def close_document(self, doc):
        if doc is None or not self.confirm_document(doc):
            return False
        group = self.group_for(doc)
        group.removeTab(group.indexOf(doc))
        self.documents.pop(doc.path, None)
        self.watch.removePath(str(doc.path))
        doc.deleteLater()
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
            group.removeTab(0)
            target.addTab(doc, doc.title)
        self.groups.remove(group)
        group.setParent(None)
        group.deleteLater()
        self.activate(target)

    def move(self, direction):
        doc = self.current
        if not doc:
            return
        index = self.groups.index(self.active_group) + direction
        if index == len(self.groups):
            self.add_group()
        if 0 <= index < len(self.groups):
            source = self.group_for(doc)
            source.removeTab(source.indexOf(doc))
            target = self.groups[index]
            target.addTab(doc, doc.title)
            target.setCurrentWidget(doc)
            self.activate(target)
            doc.setFocus()

    def find(self):
        self.search.set_editor(self.current)
        self.search.open(replace=True)

    def locate(self):
        if self.current:
            self.browser.locate(self.current.path)

    def external_change(self, path):
        path = Path(path)
        doc = self.documents.get(path)
        if doc is None:
            return
        snapshot = doc.snapshot
        def changed_on_disk():
            try:
                with path.open('rb') as stream:
                    return stream.read(len(snapshot.original) + 1) != snapshot.original
            except FileNotFoundError:
                return True
        def checked(changed):
            if self.documents.get(path) is doc and doc.snapshot is snapshot and changed:
                self.status.setText(f'File changed or removed externally: {path}. Reload to read it; saving checks for conflicts.')
        self.run(changed_on_disk, checked)
        if path.exists():
            self.watch.addPath(str(path))

    def reload_current(self):
        doc = self.current
        if not doc:
            return
        if doc.document().isModified() and qt.QMessageBox.question(self, 'Reload?', 'Discard unsaved buffer and reload?',
                qt.QMessageBox.StandardButton.Discard | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) != qt.QMessageBox.StandardButton.Discard:
            return
        try:
            doc.reload()
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
        self.browser.restore(state.get('browser', {}))
        groups = state.get('groups', [])
        if not isinstance(groups, list):
            groups = []
        for index, entry in enumerate(groups[:3]):
            group = self.groups[0] if index == 0 else self.add_group()
            if not isinstance(entry, dict):
                continue
            files = entry.get('files', [])
            if not isinstance(files, list):
                continue
            for record in files[:500]:
                if isinstance(record, dict) and isinstance(record.get('path'), str):
                    position = record.get('cursor', 0)
                    position = max(0, position) if isinstance(position, int) else 0
                    if Path(record['path']).is_file():
                        self.open_path(record['path'], group, position)
                    else:
                        self.unavailable.append(record)
        for record in state.get('unavailable', []) if isinstance(state.get('unavailable', []), list) else []:
            if isinstance(record, dict) and isinstance(record.get('path'), str):
                if Path(record['path']).is_file():
                    self.open_path(record['path'])
                else:
                    self.unavailable.append(record)
        def restored(_):
            self.restoring = False
            for group, entry in zip(self.groups, groups):
                if not isinstance(entry, dict):
                    continue
                active_path = entry.get('active')
                doc = self.documents.get(Path(active_path).resolve()) if isinstance(active_path, str) else None
                for record in entry.get('files', []) if isinstance(entry.get('files', []), list) else []:
                    if isinstance(record, dict) and isinstance(record.get('path'), str) and isinstance(record.get('scroll', 0), int):
                        opened = self.documents.get(Path(record['path']).resolve())
                        if opened:
                            opened.verticalScrollBar().setValue(record.get('scroll', 0))
                if doc and self.group_for(doc) is group:
                    group.setCurrentWidget(doc)
            active = state.get('active_group', 0)
            self.activate(self.groups[active] if isinstance(active, int) and 0 <= active < len(self.groups) else self.groups[0])
            for key, splitter in [('splitter', self.splitter), ('editors', self.editors)]:
                sizes = state.get(key)
                if isinstance(sizes, list) and all(isinstance(n, int) and n >= 0 for n in sizes) and any(sizes):
                    splitter.setSizes(sizes)
        self.run(lambda: None, restored)

    def can_close(self):
        if self.worker or self.queue:
            self.error('Please wait for the current operation to finish before closing.')
            return False
        return all(self.confirm_document(doc) for doc in list(self.documents.values()))

    def prepare_close(self):
        self.queue.clear()
        if self.worker:
            self.worker.cancel()
        ready = self.search.prepare_close() and self.worker is None
        self.closing = ready
        return ready
