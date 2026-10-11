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
        layout.addWidget(self.splitter)
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

    def run(self, callback, done):
        if self.closing:
            return
        self.queue.append((callback, done))
        self.start_next()

    def cancelled(self):
        return self.closing or bool(self.worker and self.worker.isInterruptionRequested())

    def start_next(self):
        if self.worker or not self.queue:
            return
        callback, done = self.queue.popleft()
        worker = self.worker = ResultWorker(callback, self)
        def finished():
            self.worker = None
            if not self.closing:
                if worker.error:
                    self.error(worker.error)
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

    def open_path(self, path, group=None, position=None):
        path = Path(path).expanduser().resolve()
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
            self.run(lambda: read_text_file(path), loaded)

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
        if save_as:
            name, _ = qt.QFileDialog.getSaveFileName(self, 'Save As (choose a new file)', str(doc.path))
            if not name:
                return False
            target = Path(name).resolve()
            if target in self.documents and self.documents[target] is not doc:
                self.error('That file already has an open buffer.')
                return False
        old = doc.path
        try:
            doc.save(target)
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
        self.search.show()

    def locate(self):
        if self.current:
            self.browser.locate(self.current.path)

    def external_change(self, path):
        if Path(path) in self.documents:
            self.status.setText(f'File changed or removed externally: {path}. Reload to read it; saving checks for conflicts.')
        if Path(path).exists():
            self.watch.addPath(path)

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
        return {'groups': [{'files': [{'path': str(g.widget(i).path), 'cursor': g.widget(i).textCursor().position()} for i in range(g.count())],
                            'active': str(g.currentWidget().path) if g.currentWidget() else None} for g in self.groups],
                'active_group': self.groups.index(self.active_group) if self.active_group in self.groups else 0,
                'splitter': self.splitter.sizes(), 'editors': self.editors.sizes()}

    def restore(self, state):
        groups = state.get('groups', [])
        if not isinstance(groups, list):
            return
        for index, entry in enumerate(groups[:3]):
            group = self.groups[0] if index == 0 else self.add_group()
            if not isinstance(entry, dict):
                continue
            for record in entry.get('files', []):
                if isinstance(record, dict) and isinstance(record.get('path'), str):
                    self.open_path(record['path'], group, record.get('cursor', 0))
        def restored(_):
            for group, entry in zip(self.groups, groups):
                doc = self.documents.get(Path(entry.get('active') or ''))
                if doc and self.group_for(doc) is group:
                    group.setCurrentWidget(doc)
            active = state.get('active_group', 0)
            self.activate(self.groups[active] if isinstance(active, int) and 0 <= active < len(self.groups) else self.groups[0])
            for key, splitter in [('splitter', self.splitter), ('editors', self.editors)]:
                sizes = state.get(key)
                if isinstance(sizes, list) and all(isinstance(n, int) and n >= 0 for n in sizes):
                    splitter.setSizes(sizes)
        self.run(lambda: None, restored)

    def can_close(self):
        if self.worker or self.queue:
            self.error('Please wait for the current operation to finish before closing.')
            return False
        return all(self.confirm_document(doc) for doc in list(self.documents.values()))

    def prepare_close(self):
        self.closing = True
        self.queue.clear()
        if self.worker:
            self.worker.cancel()
        return self.search.prepare_close() and self.worker is None
