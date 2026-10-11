"""Project registration, retained tabs and application close participation."""
from commonUtils.ui import pyside as qt
from .projects import Project, ProjectStore


class IDEPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, store_path=None):
        super().__init__(parent)
        self.store = ProjectStore(store_path)
        layout = qt.QVBoxLayout(self)
        bar = qt.QToolBar()
        layout.addWidget(bar)
        for text, callback in [('Register project…', self.register_project), ('Reopen…', self.reopen),
                               ('Project settings…', self.settings), ('Remove registration…', self.remove_registration)]:
            bar.addAction(text).triggered.connect(callback)
        self.tabs = qt.QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_project)
        layout.addWidget(self.tabs, 1)
        self.status = qt.QLabel(self.store.error or 'Register an existing directory to begin.')
        self.status.setWordWrap(True)
        self.status.setSizePolicy(qt.QSizePolicy.Policy.Preferred, qt.QSizePolicy.Policy.Maximum)
        layout.addWidget(self.status)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.persist)
        for identity in self.store.open_ids:
            self.open_project(self.store.projects[identity])
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).project.id == self.store.active_id:
                self.tabs.setCurrentIndex(i)
        self.tabs.currentChanged.connect(self.changed)
        self.tabs.tabBar().tabMoved.connect(self.changed)

    def changed(self, *args):
        self.timer.start()

    def persist(self):
        self.store.open_ids = [self.tabs.widget(i).project.id for i in range(self.tabs.count())]
        current = self.tabs.currentWidget()
        self.store.active_id = current.project.id if current else None
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            view.project.layout = view.state()
        try:
            self.store.save()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            return False
        return True

    def open_project(self, project):
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).project.id == project.id:
                self.tabs.setCurrentIndex(i)
                return self.tabs.widget(i)
        from .workspace import ProjectWorkspace
        view = ProjectWorkspace(project, self)
        view.changed.connect(self.changed)
        view.idle.connect(self.idle)
        self.tabs.addTab(view, project.name)
        self.tabs.setCurrentWidget(view)
        self.status.setText('Project settings and layout are saved outside source directories.')
        self.changed()
        return view

    def edit_project(self, project):
        dialog = qt.QDialog(self)
        dialog.setWindowTitle('IDE project settings')
        layout = qt.QFormLayout(dialog)
        fields = {}
        for label, key, value in [('Display name', 'name', project.name), ('Root directory', 'root_path', str(project.root)),
                                  ('Source paths (one per line)', 'source_paths', '\n'.join(project.source_paths)),
                                  ('Excluded names/relative paths (one per line)', 'excluded_paths', '\n'.join(project.excluded_paths)),
                                  ('Python interpreter/environment (optional)', 'python_interpreter', project.python_interpreter or '')]:
            widget = qt.QPlainTextEdit(value) if key.endswith('_paths') else qt.QLineEdit(value)
            fields[key] = widget
            layout.addRow(label, widget)
        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.StandardButton.Ok | qt.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != qt.QDialog.DialogCode.Accepted:
            return False
        if not fields['name'].text().strip() or not fields['root_path'].text().strip():
            return False
        for key, widget in fields.items():
            value = widget.toPlainText().splitlines() if key.endswith('_paths') else widget.text().strip()
            setattr(project, key, value if key != 'python_interpreter' else value or None)
        project.root_path = str(project.root)
        return True

    def register_project(self):
        from pathlib import Path
        root = qt.QFileDialog.getExistingDirectory(self, 'Register existing project directory')
        if not root:
            return
        for project in self.store.projects.values():
            if project.root == Path(root).resolve():
                self.open_project(project)
                return
        project = Project(Path(root).name, root)
        if self.edit_project(project):
            self.store.projects[project.id] = project
            self.open_project(project)

    def reopen(self):
        projects = list(self.store.projects.values())
        labels = [f'{p.name} — {p.root} [{p.id[:8]}]' for p in projects]
        value, ok = qt.QInputDialog.getItem(self, 'Reopen project', 'Registered projects', labels, 0, False)
        if ok and value in labels:
            self.open_project(projects[labels.index(value)])

    def settings(self):
        view = self.tabs.currentWidget()
        if view and self.edit_project(view.project):
            view.reset_root()
            self.tabs.setTabText(self.tabs.currentIndex(), view.project.name)
            self.changed()

    def close_project(self, index):
        view = self.tabs.widget(index)
        if not view.can_close() or not view.prepare_close():
            return False
        view.project.layout = view.state()
        self.tabs.removeTab(index)
        view.deleteLater()
        self.persist()
        return True

    def remove_registration(self):
        view = self.tabs.currentWidget()
        if view and qt.QMessageBox.question(self, 'Remove registration?',
                f'Remove {view.project.name} from IDE? No project files will be deleted.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
            identity = view.project.id
            if self.close_project(self.tabs.currentIndex()):
                del self.store.projects[identity]
                self.persist()

    def can_close(self):
        return all(self.tabs.widget(i).can_close() for i in range(self.tabs.count()))

    def prepare_close(self):
        ready = all([self.tabs.widget(i).prepare_close() for i in range(self.tabs.count())])
        if ready:
            self.timer.stop()
            self.persist()
            return True
        return False
