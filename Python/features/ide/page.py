"""Project registration, retained tabs and application close participation."""
from commonUtils.ui import pyside as qt
from commonUtils.ui.appearance.status_line import StatusLine
from .projects import Project, ProjectStore
from commonUtils.ui.workspaces.workspace import Workspace
from commonUtils.ui.workspaces.workspace_policy import WorkspacePolicy


class IDEPage(qt.QWidget):
    idle = qt.Signal()

    def __init__(self, parent=None, *, store_path=None):
        super().__init__(parent)
        self.setProperty('navigation_position', 'workspace')
        self.setProperty('navigation_order', 19)
        self.store = ProjectStore(store_path)
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._closing_approved = False
        self.workspace = Workspace(self._create_project, self, dock_group=self,
            policy=WorkspacePolicy(show_single_tab_in_detached=False, detached_title='IDE: {title}'),
            new_view=self.project_menu, setup_container=self.setup_container)
        self.setup_container(self.workspace)
        layout.addWidget(self.workspace, 1)
        self.workspace._drop_target.widget().setText('Open or reopen a project with +.')
        self.status = StatusLine(self.store.error or '')
        self.status.setWordWrap(True)
        self.status.setVisible(bool(self.store.error))
        layout.addWidget(self.status)
        self.timer = qt.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.persist)
        for identity in self.store.open_ids:
            self.open_project(self.store.projects[identity])
        for dock in self.workspace.all_docks:
            if dock.widget().project.id == self.store.active_id:
                dock.raise_()
                dock.workspace._activate(dock)

    def setup_container(self, workspace):
        workspace.close_action.setEnabled(False)  # Ctrl+W closes the active file.
        workspace.active_changed.connect(self.changed)
        workspace.tabs_changed.connect(self.changed)

    @property
    def views(self):
        return [dock.widget() for dock in self.workspace.all_docks]

    def dock_for(self, view):
        return next((dock for dock in self.workspace.all_docks if dock.widget() is view), None)

    def project_menu(self, workspace):
        menu = qt.QMenu(workspace)
        menu.addAction('Register / Open existing project…', lambda: self.register_project(workspace))
        menu.addAction('Reopen project…', lambda: self.reopen(workspace)).setEnabled(bool(self.store.projects))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(qt.QCursor.pos())
        return menu

    def changed(self, *args):
        self._closing_approved = False
        self.timer.start()

    def persist(self):
        self.store.open_ids = [view.project.id for view in self.views]
        current = next((view for view in self.views if view.isAncestorOf(qt.QApplication.focusWidget())), None) if qt.QApplication.focusWidget() else None
        current = current or self.workspace.active_view
        self.store.active_id = current.project.id if current else None
        for view in self.views:
            view.project.layout = view.state()
        try:
            self.store.save()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            self.status.show()
            return False
        return True

    def open_project(self, project, destination=None):
        for dock in self.workspace.all_docks:
            if dock.widget().project.id == project.id:
                if destination is not None and dock.workspace is not destination:
                    if not destination.adopt(dock):
                        return None
                dock.raise_()
                dock.workspace._activate(dock)
                dock.window().raise_()
                return dock.widget()
        return (destination or self.workspace).add_view(project)

    def open_registered_file(self, path):
        """Open in the most specific registered root, including closed projects."""
        from pathlib import Path
        path = Path(path).expanduser().resolve()
        matches = [project for project in self.store.projects.values()
                   if path.is_relative_to(project.root)]
        if not matches:
            return False
        project = max(matches, key=lambda project: len(project.root.parts))
        view = self.open_project(project)
        if view is None:
            return False
        view.open_path(path)
        return True

    def _create_project(self, project):
        from .workspace import ProjectWorkspace
        view = ProjectWorkspace(project, self)
        view.host_page = self
        view.changed.connect(self.changed)
        view.idle.connect(self.idle)
        view.install_project_menu(self)
        self.changed()
        return view

    def edit_project(self, project, parent=None):
        dialog = qt.QDialog(parent or self)
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
        column_guide = qt.QSpinBox(dialog)
        column_guide.setRange(0, 1000)
        column_guide.setSpecialValueText('Off')
        column_guide.setValue(project.column_guide)
        column_guide.setToolTip('Visual line-length guide for all source editors in this project; does not wrap or limit text.')
        layout.addRow('Column guide (0 = off)', column_guide)
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
        project.column_guide = column_guide.value()
        return True

    def register_project(self, destination=None):
        from pathlib import Path
        root = qt.QFileDialog.getExistingDirectory(destination.window() if destination else self, 'Register existing project directory')
        if not root:
            return
        for project in self.store.projects.values():
            if project.root == Path(root).resolve():
                self.open_project(project, destination)
                return
        project = Project(Path(root).name, root)
        if self.edit_project(project, destination.window() if destination else self):
            self.store.projects[project.id] = project
            self.open_project(project, destination)

    def reopen(self, destination=None):
        projects = list(self.store.projects.values())
        labels = [f'{p.name} — {p.root} [{p.id[:8]}]' for p in projects]
        value, ok = qt.QInputDialog.getItem(destination.window() if destination else self, 'Reopen project', 'Registered projects', labels, 0, False)
        if ok and value in labels:
            self.open_project(projects[labels.index(value)], destination)

    def settings(self, view=None):
        view = view or self.workspace.active_view
        if view and self.edit_project(view.project, view.window()):
            view.reset_root()
            view.title_changed.emit(view.project.name)
            self.changed()

    def close_project(self, view=None):
        view = view or self.workspace.active_view
        dock = self.dock_for(view)
        if dock is None:
            return False
        return dock.close()

    def remove_registration(self, view=None):
        view = view or self.workspace.active_view
        if view and qt.QMessageBox.question(self, 'Remove registration?',
                f'Remove {view.project.name} from IDE? No project files will be deleted.',
                qt.QMessageBox.StandardButton.Yes | qt.QMessageBox.StandardButton.Cancel,
                qt.QMessageBox.StandardButton.Cancel) == qt.QMessageBox.StandardButton.Yes:
            identity = view.project.id
            if self.close_project(view):
                del self.store.projects[identity]
                self.persist()

    def can_close(self):
        self._closing_approved = all(view.can_close() for view in self.views)
        return self._closing_approved

    def prepare_close(self):
        if not self._closing_approved and not self.can_close():
            return False
        self.timer.stop()
        self.persist()
        return self.workspace.prepare_close()
